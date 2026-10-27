import asyncio
from copy import deepcopy

import pytest

from pokerbench.adaptive import AdaptiveCFRAgent, adjust, opponent_pfr
from pokerbench.benchmark import Config, experiment
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import cached_policy
from pokerbench.holdem_v2 import agent_for

V2 = 'artifacts/mission5/policy-v2-72001-300000.json.gz'


def test_adjust_moves_folds_to_calls_only_with_enough_equity():
    out = adjust(['f', 'c', 'r'], [0.9, 0.1, 0.0], 1.0, equity=0.50, price=0.33)
    assert out[0] == pytest.approx(0.0) and out[1] == pytest.approx(1.0)
    same = adjust(['f', 'c', 'r'], [0.9, 0.1, 0.0], 1.0, equity=0.30, price=0.33)
    assert same == pytest.approx([0.9, 0.1, 0.0])
    strong = adjust(['f', 'c', 'r'], [0.2, 0.8, 0.0], 1.0, equity=0.9, price=0.3)
    assert strong[2] == pytest.approx(0.5) and sum(strong) == pytest.approx(1)
    weak_bluffs = adjust(['c', 'h', 'r', 'a'], [0.2, 0.4, 0.2, 0.2], 1.0, equity=0.2, price=0)
    assert weak_bluffs[0] == pytest.approx(0.6) and sum(weak_bluffs) == pytest.approx(1)


def observation_with_stats(pfr, hands):
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 21, chip_unit=50)
    hand.apply('raise_to_300')
    return hand.observation({'a': {'hands': hands, 'vpip': hands, 'pfr': pfr, 'three_bet': 0}})


def test_public_pfr_is_shrunk_and_the_overlay_is_inert_without_evidence():
    assert opponent_pfr(observation_with_stats(0, 0))[0] == pytest.approx(0.25)
    assert opponent_pfr(observation_with_stats(90, 100))[0] == pytest.approx((90 + 5) / 120)
    policy = cached_policy(V2)
    quiet = observation_with_stats(2, 10)
    for seed in range(20):
        base = asyncio.run(agent_for(seed, policy).choose_action(quiet))
        assert asyncio.run(AdaptiveCFRAgent(agent_for(seed, policy)).choose_action(quiet)) == base


def test_big_blind_defends_more_against_a_hyper_aggressive_opener():
    policy = cached_policy(V2)
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 21, chip_unit=50)
    hand.apply('raise_to_300')
    folds = {}
    for label, stats in (('unknown', None), ('maniac', {'a': {'hands': 200, 'vpip': 190, 'pfr': 180, 'three_bet': 0}})):
        obs = hand.observation(stats)
        hero = next(s for s in obs['seats'] if s['id'] == obs['actor'])
        hero['cards'] = ['9d', '6c']  # a weak hand V2 folds versus a 3 BB open
        folds[label] = sum(asyncio.run(AdaptiveCFRAgent(agent_for(seed, policy)).choose_action(obs)) == 'fold'
                           for seed in range(60))
    assert folds['unknown'] >= 50 and folds['maniac'] <= 10


def test_adaptive_agent_ignores_hidden_cards():
    policy = cached_policy(V2)
    obs = observation_with_stats(180, 200)
    changed = deepcopy(obs)
    next(s for s in changed['seats'] if s['id'] != changed['actor'])['cards'] = ['As', 'Ad']
    for seed in range(10):
        assert asyncio.run(AdaptiveCFRAgent(agent_for(seed, policy)).choose_action(obs)) == \
               asyncio.run(AdaptiveCFRAgent(agent_for(seed, policy)).choose_action(changed))


def test_benchmark_public_stats_reach_agents_only_when_enabled(tmp_path):
    import json
    asyncio.run(experiment(Config(hands=6, agent_a='cfr', agent_b='hyper', cfr_policy=V2, cfr_adaptive=True,
                                  public_stats=True), tmp_path / 'on'))
    asyncio.run(experiment(Config(hands=6, agent_a='cfr', agent_b='hyper', cfr_policy=V2), tmp_path / 'off'))
    on = [json.loads(l)['observation']['public_statistics'] for l in (tmp_path / 'on' / 'decisions.jsonl').open()]
    off = [json.loads(l)['observation']['public_statistics'] for l in (tmp_path / 'off' / 'decisions.jsonl').open()]
    assert on[0] == {} and any(s for s in on) and not any(off)
    assert all(set(s) <= {'player_1', 'player_2'} for s in on)
