import asyncio
from copy import deepcopy
import json
import random

import pytest

from pokerbench.adaptive import AdaptiveCFRAgent
from pokerbench.allin import AllInAwareAgent, equity_against_top, shove_frequency
from pokerbench.benchmark import Config, experiment
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import cached_policy
from pokerbench.holdem_v2 import agent_for

V2 = 'artifacts/mission5/policy-v2-72001-300000.json.gz'


def shove_spot(stats, cards):
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 21, chip_unit=50)
    hand.apply('raise_to_20000')
    obs = hand.observation(stats)
    next(s for s in obs['seats'] if s['id'] == obs['actor'])['cards'] = cards
    return obs


def test_shove_frequency_uses_a_weak_prior():
    assert shove_frequency(shove_spot(None, ['As', 'Ad'])) == pytest.approx(0.05)
    assert shove_frequency(shove_spot({'a': {'hands': 10, 'all_in': 7}}, ['As', 'Ad'])) == pytest.approx(7.5 / 20)


def test_equity_against_a_top_range_is_lower_than_against_a_wide_one():
    pre = cached_policy(V2)['abstraction']['preflop_equity']
    rng = random.Random(1)
    tight = equity_against_top(['Kh', 'Qd'], 0.05, pre, rng, 2000)
    wide = equity_against_top(['Kh', 'Qd'], 1.0, pre, rng, 2000)
    assert tight < 0.40 < 0.55 < wide


def test_identical_to_v2_adaptive_against_rare_shovers():
    policy = cached_policy(V2)
    for stats in (None, {'a': {'hands': 200, 'vpip': 40, 'pfr': 35, 'three_bet': 0, 'all_in': 4}}):
        for cards in (['9d', '6c'], ['As', 'Kd'], ['7h', '2c']):
            obs = shove_spot(stats, cards)
            for seed in range(10):
                expected = asyncio.run(AdaptiveCFRAgent(agent_for(seed, policy)).choose_action(deepcopy(obs)))
                assert asyncio.run(AllInAwareAgent(agent_for(seed, policy)).choose_action(deepcopy(obs))) == expected


def test_calls_wider_against_a_frequent_shover_and_ignores_hidden_cards():
    policy = cached_policy(V2)
    stats = {'a': {'hands': 30, 'vpip': 28, 'pfr': 27, 'three_bet': 0, 'all_in': 21}}
    obs = shove_spot(stats, ['Kh', '9d'])  # ahead of a 70 % shoving range, behind a tight one
    assert asyncio.run(AllInAwareAgent(agent_for(0, policy)).choose_action(obs)) == 'call'
    changed = deepcopy(obs)
    next(s for s in changed['seats'] if s['id'] != changed['actor'])['cards'] = ['As', 'Ad']
    assert asyncio.run(AllInAwareAgent(agent_for(0, policy)).choose_action(changed)) == 'call'
    weak = shove_spot(stats, ['7h', '2c'])
    assert asyncio.run(AllInAwareAgent(agent_for(0, policy)).choose_action(weak)) == 'fold'


def test_all_in_counters_are_separate_and_opt_in(tmp_path):
    asyncio.run(experiment(Config(hands=6, agent_a='cfr', agent_b='shover', cfr_policy=V2, cfr_allin='top',
                                  public_stats=True, allin_stats=True), tmp_path / 'on'))
    asyncio.run(experiment(Config(hands=6, agent_a='cfr', agent_b='shover', cfr_policy=V2, cfr_adaptive=True,
                                  public_stats=True), tmp_path / 'off'))
    on = [json.loads(l)['observation']['public_statistics'] for l in (tmp_path / 'on' / 'decisions.jsonl').open()]
    off = [json.loads(l)['observation']['public_statistics'] for l in (tmp_path / 'off' / 'decisions.jsonl').open()]
    assert any('all_in' in row for s in on for row in s.values())
    assert not any('all_in' in row for s in off for row in s.values())


def test_rooms_send_all_in_counters_only_to_all_in_entries(monkeypatch):
    import pokerbench.local_agents as local
    from pokerbench.config import Entry
    from pokerbench.runner import Runner
    monkeypatch.setattr(local, 'ALLIN', {'cfr-v2-allin': 'top'})
    run = {'statistics': {'p': {'hands': 3, 'pfr': 3}}, 'allin_statistics': {'p': {'all_in': 2}}}
    runner = Runner.__new__(Runner)
    plain = Entry(id='x', name='x', provider='local_cfr', model='cfr-v2-adapt', key_env='', proxy=False)
    allin = Entry(id='y', name='y', provider='local_cfr', model='cfr-v2-allin', key_env='', proxy=False)
    llm = Entry(id='z', name='z', provider='systemone', key_env='', proxy=False)
    assert runner.public_stats(run, plain) is run['statistics'] and runner.public_stats(run, llm) is run['statistics']
    assert runner.public_stats(run, allin) == {'p': {'hands': 3, 'pfr': 3, 'all_in': 2}}


def test_range_hypotheses_change_the_calling_threshold():
    policy = cached_policy(V2)
    stats = {'a': {'hands': 30, 'vpip': 28, 'pfr': 27, 'three_bet': 0, 'all_in': 12}}  # f ~ 0.33
    obs = shove_spot(stats, ['Qh', '8d'])
    top = asyncio.run(AllInAwareAgent(agent_for(0, policy), 'top').choose_action(deepcopy(obs)))
    wide = asyncio.run(AllInAwareAgent(agent_for(0, policy), 'any').choose_action(deepcopy(obs)))
    assert (top, wide) == ('fold', 'call')
    with pytest.raises(ValueError):
        AllInAwareAgent(agent_for(0, policy), 'other')


def test_preregistered_allin_protocol_end_to_end(tmp_path, monkeypatch):
    import pokerbench.allin_eval as ev
    used = {101001, 101002, 101003, 111001, 111002, 111003, 121001, 121002, 121003, 131001, 131002, 131003,
            151001, 161001, 81001, 81002, 81003, 83001, 83002, 83003, 91001, 91002, 91003, 93001, 93002, 93003}
    assert not used & {s for pair in ev.SEEDS for s in pair}
    assert len(list(ev.jobs())) == 3 * 5 * 3
    monkeypatch.setattr(ev, 'MAIN_HANDS', 6)
    root = tmp_path / 'suite'
    for name, cfg in ev.jobs(opponents=('shover', 'tag')):
        asyncio.run(experiment(cfg, root / name))
    result = ev.analyze(root, tmp_path / 'a.json', opponents=('shover', 'tag'), workers=1)
    assert {d for d in result['decisions']} == {'allin-top', 'allin-any'}
    assert result['default'] in ('adapt', 'allin-top', 'allin-any')
    assert len(result['paired']) == 4 and all(r['hands'] == 18 for r in result['results'])
