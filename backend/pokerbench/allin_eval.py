"""Preregistered evaluation of the all-in defense variants against CFR V2 adaptive.

Protocol, fixed and committed before any evaluation hand is played:
- policies: ``adapt`` (CFR V2 adaptive, the current default), ``allin-top``
  and ``allin-any`` (allin.py with each shoving-range hypothesis), all on the
  V2 300k policy file;
- opponents: hyper, tag, station, equity and shover (the profile calibrated on
  the 49-hand session, ~68 % of hands with an all-in);
- unseen seeds (171001-171003 / 181001-181003), 10,000 hands each, strictly
  alternating button; every policy plays identical deals and policy seeds, with
  public statistics and the separate all-in counters exposed: 450,000 hands;
- metric: net bb/100 at 5 % rake (cap 3 BB, no flop no drop), 95 % CI on
  two-hand blocks; paired per-hand differences against ``adapt``;
- acceptance: a variant is accepted only if its paired difference against
  ``shover`` has a CI entirely above zero AND none of the other four paired
  differences has a CI entirely below zero. If both are accepted, the larger
  shover gain wins. If none is accepted, CFR V2 adaptive stays the default.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .benchmark import Config, performance
from .holdem_abstraction import resolve_policy
from .mission3 import read_rows, rerake, run_job, write_json
from .mission6 import _audit

POLICY = "artifacts/mission5/policy-v2-72001-300000.json.gz"
VARIANTS = {"adapt": {"cfr_adaptive": True}, "allin-top": {"cfr_allin": "top"}, "allin-any": {"cfr_allin": "any"}}
OPPONENTS = ("hyper", "tag", "station", "equity", "shover")
SEEDS = ((171001, 181001), (171002, 181002), (171003, 181003))
MAIN_HANDS = 10000
RAKE_RATES = (0, 2, 5, 7)


def jobs(variants=VARIANTS, opponents=OPPONENTS, seeds=SEEDS):
    for deck, seed in seeds:
        for opponent in opponents:
            for name, options in variants.items():
                yield f"{name}-v-{opponent}-{deck}", Config(
                    hands=MAIN_HANDS, agent_a="cfr", agent_b=opponent, deck_seed=deck, policy_seed=seed,
                    measure_time=True, cfr_policy=POLICY, public_stats=True, allin_stats=True, **options)


def run_suite(root: Path, workers: int):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    plan = list(jobs())
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root / "plan.json", {"workers": workers, "jobs": {n: asdict(c) for n, c in plan},
                                    "policy_sha256": hashlib.sha256(resolve_policy(POLICY).read_bytes()).hexdigest(),
                                    "rake_rates": list(RAKE_RATES), "rake_cap_bb": 3})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(run_job, (n, c, root)) for n, c in plan]):
            name, summary, timing = future.result()
            print(json.dumps({"finished": name, "hands": summary["completed_hands"]}), flush=True)


def all_in_responses(folder: Path, seat="a") -> dict:
    """How the CFR seat answered the opponent's preflop all-ins, and the result."""
    counts = Counter()
    with (folder / "decisions.jsonl").open() as f:
        for line in f:
            e = json.loads(line)
            obs = e["observation"]
            if e["actor"] != seat or obs["street"] != "preflop" or not obs["history"]:
                continue
            if obs["history"][-1]["all_in"] and obs["history"][-1]["player"] != obs["actor"]:
                kind = next(a["kind"] for a in obs["legal_actions"] if a["id"] == e["action"])
                counts["faced"] += 1
                counts[kind] += 1
    return {"faced": counts["faced"], "call_rate": counts["call"] / counts["faced"] if counts["faced"] else None}


def analyze(root: Path, output: Path, variants=VARIANTS, opponents=OPPONENTS, seeds=SEEDS, workers: int = 4) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    plan = list(jobs(variants, opponents, seeds))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        audits = dict(zip((n for n, _ in plan), pool.map(_audit, [root / n for n, _ in plan])))
    rows_by, runs = defaultdict(dict), []
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
        variant = name.split(f"-v-{cfg.agent_b}-")[0]
        rows_by[(variant, cfg.agent_b)][cfg.deck_seed] = rows
        audit, freq = audits[name]
        runs.append({"name": name, "variant": variant, "opponent": cfg.agent_b, "audit": audit,
                     "frequencies": freq, "all_in_responses": all_in_responses(folder)})
    decks = [d for d, _ in seeds]
    results = []
    for (variant, opponent), by_seed in rows_by.items():
        pooled = [r for d in decks for r in by_seed[d]]
        entry = {"variant": variant, "opponent": opponent, "hands": len(pooled),
                 "rake": {str(rate): performance([r["a"] for r in (rerake(x, rate) for x in pooled)]) for rate in RAKE_RATES},
                 "seed_net_bb100": [performance([r["a_net_chips"] for r in by_seed[d]])["bb_per_100"] for d in decks],
                 "position_net_bb100": {pos: sum(r["a_net_chips"] for r in pooled if (r["button"] == "a") == (pos == "BTN"))
                                        / (len(pooled) / 2) for pos in ("BTN", "BB")}}
        faced = [r["all_in_responses"] for r in runs if r["variant"] == variant and r["opponent"] == opponent]
        total = sum(x["faced"] for x in faced)
        entry["faced_preflop_all_ins"] = total
        entry["call_rate_vs_all_in"] = (sum(x["faced"] * (x["call_rate"] or 0) for x in faced) / total) if total else None
        results.append(entry)
    paired, decisions = [], {}
    for variant in variants:
        if variant == "adapt":
            continue
        verdicts = {}
        for opponent in opponents:
            diffs = [a["a_net_chips"] - b["a_net_chips"] for d in decks
                     for a, b in zip(rows_by[(variant, opponent)][d], rows_by[("adapt", opponent)][d])]
            metrics = performance(diffs)
            low, high = metrics["ci95_bb_per_100"]
            verdicts[opponent] = "better" if low > 0 else "worse" if high < 0 else "inconclusive"
            paired.append({"comparison": f"{variant} - adapt", "opponent": opponent, "difference": metrics,
                           "verdict": verdicts[opponent]})
        accepted = verdicts["shover"] == "better" and all(v != "worse" for o, v in verdicts.items() if o != "shover")
        decisions[variant] = {"accepted": accepted, "verdicts": verdicts}
    accepted = [v for v, d in decisions.items() if d["accepted"]]
    gain = {p["comparison"].split(" - ")[0]: p["difference"]["bb_per_100"] for p in paired if p["opponent"] == "shover"}
    result = {"results": results, "paired": paired, "runs": runs, "decisions": decisions,
              "default": max(accepted, key=gain.get) if accepted else "adapt",
              "rake_cap_bb": 3, "no_flop_no_drop": True,
              "ci_method": "normal 95% on independent two-hand block means; paired per-hand differences on identical deals"}
    write_json(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("run"); s.add_argument("--output", type=Path, required=True); s.add_argument("--workers", type=int, default=4)
    s = sub.add_parser("analyze"); s.add_argument("source", type=Path); s.add_argument("--output", type=Path, required=True)
    s.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    if a.command == "run":
        run_suite(a.output, a.workers)
    else:
        analyze(a.source, a.output, workers=a.workers)


if __name__ == "__main__":
    main()
