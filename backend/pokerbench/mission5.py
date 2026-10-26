"""Mission 5 preregistered comparison of CFR abstractions V1 and V2 against TAG.

Protocol fixed before any V2 evaluation hand is played (committed with this file):
- policies: V1 (Mission 4, seed 71001, 200,000 iterations); V2 seed 72001 at
  200,000 iterations (primary, equal iteration budget) and 300,000 iterations;
  V2 seed 72002 at 200,000 iterations (training-seed variance);
- opponent: TightAggressiveAgent (64 equity samples), the only reference agent
  that V1 did not beat;
- data: three new (deck, policy) seed pairs, never used in training or in any
  earlier mission; 10,000 hands each, strictly alternating button; every policy
  plays the same deals with the same policy seeds: 120,000 hands in total;
- metric: net bb/100 at 5 % rake (cap 3 BB, no flop no drop), also 0/2/7 %;
  normal 95 % CI on two-hand blocks; paired per-hand differences between policies;
- verdicts: "V2 improves on V1" only if the pooled paired difference CI (V2
  200k minus V1) is entirely above zero; a policy "beats TAG" only if its pooled
  CI is entirely above zero and all three seeds are positive;
- every experiment is reported; no early stopping or seed replacement.

Amendment, declared before running it: the preregistered run exposed a V2 bug
(exported policies sort config keys, so the agent's legal-action key order
differed from training and 37 % of V2 decisions fell back off-tree). After the
fix, the same plan is run again unchanged (``eval-fixed``) and confirmed on
fresh seeds (``CONFIRM_SEEDS``) with the same verdict rules. The original run
stays reported as is.
"""
import argparse
import asyncio
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics

from .benchmark import Config, performance
from .holdem_abstraction import resolve_policy
from .mission3 import read_rows, rerake, run_job, write_json
from .mission4 import audit_cfr

POLICIES = {
    "v1": "artifacts/mission4/policy-71001-200000.json.gz",
    "v2": "artifacts/mission5/policy-v2-72001-200000.json.gz",
    "v2-300k": "artifacts/mission5/policy-v2-72001-300000.json.gz",
    "v2-seed2": "artifacts/mission5/policy-v2-72002-200000.json.gz",
}
EVAL_SEEDS = ((81001, 91001), (81002, 91002), (81003, 91003))
CONFIRM_SEEDS = ((83001, 93001), (83002, 93002), (83003, 93003))
MAIN_HANDS = 10000
RAKE_RATES = (0, 2, 5, 7)
COMPARISONS = (("v2", "v1"), ("v2-300k", "v2"), ("v2-seed2", "v2"))


def jobs(policies=POLICIES, seeds=EVAL_SEEDS):
    for deck, seed in seeds:
        for name, path in policies.items():
            yield f"{name}-v-tag-{deck}", Config(hands=MAIN_HANDS, agent_a="cfr", agent_b="tag", deck_seed=deck,
                                                 policy_seed=seed, measure_time=True, cfr_policy=path)


def run_suite(root: Path, workers: int, policies=POLICIES, seeds=EVAL_SEEDS):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    plan = list(jobs(policies, seeds))
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root / "plan.json", {"workers": workers, "jobs": {n: asdict(c) for n, c in plan},
                                    "policy_sha256": {k: hashlib.sha256(resolve_policy(p).read_bytes()).hexdigest()
                                                      for k, p in policies.items()},
                                    "rake_rates": list(RAKE_RATES), "rake_cap_bb": 3})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, (name, cfg, root)) for name, cfg in plan]
        for future in as_completed(futures):
            name, summary, timing = future.result()
            print(json.dumps({"finished": name, "hands": summary["completed_hands"],
                              "cpu_seconds": timing["cpu_seconds"]}), flush=True)


def analyze(root: Path, output: Path, policies=POLICIES, seeds=EVAL_SEEDS) -> dict:
    rows_by, runs = defaultdict(dict), []
    for name, cfg in jobs(policies, seeds):
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
        policy = name.split("-v-tag-")[0]
        rows_by[policy][cfg.deck_seed] = rows
        timing = m["decision_bridge_timing"]
        runs.append({"name": name, "audit": asyncio.run(audit_cfr(folder)),
                     "cfr_ms_per_decision": 1000 * timing["a"]["cpu_seconds"] / timing["a"]["decisions"],
                     "net_5": performance([r["a_net_chips"] for r in rows])})
    decks = [deck for deck, _ in seeds]
    results = {}
    for policy, by_seed in rows_by.items():
        pooled = [r for deck in decks for r in by_seed[deck]]
        entry = {"policy": policies[policy], "hands": len(pooled), "rake": {}}
        for rate in RAKE_RATES:
            ledger = [rerake(r, rate) for r in pooled]
            entry["rake"][str(rate)] = performance([r["a"] for r in ledger])
        entry["seed_net_bb100"] = [performance([r["a_net_chips"] for r in by_seed[d]])["bb_per_100"] for d in decks]
        entry["sd_seed_means_bb100"] = statistics.stdev(entry["seed_net_bb100"])
        low, high = entry["rake"]["5"]["ci95_bb_per_100"]
        entry["verdict_vs_tag"] = ("beats" if low > 0 and all(v > 0 for v in entry["seed_net_bb100"])
                                   else "loses" if high < 0 else "inconclusive")
        results[policy] = entry
    paired = []
    for new, old in COMPARISONS:
        diffs = [a["a_net_chips"] - b["a_net_chips"] for d in decks for a, b in zip(rows_by[new][d], rows_by[old][d])]
        metrics = performance(diffs)
        low, high = metrics["ci95_bb_per_100"]
        paired.append({"comparison": f"{new} - {old}", "difference": metrics,
                       "per_seed": [performance([a["a_net_chips"] - b["a_net_chips"]
                                                 for a, b in zip(rows_by[new][d], rows_by[old][d])])["bb_per_100"] for d in decks],
                       "verdict": "better" if low > 0 else "worse" if high < 0 else "inconclusive"})
    result = {"policies": results, "paired": paired, "runs": runs, "rake_cap_bb": 3, "no_flop_no_drop": True,
              "ci_method": "normal 95% on independent two-hand block means; paired per-hand differences on identical deals"}
    write_json(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("run"); s.add_argument("--output", type=Path, required=True); s.add_argument("--workers", type=int, default=4)
    s.add_argument("--confirm", action="store_true", help="use the fresh confirmation seeds")
    s = sub.add_parser("analyze"); s.add_argument("source", type=Path); s.add_argument("--output", type=Path, required=True)
    s.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    seeds = CONFIRM_SEEDS if a.confirm else EVAL_SEEDS
    if a.command == "run":
        run_suite(a.output, a.workers, seeds=seeds)
    else:
        analyze(a.source, a.output, seeds=seeds)


if __name__ == "__main__":
    main()
