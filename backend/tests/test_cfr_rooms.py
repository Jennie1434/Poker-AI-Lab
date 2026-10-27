import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from pokerbench.config import Entry, Settings
from pokerbench.engine import Hand
from pokerbench.local_agents import LOCAL_POLICIES, decide, local_entries


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Real Provider: local CFR decisions run in-process; sockets stay forbidden."""
    import pokerbench.api as api_module
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'entries.json').write_text(json.dumps(
        [Entry(id='bot', name='Local Model', provider='systemone', key_env='', proxy=False).model_dump()]))
    monkeypatch.setattr(api_module, 'ROOT', tmp_path)
    app = api_module.create_app(Settings(_env_file=None, pokerbench_data_dir=str(tmp_path / 'data')))
    with TestClient(app) as c:
        assert c.post('/api/auth/register', json={'id': 'cfr-player', 'password': 'test-password'}).status_code == 200
        yield c, app


def test_local_policies_are_registered_and_never_join_the_benchmark_roster(client):
    c, _ = client
    models = {e['id']: e for e in c.get('/api/rooms/models').json()}
    for key in LOCAL_POLICIES:
        assert models[key]['provider'] == 'local_cfr' and models[key]['ready'] is True
    assert all(e.revision != 'missing' for e in local_entries())
    assert not {e['id'] for e in c.get('/api/entries').json()} & set(LOCAL_POLICIES)


@pytest.mark.parametrize('body', [{'model_ids': ['cfr-v1', 'bot']}, {'model_ids': ['cfr-v1', 'cfr-v1']},
                                  {'model_ids': ['cfr-v1'], 'mode': 'sng'}])
def test_cfr_rooms_are_heads_up_cash_only(client, body):
    c, _ = client
    response = c.post('/api/rooms', json=body)
    assert response.status_code == 422 and 'CFR' in response.json()['detail']


def wait(c, rid):
    for _ in range(400):
        data = c.get(f'/api/rooms/{rid}/state').json()
        if data['run']['status'] not in ('running', 'ready'):
            return data
        time.sleep(0.01)
    pytest.fail('room did not reach a human decision or hand boundary')


@pytest.mark.parametrize('policy', ['cfr-v1', 'cfr-v2', 'cfr-v2-adapt', 'cfr-v3'])
def test_human_plays_full_hands_against_cfr_without_seeing_hidden_cards(client, policy):
    c, app = client
    created = c.post('/api/rooms', json={'model_ids': [policy], 'max_hands': 4, 'name': 'CFR test'})
    assert created.status_code == 200
    rid = created.json()['run']['id']
    run = app.state.store.run(rid)
    assert run['config']['cash_reset_at'] == 40000 and run['config']['entries'][1]['provider'] == 'local_cfr'
    assert c.post(f'/api/runs/{rid}/start').status_code == 200
    human_turns = 0
    for _ in range(200):
        data = wait(c, rid)
        status = data['run']['status']
        if status == 'complete':
            break
        snapshot = data['record']['events'][-1]['snapshot']
        opponent = next(s for s in snapshot['seats'] if s['id'] != 'human-player')
        if not snapshot['complete']:
            assert opponent['cards'] == opponent['public_cards']
            assert all(card == '??' for card in opponent['cards'])
        if status == 'waiting_human':
            legal = {a['id']: a for a in snapshot['legal_actions']}
            choice = 'check' if 'check' in legal else 'call' if 'call' in legal else next(iter(legal))
            response = c.post(f'/api/rooms/{rid}/action', json={
                'hand_number': data['run']['active_hand'], 'action_count': data['action_count'], 'action_id': choice})
            assert response.status_code == 200, response.text
            human_turns += 1
        elif status == 'waiting_next_hand':
            assert c.post(f'/api/runs/{rid}/start').status_code == 200
        else:
            pytest.fail(f'unexpected status {status}: {data["run"]["message"]}')
    assert data['run']['hands_played'] == 4 and human_turns > 0
    decisions = [a.get('decision') for h in app.state.store.hands(rid) for a in h['actions'] if a['player'] != 'human-player']
    assert decisions and all(d['provider'] == 'local_cfr' and d['cost_cny_estimate'] == 0 for d in decisions)
    # Replaying a completed hand reproduces it exactly from the recorded actions.
    record = app.state.store.hand(rid, 1)
    assert Hand.restore(record).record()['events'] == record['events']

    history = c.get(f'/api/rooms/{rid}/history').json()
    assert history['completed_hands'] == 4 and len(history['hands']) == 4
    stats = history['stats']
    assert set(stats) == {'human-player', 'opponent-1'}
    assert stats['human-player']['net_chips'] + stats['opponent-1']['net_chips'] == 0
    assert stats['human-player']['hands'] == 4 and stats['human-player']['bb_per_100'] is not None
    raw = {h['spec']['number']: h for h in app.state.store.hands(rid)}
    for summary in history['hands']:
        assert 'decision' not in json.dumps(summary)
        opponent = next(p for p in summary['players'] if p['id'] == 'opponent-1')
        shown = raw[summary['number']]['events'][-1]['snapshot']
        real = next(s for s in shown['seats'] if s['id'] == 'opponent-1')
        assert opponent['cards'] == real['public_cards']  # only what was shown at showdown
        me = next(p for p in summary['players'] if p['id'] == 'human-player')
        assert '??' not in me['cards']
    other = TestClient(app)
    assert other.get(f'/api/rooms/{rid}/history').status_code in (401, 403)


def test_local_decision_is_deterministic_per_decision_id():
    entry = next(e for e in local_entries() if e.id == 'cfr-v1')
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 5, chip_unit=50)
    request = hand.request(entry.model)
    first = asyncio.run(decide(entry, request, 'room:1:0', 'h'))
    assert all(asyncio.run(decide(entry, request, 'room:1:0', 'h'))['answers'] == first['answers'] for _ in range(5))
    assert first['answers']['action']['choice'] in request['questions']['action']['criteria']


def test_aggressive_session_ledgers_agree_across_cash_resets(client):
    """Room standings, per-hand PokerKit payoffs and the history panel must agree."""
    import random
    c, app = client
    rid = c.post('/api/rooms', json={'model_ids': ['cfr-v2'], 'max_hands': 49}).json()['run']['id']
    c.post(f'/api/runs/{rid}/start')
    rng = random.Random(1)
    for _ in range(4000):
        data = c.get(f'/api/rooms/{rid}/state').json()
        status = data['run']['status']
        if status in ('running', 'ready'):
            time.sleep(0.002)
            continue
        if status == 'complete':
            break
        if status == 'waiting_next_hand':
            c.post(f'/api/runs/{rid}/start')
            continue
        legal = data['record']['events'][-1]['snapshot']['legal_actions']
        raises = [a for a in legal if a['kind'] == 'raise']
        action = rng.choice(raises) if raises and rng.random() < 0.85 else next(
            (a for a in legal if a['kind'] in ('call', 'check')), legal[0])
        c.post(f'/api/rooms/{rid}/action', json={'hand_number': data['run']['active_hand'],
                                                 'action_count': data['action_count'], 'action_id': action['id']})
    run = app.state.store.run(rid)
    assert run['hands_played'] == 49
    standings = {s['id']: s['stack'] + s['reserve'] - s['initial'] for s in run['seats']}
    payoffs = {}
    for record in app.state.store.hands(rid):
        for seat in record['events'][-1]['snapshot']['seats']:
            payoffs[seat['id']] = payoffs.get(seat['id'], 0) + seat['payoff']
    history = c.get(f'/api/rooms/{rid}/history?limit=200').json()['stats']
    assert standings == payoffs == {k: v['net_chips'] for k, v in history.items()}
    for row in history.values():
        assert row['won_chips'] - row['lost_chips'] == row['net_chips']
    assert any(e['type'] == 'cash_reset' for e in run['events'])


def test_room_audit_reads_owner_export_without_changing_results(client):
    from pokerbench.room_audit import audit
    c, app = client
    rid = c.post('/api/rooms', json={'model_ids': ['cfr-v2'], 'max_hands': 6}).json()['run']['id']
    c.post(f'/api/runs/{rid}/start')
    for _ in range(2000):
        data = c.get(f'/api/rooms/{rid}/state').json()
        status = data['run']['status']
        if status in ('running', 'ready'):
            time.sleep(0.002)
            continue
        if status == 'complete':
            break
        if status == 'waiting_next_hand':
            c.post(f'/api/runs/{rid}/start')
            continue
        legal = data['record']['events'][-1]['snapshot']['legal_actions']
        action = next((a for a in legal if a['kind'] == 'raise'), legal[0])
        c.post(f'/api/rooms/{rid}/action', json={'hand_number': data['run']['active_hand'],
                                                 'action_count': data['action_count'], 'action_id': action['id']})
    before = json.dumps([h['events'] for h in app.state.store.hands(rid)])
    export = c.get(f'/api/rooms/{rid}/history?limit=200').json()
    report = audit(export)
    assert report['hands'] == 6
    human, bot = report['players']['human-player'], report['players']['opponent-1']
    # The human raises whenever a raise is offered (none is left facing an all-in).
    assert human['pfr'] >= 0.5 and human['vpip'] >= human['pfr'] and human['net_bb'] + bot['net_bb'] == 0
    assert set(bot['streets']) <= {'preflop', 'flop', 'turn', 'river'}
    assert json.dumps([h['events'] for h in app.state.store.hands(rid)]) == before


def test_adaptive_room_entry_uses_public_statistics_from_the_request():
    entries = {e.id: e for e in local_entries()}
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 21, chip_unit=50)
    hand.apply('raise_to_300')
    folds = {}
    for name in ('cfr-v2', 'cfr-v2-adapt'):
        request = hand.request(entries[name].model, {'a': {'hands': 200, 'vpip': 190, 'pfr': 180, 'three_bet': 0}})
        hero = next(s for s in request['state']['seats'] if s['id'] == request['state']['actor'])
        hero['cards'] = ['9d', '6c']
        folds[name] = sum(asyncio.run(decide(entries[name], request, f'r:1:{i}', 'h'))['answers']['action']['choice'] == 'fold'
                          for i in range(40))
    assert folds['cfr-v2'] >= 30 and folds['cfr-v2-adapt'] <= 8
