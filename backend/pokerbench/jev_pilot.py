"""Mission 7B pilot: 500 decisions answered by Jev and by CFR V2 adaptive.

Protocol, fixed before any call:
- decision points: the CFR V2 adaptive seat's requests over seeded local hands
  against hyper, tag, station and equity (seed 74001, 200 hands each), exactly
  as a room sends them to a model; synthetic deals, no personal history;
- sample: 150 preflop, 150 flop, 100 turn, 100 river requests drawn without
  replacement (seed 74001); the plan file and its SHA-256 are committed;
- Jev: official TypeSafe endpoint ``/v1/systemone``, model pinned to
  ``jev-1.14.0`` (a reply from another model stops the run), one call per
  request, answers cached by request so a rerun costs nothing;
- measures: valid answers, latency, billed tokens and cost, agreement with CFR
  (top action, action kind, total variation), where they disagree;
- the pilot says nothing about playing strength: that is the benchmark's job.

``run`` makes paid calls: it refuses without ``--approve-paid-calls`` and a
USD ceiling, and the Provider's budget hold stops it before the ceiling.
"""
import argparse
import asyncio
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import time

from .compare import KINDS, CFRAdvisor, RecordedAdvisor, collect, compare, request_hash, total_variation

SEED, HANDS = 74001, 200
QUOTAS = {"preflop": 150, "flop": 150, "turn": 100, "river": 100}
MODEL = "jev-1.14.0"
PLAN = Path(__file__).resolve().parents[2] / "artifacts" / "mission7b" / "pilot-plan.jsonl.gz"


def build_plan(seed: int = SEED, hands: int = HANDS, quotas: dict = QUOTAS) -> list[dict]:
    pool = asyncio.run(collect(hands, seed))
    rng = random.Random(seed)
    chosen = []
    for street, quota in quotas.items():
        candidates = [r for r in pool if r["state"]["street"] == street]
        if len(candidates) < quota:
            raise ValueError(f"Only {len(candidates)} {street} decisions for a quota of {quota}")
        chosen += rng.sample(candidates, quota)
    return chosen


def body(request: dict) -> dict:
    return {k: v for k, v in request.items() if k != "meta"}


