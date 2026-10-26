import asyncio

import pytest
from fastapi.testclient import TestClient

from pokerbench.config import Settings
from pokerbench.spectator import Spectator


@pytest.fixture
def client(tmp_path):
    import pokerbench.api as api_module
    app = api_module.create_app(Settings(_env_file=None, pokerbench_data_dir=str(tmp_path / 'data')))
    with TestClient(app) as c:
        assert c.post('/api/auth/register', json={'id': 'watcher', 'password': 'test-password'}).status_code == 200
        yield c, app


def test_spectator_plays_cfr_against_tag_hand_by_hand(client):
    c, app = client
    agents = {a['id'] for a in c.get('/api/spectate/agents').json()}
    assert {'cfr-v1', 'cfr-v1-20k', 'cfr-v2', 'cfr-v2-adapt', 'cfr-v3', 'tag', 'hyper', 'station', 'equity', 'heuristic', 'random'} <= agents
    session = c.post('/api/spectate', json={'agent_a': 'cfr-v1', 'agent_b': 'tag'}).json()
    assert session['names'] == {'a': 'CFR V1 · 200k', 'b': 'TightAggressive'} and session['hands_played'] == 0
    assert c.get(f"/api/spectate/{session['id']}/hands/2").status_code == 422  # cannot skip ahead
    total = 0
    for number in range(1, 6):
        data = c.get(f"/api/spectate/{session['id']}/hands/{number}").json()
        hand = data['hand']
        final = hand['events'][-1]['snapshot']
        assert final['complete'] and sum(hand['payoffs'].values()) == 0
        assert final['button'] == (number - 1) % 2  # strictly alternating button
        assert all('decision' not in (e.get('action') or {}) for e in hand['events'])
        total += hand['payoffs']['a']
    assert data['session']['hands_played'] == 5 and data['session']['stats']['a']['net_chips'] == total
    # Re-reading a dealt hand returns the same record without playing again.
    again = c.get(f"/api/spectate/{session['id']}/hands/3").json()
    assert again['session']['hands_played'] == 5
    other = TestClient(app)
    assert other.get(f"/api/spectate/{session['id']}/hands/1").status_code == 401
    assert other.post('/api/spectate', json={'agent_a': 'cfr-v1', 'agent_b': 'tag'}).status_code == 401


def test_spectator_sessions_are_private_validated_and_capped():
    spectator = Spectator()
    with pytest.raises(ValueError):
        spectator.create('u1', 'cfr-v1', 'unknown')
    first = spectator.create('u1', 'random', 'heuristic')
    with pytest.raises(KeyError):
        spectator.get('u2', first['id'])
    for _ in range(6):
        spectator.create('u1', 'random', 'random')
    assert sum(s['owner'] == 'u1' for s in spectator.sessions.values()) == 5
    assert first['id'] not in spectator.sessions
    same = spectator.create('u1', 'cfr-v1', 'cfr-v1')
    assert same['names'] == {'a': 'CFR V1 · 200k (A)', 'b': 'CFR V1 · 200k (B)'}


def test_concurrent_requests_play_each_hand_once():
    spectator = Spectator()
    session = spectator.create('u1', 'random', 'heuristic')

    async def both():
        return await asyncio.gather(*(spectator.hand('u1', session['id'], 1) for _ in range(3)))
    results = asyncio.run(both())
    assert len(spectator.sessions[session['id']]['hands']) == 1
    assert len({id(r['hand']) for r in results}) == 1
