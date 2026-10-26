import random

import pytest

from pokerbench.cfr import CFRTrainer
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import STACK, export_policy, hand_class, load_policy
from pokerbench.holdem_v2 import agent_for
from pokerbench.holdem_v3 import AbstractionV3, CFRAgentV3, HoldemAbstractGameV3

FAST = {"preflop_table_samples": 200, "postflop_samples": 8}


@pytest.fixture(scope="module")
def abstraction():
    return AbstractionV3(FAST)


def test_v3_tree_matches_pokerkit_after_real_export(tmp_path, abstraction):
    game, rng = HoldemAbstractGameV3(abstraction), random.Random(31)
    trainer = CFRTrainer(game, "external", seed=2).train(15)
    export_policy(trainer, abstraction, tmp_path / "v3.json.gz", {})
    agent = agent_for(0, load_policy(tmp_path / "v3.json.gz"))
    assert isinstance(agent, CFRAgentV3)
    used, deepest = set(), 0
    for number in range(250):
        button = number % 2
        hand = Hand([{"id": "a", "stack": STACK}, {"id": "b", "stack": STACK}], button, (50, 100, 0), 500 + number, chip_unit=50)
        seat_of = {0: "ab"[button], 1: "ab"[1 - button]}
        h = game.sample_chance(None, rng)
        while not game.is_terminal(h):
            obs = hand.observation()
            player, street, _, history, raises, sized = agent.abstract_view(obs)
            assert (player, street, history, raises, sized) == (h.player, h.street, h.history, h.raises, h.pot_raises)
            assert agent.legal == game.actions(h)
            hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
            assert agent.tier == abstraction.tier(abstraction.preflop[hand_class(hero["cards"])])
            # The sampled abstract deal is independent of the real cards: align its tier.
            agent.tier = abstraction.tier(h.deal[0][h.player][0])
            assert agent.key(player, street, h.deal[0][h.player][h.street], history) == game.infoset(h)
            actions = game.actions(h)
            sized_options = [a for a in actions if a in "hro"]
            abstract = rng.choice(sized_options) if sized_options and rng.random() < 0.7 else rng.choice(actions)
            used.add((h.raises > 0, abstract))
            deepest = max(deepest, h.raises)
            hand.apply(agent.map_action(abstract, obs))
            h = game.child(h, abstract)
            assert [hand.committed[seat_of[p]] for p in (0, 1)] == h.committed
        assert not hand.state.status
    assert {(True, "h"), (True, "r"), (False, "o")} <= used  # half-pot re-raises exist in V3
    assert deepest == 3  # a fourth raise (all-in) is offered after three


def test_v3_keys_carry_preflop_tier_and_v2_is_unchanged(abstraction):
    game, rng = HoldemAbstractGameV3(abstraction), random.Random(2)
    h = game.sample_chance(None, rng)
    assert "t" not in game.infoset(h).split(":")[0]
    while h.street == 0 and not game.is_terminal(h):
        h = game.child(h, "c")
    if not game.is_terminal(h):
        assert f"t{abstraction.tier(h.deal[0][h.player][0])}:" in game.infoset(h)
    from pokerbench.holdem_v2 import AbstractionV2
    assert AbstractionV2(FAST).config["max_raises"] == 3 and "facing_sizes" not in AbstractionV2(FAST).config
