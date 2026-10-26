"""Mission 6: CFR against aggressive and passive profiles, then V2 versus V3.

Baseline protocol (fixed before running it): V2 300k against hyper, tag,
station and equity on three new (deck, policy) seed pairs, 10,000 hands each,
strictly alternating button. Metrics: net bb/100 at 0/2/5/7 % rake (cap 3 BB,
no flop no drop), 95 % CI on two-hand blocks, per seed, per position, action
frequencies per street and off-tree fallback rate. The V2/V3 comparison uses
its own fresh seeds, declared in ``FINAL_SEEDS`` before it is run.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics

from .benchmark import Config, performance
from .holdem_abstraction import resolve_policy
from .mission3 import read_rows, rerake, run_job, write_json
from .mission4 import audit_cfr

OPPONENTS = ("hyper", "tag", "station", "equity")
BASELINE_POLICIES = {"v2": "artifacts/mission5/policy-v2-72001-300000.json.gz"}
BASELINE_SEEDS = ((101001, 111001), (101002, 111002), (101003, 111003))
FINAL_SEEDS = ((121001, 131001), (121002, 131002), (121003, 131003))
MAIN_HANDS = 10000
RAKE_RATES = (0, 2, 5, 7)
STREETS = ("preflop", "flop", "turn", "river")


def jobs(policies, seeds, opponents=OPPONENTS, public_stats=False):
    for deck, seed in seeds:
        for opponent in opponents:
            for name, path in policies.items():
                yield f"{name}-v-{opponent}-{deck}", Config(hands=MAIN_HANDS, agent_a="cfr", agent_b=opponent,
                                                            deck_seed=deck, policy_seed=seed, measure_time=True,
                                                            cfr_policy=path, cfr_adaptive=name.endswith("+adapt"),
                                                            public_stats=public_stats)


def run_suite(root: Path, workers: int, policies, seeds, opponents=OPPONENTS, public_stats=False):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    plan = list(jobs(policies, seeds, opponents, public_stats))
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root / "plan.json", {"workers": workers, "jobs": {n: asdict(c) for n, c in plan},
                                    "policy_sha256": {k: hashlib.sha256(resolve_policy(p).read_bytes()).hexdigest()
                                                      for k, p in policies.items()},
                                    "rake_rates": list(RAKE_RATES), "rake_cap_bb": 3})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run_job, (n, c, root)) for n, c in plan]):
            name, summary, timing = future.result()
            print(json.dumps({"finished": name, "hands": summary["completed_hands"],
                              "cpu_seconds": timing["cpu_seconds"]}), flush=True)


def frequencies(folder: Path, seat="a") -> dict:
    """Action shares per street, preflop VPIP/PFR and blind defense for one seat."""
    streets = {s: Counter() for s in STREETS}
    hands = defaultdict(Counter)
    with (folder / "decisions.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            if e["actor"] != seat:
                continue
            obs = e["observation"]
            action = next(a for a in obs["legal_actions"] if a["id"] == e["action"])
            row = streets[obs["street"]]
            row["decisions"] += 1
            row[action["kind"]] += 1
            if obs["to_call"] and obs["street"] != "preflop":
                row["facing"] += 1
                row["fold_facing"] += action["kind"] == "fold"
                row["raise_facing"] += action["kind"] == "raise"
            if obs["street"] == "preflop":
                h = hands[e["hand"]]
                h["acted"] = 1
                h["vpip"] |= action["kind"] in ("call", "raise") and action["pay"] > 0
                h["pfr"] |= action["kind"] == "raise"
                hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
                if hero["position"] == "BB" and obs["to_call"] > 0 and not h["bb_seen"]:
                    h["bb_seen"] = 1
                    h["bb_fold"] = action["kind"] == "fold"
    acted = [h for h in hands.values() if h["acted"]]
    bb = [h for h in acted if h["bb_seen"]]
    result = {"vpip": sum(h["vpip"] for h in acted) / max(1, len(acted)),
              "pfr": sum(h["pfr"] for h in acted) / max(1, len(acted)),
              "bb_fold_vs_raise": sum(h["bb_fold"] for h in bb) / len(bb) if bb else None, "streets": {}}
    for street, row in streets.items():
        n = row["decisions"]
        if n:
            result["streets"][street] = {k: row[k] / n for k in ("fold", "check", "call", "raise")} | {
                "decisions": n, "fold_facing_bet": row["fold_facing"] / row["facing"] if row["facing"] else None,
                "raise_facing_bet": row["raise_facing"] / row["facing"] if row["facing"] else None}
    return result


def _audit(folder):
    return asyncio.run(audit_cfr(folder)), frequencies(folder)


def analyze(root: Path, output: Path, policies, seeds, opponents=OPPONENTS, comparisons=(), public_stats=False,
            workers: int = 1) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    rows_by = defaultdict(dict)
    runs = []
    plan = list(jobs(policies, seeds, opponents, public_stats))
    # Replaying every CFR decision dominates the cost; audit runs in parallel.
    with ProcessPoolExecutor(max_workers=workers) as pool:
        audits = dict(zip((n for n, _ in plan), pool.map(_audit, [root / n for n, _ in plan])))
    for name, cfg in plan:
        folder = root / name
        m = json.loads((folder / "experiment.json").read_text())
        if m["status"] != "complete" or Config(**m["config"]) != cfg:
            raise ValueError(f"Missing or incompatible experiment {name}")
        rows = read_rows(folder)
        if len(rows) != cfg.hands or [r["button"] for r in rows] != ["a", "b"] * (cfg.hands // 2):
            raise ValueError("Incomplete or unbalanced experiment")
        for row in rows:
            if rerake(row, 5) != {s: row[f"{s}_net_chips"] for s in ("a", "b")}:
                raise ValueError("Independent rake mismatch")
        policy = name.split(f"-v-{cfg.agent_b}-")[0]
        rows_by[(policy, cfg.agent_b)][cfg.deck_seed] = rows
        timing = m["decision_bridge_timing"]
        audit, freq = audits[name]
        runs.append({"name": name, "policy": policy, "opponent": cfg.agent_b, "audit": audit, "frequencies": freq,
                     "cfr_ms_per_decision": 1000 * timing["a"]["cpu_seconds"] / timing["a"]["decisions"]})
    decks = [d for d, _ in seeds]
    results = []
    for (policy, opponent), by_seed in rows_by.items():
        pooled = [r for d in decks for r in by_seed[d]]
        entry = {"policy": policy, "opponent": opponent, "hands": len(pooled), "rake": {}}
        for rate in RAKE_RATES:
            entry["rake"][str(rate)] = performance([r["a"] for r in (rerake(x, rate) for x in pooled)])
        entry["seed_net_bb100"] = [performance([r["a_net_chips"] for r in by_seed[d]])["bb_per_100"] for d in decks]
        entry["sd_seed_means_bb100"] = statistics.stdev(entry["seed_net_bb100"])
        # Button alternates: even hand indices put seat a on the button.
        entry["position_net_bb100"] = {pos: 100 * sum(r["a_net_chips"] for r in pooled if (r["button"] == "a") == (pos == "BTN"))
                                       / 100 / (len(pooled) / 2) for pos in ("BTN", "BB")}
        low, high = entry["rake"]["5"]["ci95_bb_per_100"]
        entry["verdict"] = "beats" if low > 0 and all(v > 0 for v in entry["seed_net_bb100"]) else "loses" if high < 0 else "inconclusive"
        entry["fallback_rate"] = statistics.mean(r["audit"]["fallback_rate"] for r in runs if r["policy"] == policy and r["opponent"] == opponent)
        results.append(entry)
    paired = []
    for new, old in comparisons:
        for opponent in opponents:
            diffs = [a["a_net_chips"] - b["a_net_chips"] for d in decks
                     for a, b in zip(rows_by[(new, opponent)][d], rows_by[(old, opponent)][d])]
            metrics = performance(diffs)
            low, high = metrics["ci95_bb_per_100"]
            paired.append({"comparison": f"{new} - {old}", "opponent": opponent, "difference": metrics,
                           "verdict": "better" if low > 0 else "worse" if high < 0 else "inconclusive"})
    result = {"results": results, "paired": paired, "runs": runs, "rake_cap_bb": 3, "no_flop_no_drop": True,
              "ci_method": "normal 95% on independent two-hand block means; paired per-hand differences on identical deals"}
    write_json(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("run", "analyze"):
        s = sub.add_parser(command)
        s.add_argument("--plan", choices=("baseline", "final"), required=True)
        if command == "run":
            s.add_argument("--output", type=Path, required=True); s.add_argument("--workers", type=int, default=4)
        else:
            s.add_argument("source", type=Path); s.add_argument("--output", type=Path, required=True)
            s.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    policies, seeds, comparisons = (BASELINE_POLICIES, BASELINE_SEEDS, ()) if a.plan == "baseline" else (FINAL_POLICIES, FINAL_SEEDS, FINAL_COMPARISONS)
    final = a.plan == "final"
    if a.command == "run":
        run_suite(a.output, a.workers, policies, seeds, public_stats=final)
    else:
        analyze(a.source, a.output, policies, seeds, comparisons=comparisons, public_stats=final, workers=a.workers)


# Final protocol, fixed before V3 training ends and before any final hand is played:
# V2 and V3 (seed 73001, 300k iterations), each plain and with the public-stats
# adaptation overlay ("+adapt"); V3 seed 73002 measures training-seed variance.
# All final jobs expose public statistics so the overlay can see them (plain
# CFR agents ignore them). Verdicts: as in the baseline; a paired difference is
# "better" only if its 95 % CI is entirely above zero.
FINAL_POLICIES = {
    "v2": "artifacts/mission5/policy-v2-72001-300000.json.gz",
    "v2+adapt": "artifacts/mission5/policy-v2-72001-300000.json.gz",
    "v3": "artifacts/mission6/policy-v3-73001-300000.json.gz",
    "v3+adapt": "artifacts/mission6/policy-v3-73001-300000.json.gz",
    "v3-seed2": "artifacts/mission6/policy-v3-73002-300000.json.gz",
}
FINAL_COMPARISONS = (("v3", "v2"), ("v2+adapt", "v2"), ("v3+adapt", "v3"), ("v3+adapt", "v2"), ("v3-seed2", "v3"))

if __name__ == "__main__":
    main()