def write_plan(path: Path, plan: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in plan).encode()
    # Fixed mtime: the same plan always gives the same file and checksum.
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def read_plan(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def jev_entry():
    from .config import Entry
    return Entry(id="jev", name="Jev", provider="jev", model=MODEL, expected_model=MODEL, proxy=False)


def estimate(plan: list[dict], usd_cny_rate: float, max_tokens: int = 8192) -> dict:
    """Upper bound = the Provider's hold (one token per byte + 512); expected = 4 bytes per token."""
    entry = jev_entry()
    sizes = [len(json.dumps(body(r) | {"model": entry.model}).encode()) for r in plan]
    price = entry.input_usd_per_million / 1e6
    bound = sum(s + 512 for s in sizes) * price + len(sizes) * max_tokens * entry.output_usd_per_million / 1e6
    expected = sum(s / 4 for s in sizes) * price
    return {"requests": len(sizes), "mean_request_bytes": statistics.mean(sizes), "max_request_bytes": max(sizes),
            "input_usd_per_million": entry.input_usd_per_million, "output_usd_per_million": entry.output_usd_per_million,
            "upper_bound_usd": bound, "expected_usd": expected,
            "upper_bound_cny": bound * usd_cny_rate, "expected_cny": expected * usd_cny_rate, "usd_cny_rate": usd_cny_rate}


async def run(plan: list[dict], output: Path, max_usd: float, approve_paid_calls: bool = False,
              settings=None, concurrency: int = 4) -> dict:
    """Ask Jev every planned request once; answers go to ``output/answers.jsonl``."""
    if not approve_paid_calls:
        raise PermissionError("The pilot makes paid calls: pass approve_paid_calls=True (--approve-paid-calls)")
    if not 0 < max_usd <= 5:
        raise ValueError("max_usd must be in (0, 5]")
    from .config import Settings
    from .provider import Provider, ProviderError
    from .store import Store
    settings = settings or Settings()
    entry = jev_entry()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    provider = Provider(settings, Store(str(output / "calls.db")))
    if not provider.available(entry):
        raise PermissionError("JEV_API_KEY is not configured")
    budget_cny = max_usd * settings.pokerbench_usd_cny_rate
    if not budget_cny > 0:
        raise ValueError("POKERBENCH_USD_CNY_RATE must be positive for a USD budget")
    done = {}
    answers = output / "answers.jsonl"
    if answers.exists():
        done = {row["request_hash"]: row for row in map(json.loads, answers.read_text().splitlines())}
    gate, stop = asyncio.Semaphore(concurrency), asyncio.Event()

    async def ask(request):
        digest = request_hash(body(request))
        if digest in done or stop.is_set():
            return done.get(digest)
        async with gate:
            if stop.is_set():
                return None
            started = time.monotonic()
            try:
                result = await provider.call(entry, body(request) | {"model": entry.model},
                                             decision_id=f"pilot7b-{digest[:32]}", run_id="pilot7b",
                                             run_budget=budget_cny, timeout=60)
                row = {"request_hash": digest, "response": result, "error": None}
            except (ProviderError, ValueError) as exc:
                # The Store refuses a call beyond the budget with a ValueError ("预算不足").
                row = {"request_hash": digest, "response": None, "error": str(exc)}
                # Identity mismatch or exhausted budget: no further call can be valid.
                if "模型身份不符" in str(exc) or "预算" in str(exc):
                    stop.set()
            row["wall_seconds"] = time.monotonic() - started
            with answers.open("a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            done[digest] = row
            return row

    await asyncio.gather(*(ask(r) for r in plan))
    calls = provider.store.calls()
    return {"answered": sum(1 for r in done.values() if r["response"]), "errors": sum(1 for r in done.values() if r["error"]),
            "stopped_early": stop.is_set(), "calls": len(calls),
            "spent_cny": provider.store.spend(), "spent_usd": provider.store.spend() / settings.pokerbench_usd_cny_rate}


VERIFY_CALLS = 10


def verification_sample(plan: list[dict], n: int = VERIFY_CALLS) -> list[dict]:
    """Evenly spaced planned requests (every street is represented), asked first."""
    return plan[:: max(1, len(plan) // n)][:n]


def check_calls(output: Path, plan: list[dict], usd_cny_rate: float) -> dict:
    """Authentication, model identity, answer structure, usage and billing of every call so far.

    Reads the recorded answers and the call ledger; writes nothing that holds a key.
    """
    import sqlite3
    rows = [json.loads(line) for line in (output / "answers.jsonl").read_text().splitlines()]
    planned = {request_hash(body(r)): body(r) for r in plan}
    failures = []
    for row in rows:
        tag = row["request_hash"][:12]
        if row["error"]:
            failures.append(f"{tag}: call failed: {row['error'][:120]}")
            continue
        response, request = row["response"], planned[row["request_hash"]]
        if response.get("model") != MODEL:
            failures.append(f"{tag}: model {str(response.get('model'))[:40]}")
        answer = (response.get("answers") or {}).get("action") or {}
        legal = set(request["questions"]["action"]["criteria"])
        if set(answer.get("probabilities") or {}) != legal or answer.get("choice") not in legal \
                or not isinstance(answer.get("confidence"), (int, float)):
            failures.append(f"{tag}: answer structure")
        usage = response.get("usage") or {}
        if not (isinstance(usage.get("input_tokens"), int) and usage["input_tokens"] > 0
                and isinstance(usage.get("output_tokens"), int) and usage["output_tokens"] >= 0):
            failures.append(f"{tag}: usage {usage}")
    db = sqlite3.connect(output / "calls.db")
    ledger = [(status, charged, json.loads(body_)) for status, charged, body_ in
              db.execute("SELECT status, charged, body FROM calls WHERE run_id='pilot7b'")]
    db.close()
    for status, charged, meta in ledger:
        tokens = meta.get("input_tokens")
        if status != "reported" or not isinstance(tokens, int):
            failures.append(f"billing: call not metered ({status})")
            continue
        expected_usd = tokens * jev_entry().input_usd_per_million / 1e6
        if abs(meta.get("charge_usd", -1) - expected_usd) > 1e-12 or abs(charged - expected_usd * usd_cny_rate) > 1e-9:
            failures.append("billing: charge does not match input tokens x 0.042 USD/M")
    return {"calls": len(ledger), "answers": len(rows), "failures": failures, "passed": not failures and bool(rows)}


async def pilot(plan: list[dict], output: Path, max_usd: float, approve_paid_calls: bool = False,
                settings=None, concurrency: int = 4) -> dict:
    """Ten verification calls, then the rest of the plan only if every check passed.

    Both stages share one call ledger and run id: ``max_usd`` caps their total.
    """
    from .config import Settings
    settings = settings or Settings()
    first = verification_sample(plan)
    stage1 = await run(first, output, max_usd, approve_paid_calls, settings, concurrency=1)
    verification = check_calls(output, first, settings.pokerbench_usd_cny_rate)
    (output / "verification.json").write_text(json.dumps(verification, indent=1))
    if not verification["passed"] or stage1["stopped_early"]:
        return {"verification": verification, "stage1": stage1, "stage2": None, "stopped": True}
    stage2 = await run(plan, output, max_usd, approve_paid_calls, settings, concurrency)
    return {"verification": verification, "stage1": stage1, "stage2": stage2, "stopped": stage2["stopped_early"]}


def _describe(state: dict) -> dict:
    hero = next(s for s in state["seats"] if s["id"] == state["actor"])
    return {"street": state["street"], "position": hero["position"], "cards": hero["cards"], "board": state["board"],
            "pot": state["pot"], "to_call": state["to_call"], "stack": hero["stack"],
            "history": " ".join(f"{e['player'][-1]}:{e['kind']}{e['to'] if e['kind'] == 'raise' else ''}"
                                for e in state["history"])}


async def analyze(plan: list[dict], answers_path: Path) -> dict:
    rows = [json.loads(line) for line in Path(answers_path).read_text().splitlines()]
    by_hash = {r["request_hash"]: r for r in rows}
    answered = [r for r in plan if (by_hash.get(request_hash(body(r))) or {}).get("response")]
    jev = RecordedAdvisor.from_answers({h: r["response"] for h, r in by_hash.items() if r["response"]})
    cfr = CFRAdvisor("cfr-v2-adapt")
    agreement = await compare(answered, cfr, jev, examples=0)
    confusion, mass_on_cfr_top, detail = Counter(), [], []
    for request in answered:
        b = body(request)
        criteria = b["questions"]["action"]["criteria"]
        c = (await cfr(b))["answers"]["action"]["probabilities"]
        j = (await jev(b))["answers"]["action"]["probabilities"]
        top_c, top_j = max(c, key=c.get), max(j, key=j.get)
        confusion[f"{KINDS[criteria[top_c]['action']]}→{KINDS[criteria[top_j]['action']]}"] += 1
        mass_on_cfr_top.append(j.get(top_c, 0.0))
        detail.append({**_describe(b["state"]), "opponent": request["meta"]["opponent"], "cfr": c, "jev": j,
                       "tv": total_variation(c, j), "hash": request_hash(b)[:12]})
    responses = [r["response"] for r in rows if r["response"]]
    latency = [r["latency"] for r in responses if isinstance(r.get("latency"), (int, float))]
    tokens = [r["usage"]["input_tokens"] for r in responses if isinstance((r.get("usage") or {}).get("input_tokens"), int)]
    confidence = [a["action"].get("confidence") for a in (r["answers"] for r in responses)
                  if isinstance(a["action"].get("confidence"), (int, float))]
    return {"planned": len(plan), "answered": len(answered), "errors": sum(1 for r in rows if r["error"]),
            "error_reasons": dict(Counter(r["error"][:80] for r in rows if r["error"])),
            "models": dict(Counter(r.get("model") for r in responses)),
            "latency_seconds": {"median": statistics.median(latency), "p90": sorted(latency)[int(0.9 * (len(latency) - 1))]}
            if latency else None,
            "input_tokens": {"mean": statistics.mean(tokens), "total": sum(tokens)} if tokens else None,
            "jev_confidence_mean": statistics.mean(confidence) if confidence else None,
            "agreement": agreement, "kind_confusion_cfr_to_jev": dict(confusion),
            "jev_mass_on_cfr_top_action": statistics.mean(mass_on_cfr_top) if mass_on_cfr_top else None,
            "largest_disagreements": sorted(detail, key=lambda d: -d["tv"])[:15]}


def report_markdown(result: dict, estimate_: dict | None = None) -> str:
    a = result["agreement"]
    lines = ["# Pilote Jev ↔ CFR V2 adaptative (Mission 7B)", "",
             f"Décisions prévues : {result['planned']} · réponses valides : {result['answered']} · erreurs : {result['errors']}",
             f"Modèles servis : {result['models']}", ""]
    if result["latency_seconds"]:
        lines.append(f"Latence : médiane {result['latency_seconds']['median']:.2f} s, p90 {result['latency_seconds']['p90']:.2f} s")
    if result["input_tokens"]:
        lines.append(f"Tokens d'entrée facturés : {result['input_tokens']['total']} (moyenne {result['input_tokens']['mean']:.0f})")
    if estimate_:
        lines.append(f"Coût prévu (borne haute) : {estimate_['upper_bound_usd']:.4f} USD")
    o = a["overall"]
    lines += ["", "## Accord", "", "| Périmètre | Décisions | Même action | Même type | Variation totale |",
              "| :-- | --: | --: | --: | --: |",
              f"| Tout | {o['decisions']} | {o['same_action']:.1%} | {o['same_kind']:.1%} | {o['mean_tv']:.3f} |"]
    for group in ("by_street", "by_opponent", "by_facing_bet"):
        for key, v in a[group].items():
            lines.append(f"| {group[3:]} = {key} | {v['decisions']} | {v['same_action']:.1%} | {v['same_kind']:.1%} | {v['mean_tv']:.3f} |")
    lines += ["", f"Masse moyenne que Jev place sur l'action préférée de CFR : {result['jev_mass_on_cfr_top_action']:.1%}",
              "", "## Types d'action (CFR → Jev)", "", "| CFR → Jev | Décisions |", "| :-- | --: |"]
    lines += [f"| {k} | {v} |" for k, v in sorted(result["kind_confusion_cfr_to_jev"].items(), key=lambda kv: -kv[1])]
    lines += ["", "## Plus grands désaccords", "", "| Rue | Pos. | Cartes | Board | Pot / à payer | Historique | CFR | Jev | VT |",
              "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: |"]
    top = lambda d: ", ".join(f"{k} {v:.0%}" for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:2])
    for d in result["largest_disagreements"]:
        lines.append(f"| {d['street']} | {d['position']} | {' '.join(d['cards'])} | {' '.join(d['board']) or '—'} | "
                     f"{d['pot']} / {d['to_call']} | {d['history'] or '—'} | {top(d['cfr'])} | {top(d['jev'])} | {d['tv']:.2f} |")
    lines += ["", "Un désaccord n'indique pas qui a raison : seul le benchmark apparié (mission7.py) mesure l'effet en jetons."]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("plan", help="build the 500-decision plan (free)")
    s.add_argument("--output", type=Path, default=PLAN)
    s = sub.add_parser("estimate", help="cost bound for the plan (free)")
    s.add_argument("--plan", type=Path, default=PLAN)
    s = sub.add_parser("run", help="PAID: ask Jev every planned request")
    s.add_argument("--plan", type=Path, default=PLAN); s.add_argument("--output", type=Path, required=True)
    s.add_argument("--max-usd", type=float, required=True); s.add_argument("--approve-paid-calls", action="store_true")
    s = sub.add_parser("pilot", help="PAID: 10 verification calls, then the rest if every check passes")
    s.add_argument("--plan", type=Path, default=PLAN); s.add_argument("--output", type=Path, required=True)
    s.add_argument("--max-usd", type=float, required=True); s.add_argument("--approve-paid-calls", action="store_true")
    s = sub.add_parser("analyze", help="disagreement report from recorded answers (free)")
    s.add_argument("--plan", type=Path, default=PLAN); s.add_argument("answers", type=Path)
    s.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    from .config import Settings
    if a.command == "plan":
        digest = write_plan(a.output, build_plan())
        print(json.dumps({"plan": str(a.output), "sha256": digest}))
    elif a.command == "estimate":
        print(json.dumps(estimate(read_plan(a.plan), Settings().pokerbench_usd_cny_rate), indent=1))
    elif a.command == "run":
        print(json.dumps(asyncio.run(run(read_plan(a.plan), a.output, a.max_usd, a.approve_paid_calls)), indent=1))
    elif a.command == "pilot":
        result = asyncio.run(pilot(read_plan(a.plan), a.output, a.max_usd, a.approve_paid_calls))
        print(json.dumps(result, indent=1))
        if result["stopped"]:
            raise SystemExit("Pilot stopped: see verification.json")
    else:
        plan = read_plan(a.plan)
        result = asyncio.run(analyze(plan, a.answers))
        a.output.mkdir(parents=True, exist_ok=True)
        (a.output / "pilot-analysis.json").write_text(json.dumps(result, indent=1))
        (a.output / "pilot-report.md").write_text(report_markdown(result, estimate(plan, Settings().pokerbench_usd_cny_rate)))
        print(json.dumps(result["agreement"]["overall"]))


if __name__ == "__main__":
    main()
