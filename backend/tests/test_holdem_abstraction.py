import asyncio
from copy import deepcopy
import random

import pytest

from pokerbench.benchmark import Config, experiment
from pokerbench.cfr import CFRTrainer
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import (STACK, Abstraction, CFRAgent, HoldemAbstractGame, export_policy,
                                           hand_class, load_policy, preflop_buckets)

FAST = {"preflop_table_samples": 200, "postflop_samples": 8}


@pytest.fixture(scope="module")
def abstraction():
    return Abstraction(FAST)


def policy_for(abstraction, trainer=None):
    return {"abstraction": abstraction.describe(), "actions": dict(trainer.actions) if trainer else {},
            "strategy": {k: list(v.values()) for k, v in trainer.average_strategy().items()} if trainer else {}}


def test_hand_classes_and_balanced_preflop_buckets(abstraction):
    assert hand_class(["Kd", "As"]) == "AKo" and hand_class(["7h", "2h"]) == "72s" and hand_class(["9c", "9d"]) == "99"
    assert len(abstraction.preflop_equity) == 169
    buckets = abstraction.preflop
    assert buckets["AA"] == 7 and buckets["72o"] == 0
    combos = lambda k: 6 if len(k) == 2 else 4 if k[2] == "s" else 12
    sizes = [sum(combos(k) for k, b in buckets.items() if b == i) for i in range(8)]
    assert sum(sizes) == 1326 and max(sizes) - min(sizes) <= 2 * 12
    assert preflop_buckets({"AA": 0.8, "KK": 0.7, "AKo": 0.6}, 2) == {"AKo": 0, "KK": 0, "AA": 0}


def test_abstract_game_is_zero_sum_and_bounded(abstraction):
    game, rng = HoldemAbstractGame(abstraction), random.Random(3)
    for _ in range(300):
        h = game.sample_chance(None, rng)
        while not game.is_terminal(h):
            actions = game.actions(h)
            assert len(set(actions)) == len(actions) and "c" in actions
            h = game.child(h, rng.choice(actions))
            assert all(0 < c <= STACK for c in h.committed)
        assert abs(game.utility(h)) <= STACK / 100


def test_abstract_tree_matches_pokerkit_chip_for_chip(abstraction):
    """Every abstract action maps to a real legal action with identical chips and history."""
    game, rng = HoldemAbstractGame(abstraction), random.Random(17)
    agent = CFRAgent(1, policy_for(abstraction))
    for number in range(120):
        button = number % 2
        hand = Hand([{"id": "a", "stack": STACK}, {"id": "b", "stack": STACK}], button, (50, 100, 0), 900 + number, chip_unit=50)
        seat_of = {0: "ab"[button], 1: "ab"[1 - button]}
        h = game.sample_chance(None, rng)
        while not game.is_terminal(h):
            obs = hand.observation()
            player, street, _, history, raises, _ = agent.abstract_view(obs)
            assert (player, street, history, raises) == (h.player, h.street, h.history, h.raises)
            assert obs["actor"] == {"a": "player_1", "b": "player_2"}[seat_of[h.player]]
            abstract = rng.choice(game.actions(h))
            real = agent.map_action(abstract, obs)
            hand.apply(real)
            h = game.child(h, abstract)
            assert [hand.committed[seat_of[p]] for p in (0, 1)] == h.committed
        assert not hand.state.status


@pytest.mark.asyncio
async def test_agent_never_depends_on_hidden_cards_and_counts_fallbacks(abstraction):
    trainer = CFRTrainer(HoldemAbstractGame(abstraction), "external", seed=2).train(30)
    policy = policy_for(abstraction, trainer)
    hand = Hand([{"id": "a", "stack": STACK}, {"id": "b", "stack": STACK}], 0, (50, 100, 0), 42, chip_unit=50)
    obs = hand.observation()
    changed = deepcopy(obs)
    other = next(s for s in changed["seats"] if s["id"] != changed["actor"])
    assert other["cards"] == ["??", "??"]
    other["cards"] = ["As", "Ad"]
    for seed in range(20):
        assert await CFRAgent(seed, policy).choose_action(obs) == await CFRAgent(seed, policy).choose_action(changed)
    empty = CFRAgent(0, policy_for(abstraction))
    assert await empty.choose_action(obs) in {a["id"] for a in obs["legal_actions"]}
    assert empty.stats == {"decisions": 1, "fallback": 1}


def test_policy_file_roundtrip_and_tamper_detection(tmp_path, abstraction):
    import gzip, json
    trainer = CFRTrainer(HoldemAbstractGame(abstraction), "external", seed=2).train(20)
    path = tmp_path / "policy.json.gz"
    export_policy(trainer, abstraction, path, {"split": "train"})
    policy = load_policy(path)
    assert policy["iterations"] == 20 and policy["metadata"] == {"split": "train"}
    assert set(policy["strategy"]) == set(trainer.actions)
    with pytest.raises(FileExistsError):
        export_policy(trainer, abstraction, path, {})
    data = json.loads(gzip.open(path, "rt").read())
    key = next(iter(data["strategy"]))
    data["strategy"][key][0] = 1.0
    with gzip.open(path, "wt") as f:
        json.dump(data, f)
    with pytest.raises(ValueError, match="corrupted"):
        load_policy(path)


@pytest.mark.asyncio
async def test_cfr_agent_plays_full_benchmark_hands(tmp_path, abstraction):
    trainer = CFRTrainer(HoldemAbstractGame(abstraction), "external", seed=4).train(50)
    path = tmp_path / "policy.json.gz"
    export_policy(trainer, abstraction, path, {})
    with pytest.raises(ValueError, match="cfr-policy"):
        Config(hands=4, agent_a="cfr").validate()
    result = await experiment(Config(hands=20, agent_a="cfr", agent_b="tag", tag_samples=8, cfr_policy=str(path)),
                              tmp_path / "run")
    assert result["status"] == "complete" and result["summary"]["completed_hands"] == 20
    assert len(result["provenance"]["cfr_policy_sha256"]) == 64


def test_holdem_training_checkpoints_resume_identically(tmp_path):
    from pokerbench.cfr import load_checkpoint
    from pokerbench.selfplay import train_holdem
    config = {**FAST}
    full = train_holdem(40, tmp_path / "full", seed=9, every=20, config=config, snapshots=(20,))
    assert (tmp_path / "full" / "policy-20.json.gz").exists() and full["iterations"] == 40
    train_holdem(20, tmp_path / "half", seed=9, every=20, config=config)
    resumed = train_holdem(20, tmp_path / "resumed", seed=0, every=20, resume=tmp_path / "half" / "checkpoint.json")
    assert resumed["iterations"] == 40
    a, b = (load_checkpoint(tmp_path / d / "checkpoint.json") for d in ("full", "resumed"))
    assert a["regrets"] == b["regrets"] and a["strategy_sum"] == b["strategy_sum"] and a["rng_state"] == b["rng_state"]
    assert load_policy(tmp_path / "full" / "policy.json.gz")["strategy"] == load_policy(tmp_path / "resumed" / "policy.json.gz")["strategy"]
