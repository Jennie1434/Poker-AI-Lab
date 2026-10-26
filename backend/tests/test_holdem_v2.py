import random

import pytest

from pokerbench.cfr import CFRTrainer
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import STACK, export_policy, load_policy
from pokerbench.holdem_v2 import AbstractionV2, CFRAgentV2, HoldemAbstractGameV2, agent_for

FAST = {"preflop_table_samples": 200, "postflop_samples": 8}


@pytest.fixture(scope="module")
def abstraction():
    return AbstractionV2(FAST)


def policy_for(abstraction, trainer=None):
    return {"game": HoldemAbstractGameV2.name, "abstraction": abstraction.describe(),
            "actions": dict(trainer.actions) if trainer else {},
            "strategy": {k: list(v.values()) for k, v in trainer.average_strategy().items()} if trainer else {}}


def test_v2_tree_matches_pokerkit_chip_for_chip_with_all_sizes(abstraction):
    game, rng = HoldemAbstractGameV2(abstraction), random.Random(23)
    agent = CFRAgentV2(1, policy_for(abstraction))
    used = set()
    for number in range(250):
        button = number % 2
        hand = Hand([{"id": "a", "stack": STACK}, {"id": "b", "stack": STACK}], button, (50, 100, 0), 700 + number, chip_unit=50)
        seat_of = {0: "ab"[button], 1: "ab"[1 - button]}
        h = game.sample_chance(None, rng)
        while not game.is_terminal(h):
            obs = hand.observation()
            player, street, _, history, raises, sized = agent.abstract_view(obs)
            # Real raise sizes are translated back to exactly the abstract history.
            assert (player, street, history, raises, sized) == (h.player, h.street, h.history, h.raises, h.pot_raises)
            assert agent.legal == game.actions(h)
            assert agent.key(player, street, h.deal[0][h.player][h.street], history) == game.infoset(h)
            # Bias toward sized raises so every size and depth cap is exercised.
            actions = game.actions(h)
            sized_options = [a for a in actions if a in "hro"]
            abstract = rng.choice(sized_options) if sized_options and rng.random() < 0.6 else rng.choice(actions)
            used.add((h.street > 0, abstract))
            hand.apply(agent.map_action(abstract, obs))
            h = game.child(h, abstract)
            assert [hand.committed[seat_of[p]] for p in (0, 1)] == h.committed
        assert not hand.state.status
    assert {(False, "h"), (False, "r"), (True, "h"), (True, "r"), (True, "o"), (True, "a")} <= used
    assert (False, "o") not in used  # 1.5x pot is postflop only


def test_v2_draw_buckets_and_ranges(abstraction):
    rng = random.Random(4)
    flush_draw = abstraction.bucket(["Ah", "Kh"], ["2h", "9h", "3c"], rng)
    no_draw = abstraction.bucket(["Ad", "Kc"], ["2h", "9s", "3c"], rng)
    assert flush_draw % 2 == 1 and no_draw % 2 == 0
    assert 0 <= abstraction.bucket(["Ah", "Kh"], ["2h", "9h", "3c", "4s", "Ts"], rng) < 8
    assert all(0 <= abstraction.bucket(*random.Random(i).sample([["Ah", "Kh"], ["2c", "7d"]], 1), ["2h", "9h", "3c", "4s"], rng) < 12 for i in range(5))


def test_v2_trains_exports_and_plays_without_hidden_information(tmp_path, abstraction):
    import asyncio
    from copy import deepcopy
    trainer = CFRTrainer(HoldemAbstractGameV2(abstraction), "external", seed=3).train(60)
    assert any(set("hro") & set(actions) for actions in trainer.actions.values())
    path = tmp_path / "v2.json.gz"
    export_policy(trainer, abstraction, path, {})
    policy = load_policy(path)
    assert policy["game"] == HoldemAbstractGameV2.name and isinstance(agent_for(0, policy), CFRAgentV2)
    hand = Hand([{"id": "a", "stack": STACK}, {"id": "b", "stack": STACK}], 0, (50, 100, 0), 8, chip_unit=50)
    obs = hand.observation()
    changed = deepcopy(obs)
    next(s for s in changed["seats"] if s["id"] != changed["actor"])["cards"] = ["As", "Ad"]
    for seed in range(10):
        assert asyncio.run(agent_for(seed, policy).choose_action(obs)) == asyncio.run(agent_for(seed, policy).choose_action(changed))


def test_v1_policy_still_selects_v1_agent():
    from pokerbench.holdem_abstraction import CFRAgent, cached_policy
    policy = cached_policy("artifacts/mission4/policy-71001-200000.json.gz")
    agent = agent_for(0, policy)
    assert type(agent) is CFRAgent
