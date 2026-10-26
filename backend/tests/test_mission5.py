import asyncio

from pokerbench.benchmark import experiment
from pokerbench.cfr import CFRTrainer
from pokerbench.holdem_abstraction import export_policy
from pokerbench.holdem_v2 import game_for
import pokerbench.mission5 as m5

FAST = {"preflop_table_samples": 200, "postflop_samples": 8}


def test_preregistered_plan_new_seeds_identical_deals():
    plan = list(m5.jobs())
    assert len(plan) == 12 and sum(c.hands for _, c in plan) == 120000
    assert all(c.agent_b == "tag" and c.agent_a == "cfr" for _, c in plan)
    earlier = {1234, 5678, 31001, 31002, 31003, 41001, 41002, 41003, 51001, 51002, 51003, 61001, 61002, 61003, 71001, 72001, 72002}
    assert not earlier & {s for pair in m5.EVAL_SEEDS for s in pair}
    by_seed = {}
    for _, c in plan:
        by_seed.setdefault(c.deck_seed, set()).add(c.policy_seed)
    assert all(len(v) == 1 for v in by_seed.values())  # every policy sees the same deals and policy seeds


def test_mission5_analysis_pairs_policies_and_audits(tmp_path, monkeypatch):
    policies = {}
    for name, version in (("v1", 1), ("v2", 2), ("v2-300k", 2), ("v2-seed2", 2)):
        abstraction, game = game_for(version, FAST)
        trainer = CFRTrainer(game, "external", seed=len(name)).train(20)
        path = tmp_path / f"{name}.json.gz"
        export_policy(trainer, abstraction, path, {})
        policies[name] = str(path)
    monkeypatch.setattr(m5, "MAIN_HANDS", 6)
    root = tmp_path / "suite"
    for name, cfg in m5.jobs(policies):
        asyncio.run(experiment(cfg, root / name))
    result = m5.analyze(root, tmp_path / "analysis.json", policies)
    assert set(result["policies"]) == set(policies)
    assert all(p["hands"] == 18 and p["verdict_vs_tag"] in ("beats", "loses", "inconclusive") for p in result["policies"].values())
    assert [p["comparison"] for p in result["paired"]] == ["v2 - v1", "v2-300k - v2", "v2-seed2 - v2"]
    assert all(r["audit"]["decisions"] > 0 for r in result["runs"])
