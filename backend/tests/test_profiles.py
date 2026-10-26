import asyncio
from copy import deepcopy
from collections import defaultdict
import json

import pytest

from pokerbench.agents import CallingStationAgent, HyperAggressiveAgent
from pokerbench.benchmark import Config, experiment
from pokerbench.engine import Hand


def preflop_rates(folder, seat='a'):
    hands = defaultdict(lambda: {'vpip': False, 'pfr': False})
    for line in (folder / 'decisions.jsonl').open():
        e = json.loads(line)
        if e['actor'] != seat or e['observation']['street'] != 'preflop':
            continue
        a = next(x for x in e['observation']['legal_actions'] if x['id'] == e['action'])
        hands[e['hand']]['vpip'] |= a['kind'] in ('call', 'raise') and a['pay'] > 0
        hands[e['hand']]['pfr'] |= a['kind'] == 'raise'
    n = len(hands)
    return sum(h['vpip'] for h in hands.values()) / n, sum(h['pfr'] for h in hands.values()) / n


def test_hyper_aggressive_matches_observed_human_frequencies(tmp_path):
    asyncio.run(experiment(Config(hands=600, agent_a='hyper', agent_b='heuristic', deck_seed=3, policy_seed=4), tmp_path / 'r'))
    vpip, pfr = preflop_rates(tmp_path / 'r')
    assert 0.85 <= vpip <= 0.97 and 0.78 <= pfr <= 0.93


def test_calling_station_is_loose_and_passive(tmp_path):
    asyncio.run(experiment(Config(hands=200, agent_a='station', agent_b='hyper', deck_seed=3, policy_seed=4), tmp_path / 'r'))
    vpip, pfr = preflop_rates(tmp_path / 'r')
    assert vpip > 0.9 and pfr == 0


@pytest.mark.parametrize('cls', [HyperAggressiveAgent, CallingStationAgent])
def test_profiles_ignore_hidden_cards_and_are_reproducible(cls):
    hand = Hand([{'id': 'a', 'stack': 20000}, {'id': 'b', 'stack': 20000}], 0, (50, 100, 0), 9, chip_unit=50)
    hand.apply('call'); hand.apply('check')
    obs = hand.observation()
    changed = deepcopy(obs)
    next(s for s in changed['seats'] if s['id'] != changed['actor'])['cards'] = ['As', 'Ad']
    for seed in range(10):
        assert asyncio.run(cls(seed).choose_action(obs)) == asyncio.run(cls(seed).choose_action(changed))
