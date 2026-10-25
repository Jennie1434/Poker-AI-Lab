"""Mission 4 preregistered evaluation of the frozen MCCFR Hold'em policy.

Protocol fixed before any evaluation hand is played (committed with this file):
- policy: external-sampling MCCFR, training seed 71001, 200,000 iterations,
  abstraction ``holdem-hu-abstract-v1`` defaults; frozen, no learning in play;
- primary: CFRAgent (seat a) against random, heuristic, equity, tag, each on
  three new (deck, policy) seed pairs never used in training or earlier missions,
  10,000 hands per experiment, strictly alternating button: 120,000 hands;
- secondary diagnostic: the 20,000-iteration snapshot against equity and tag on
  the first seed pair, compared hand-for-hand with the final policy;
- metric: net bb/100 at 5 % rake (cap 3 BB, no flop no drop); also 0/2/7 %;
  normal 95 % CI on two-hand position-balanced blocks, per seed and pooled;
- verdict rule: "beats" an opponent only if the pooled 5 % CI is entirely above
  zero and all three seeds are positive; "loses" if entirely below zero;
- every experiment is reported; no early stopping or seed replacement.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
from itertools import groupby
import json
from pathlib import Path
import statistics

from .benchmark import Config, derive_seed, performance
from .holdem_abstraction import CFRAgent, cached_policy, resolve_policy
from .mission3 import read_rows, rerake, run_job, write_json

TRAIN_SEED, TRAIN_ITERATIONS, SNAPSHOT = 71001, 200000, 20000
EVAL_SEEDS = ((51001, 61001), (51002, 61002), (51003, 61003))
OPPONENTS = ("random", "heuristic", "equity", "tag")
MAIN_HANDS = 10000
POLICY = "artifacts/mission4/policy-71001-200000.json.gz"
SNAPSHOT_POLICY = "artifacts/mission4/policy-71001-20000.json.gz"
RAKE_RATES = (0, 2, 5, 7)


def jobs(policy=POLICY, snapshot=SNAPSHOT_POLICY):
    for deck, seed in EVAL_SEEDS:
        for opponent in OPPONENTS:
            yield f"cfr-v-{opponent}-{deck}", Config(hands=MAIN_HANDS, agent_a="cfr", agent_b=opponent, deck_seed=deck,
                                                     policy_seed=seed, measure_time=True, cfr_policy=policy)
    deck, seed = EVAL_SEEDS[0]
    for opponent in ("equity", "tag"):
        yield f"cfr{SNAPSHOT}-v-{opponent}-{deck}-diagnostic", Config(
            hands=MAIN_HANDS, agent_a="cfr", agent_b=opponent, deck_seed=deck, policy_seed=seed,
            measure_time=True, cfr_policy=snapshot)


def run_suite(root: Path, workers: int, policy=POLICY, snapshot=SNAPSHOT_POLICY):
    plan = list(jobs(policy, snapshot))
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root / "plan.json", {"workers": workers, "jobs": {n: asdict(c) for n, c in plan},
                                    "policy_sha256": {p: hashlib.sha256(resolve_policy(p).read_bytes()).hexdigest()
                                                      for p in {policy, snapshot}},
                                    "rake_rates": list(RAKE_RATES), "rake_cap_bb": 3})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_job, (name, cfg, root)) for name, cfg in plan]
        for future in as_completed(futures):
            name, summary, timing = future.result()
            print(json.dumps({"finished": name, "hands": summary["completed_hands"],
                              "cpu_seconds": timing["cpu_seconds"]}), flush=True)


async def audit_cfr(folder: Path) -> dict:
    """Replay every CFR decision from its seed: same action, hidden cards absent.

    Also counts decisions that left the abstract tree (fallback policy).
    """
    m = json.loads((folder / "experiment.json").read_text())
    cfg = Config(**m["config"])
    for name, expected in m["artifacts_sha256"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact checksum mismatch")
    policy = cached_policy(cfg.cfr_policy)
    counts, streets = Counter(), Counter()
    with (folder / "decisions.jsonl").open() as f:
        for number, entries in groupby((json.loads(line) for line in f), key=lambda e: e["hand"]):
            agent = CFRAgent(derive_seed(cfg.policy_seed, "policy:a", number - 1), policy)
            for entry in entries:
                if entry["actor"] != "a":
                    continue
                obs = entry["observation"]
                for seat in obs["seats"]:
                    if seat["id"] != obs["actor"] and seat["cards"] != seat["public_cards"]:
                        raise ValueError("Hidden-card leak")
                before = agent.stats["fallback"]
                if await agent.choose_action(obs) != entry["action"]:
                    raise ValueError(f"CFR decision not reproduced in hand {number}")
                if agent.stats["fallback"] > before:
                    streets[obs["street"]] += 1
            counts.update(agent.stats)
    return {"decisions": counts["decisions"], "fallback": counts["fallback"],
            "fallback_rate": counts["fallback"] / max(1, counts["decisions"]), "fallback_by_street": dict(streets)}


def analyze(root: Path, output: Path, policy=POLICY, snapshot=SNAPSHOT_POLICY) -> dict:
    reports, groups, per_run = {}, defaultdict(list), []
    for name, cfg in jobs(policy, snapshot):
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
        audit = asyncio.run(audit_cfr(folder))
        timing = m["decision_bridge_timing"]
        reports[name] = rows
        per_run.append({"name": name, "config": asdict(cfg), "audit": audit,
                        "cfr_ms_per_decision": 1000 * timing["a"]["cpu_seconds"] / timing["a"]["decisions"],
                        "opponent_ms_per_decision": 1000 * timing["b"]["cpu_seconds"] / max(1, timing["b"]["decisions"]),
                        "net_5": performance([r["a_net_chips"] for r in rows])})
        if not name.endswith("diagnostic"):
            groups[cfg.agent_b].append(rows)
    primary = []
    for opponent in OPPONENTS:
        sets = groups[opponent]
        rows = [r for block in sets for r in block]
        entry = {"opponent": opponent, "hands": len(rows), "seeds": len(sets), "rake": {}}
        for rate in RAKE_RATES:
            ledger = [rerake(r, rate) for r in rows]
            entry["rake"][str(rate)] = {seat: performance([r[seat] for r in ledger]) for seat in ("a", "b")}
        seeds = [performance([r["a_net_chips"] for r in block]) for block in sets]
        entry["seed_net_bb100"] = [s["bb_per_100"] for s in seeds]
        entry["sd_seed_means_bb100"] = statistics.stdev(entry["seed_net_bb100"])
        low, high = entry["rake"]["5"]["a"]["ci95_bb_per_100"]
        entry["verdict"] = ("beats" if low > 0 and all(v > 0 for v in entry["seed_net_bb100"])
                            else "loses" if high < 0 else "inconclusive")
        primary.append(entry)
    deck = EVAL_SEEDS[0][0]
    diagnostic = []
    for opponent in ("equity", "tag"):
        final, early = reports[f"cfr-v-{opponent}-{deck}"], reports[f"cfr{SNAPSHOT}-v-{opponent}-{deck}-diagnostic"]
        diagnostic.append({"opponent": opponent, "snapshot_iterations": SNAPSHOT,
                           "snapshot_net": performance([r["a_net_chips"] for r in early]),
                           "final_net": performance([r["a_net_chips"] for r in final]),
                           "paired_final_minus_snapshot": performance(
                               [f["a_net_chips"] - e["a_net_chips"] for f, e in zip(final, early)])})
    result = {"primary": primary, "runs": per_run, "training_diagnostic": diagnostic,
              "rake_cap_bb": 3, "no_flop_no_drop": True,
              "ci_method": "normal 95% on independent two-hand block means; per-seed results also reported"}
    write_json(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("run"); s.add_argument("--output", type=Path, required=True); s.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("analyze"); s.add_argument("source", type=Path); s.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.command == "run":
        run_suite(a.output, a.workers)
    else:
        analyze(a.source, a.output)


if __name__ == "__main__":
    main()
