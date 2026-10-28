"""Complementary review of the Jev pilot: families, raise sizes, strong-hand folds.

Reads the recorded answers only (no call). Every number published from here is
an aggregate or a synthetic decision point from the committed plan; raw
responses and the call ledger stay private.

- families: probability mass on fold / check-call / bet-raise, so a raise
  spread over several sizes is not mistaken for passivity;
- size split: how often Jev's top single action is passive while its total
  raise mass is the largest family;
- hand strength: made-hand class (treys) and equity against a random hand
  (Monte Carlo, fixed seed), to flag folds of strong hands and river raises.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import statistics

from treys import Card, Evaluator

from .compare import CFRAdvisor, request_hash
from .jev_pilot import PLAN, body, read_plan

FAMILIES = ("fold", "check/call", "bet/raise")
FAMILY = {"fold": "fold", "check": "check/call", "call": "check/call", "raise": "bet/raise"}
STRONG_CLASSES = {"Royal Flush", "Straight Flush", "Four of a Kind", "Full House", "Flush", "Straight", "Three of a Kind", "Two Pair"}
_EVAL = Evaluator()


def families(probabilities: dict, criteria: dict) -> dict:
    mass = dict.fromkeys(FAMILIES, 0.0)
    for action, p in probabilities.items():
        mass[FAMILY[criteria[action]["action"]]] += p
    return mass


def top(mass: dict) -> str:
    return max(mass, key=mass.get)


def raise_spread(probabilities: dict, criteria: dict) -> dict:
    """Raise mass, number of sizes carrying it, and the largest single size's share."""
    sizes = [p for a, p in probabilities.items() if criteria[a]["action"] == "raise"]
    total = sum(sizes)
    used = [p for p in sizes if p >= 0.01]
    return {"mass": total, "sizes_offered": len(sizes), "sizes_used": len(used),
            "largest_share": max(sizes) / total if total > 0 else None}


def strength(state: dict, rng: random.Random, samples: int = 400) -> dict:
    """Made-hand class and equity against one random hand (exact table preflop)."""
    from .holdem_abstraction import equity, hand_class
    hero = next(s for s in state["seats"] if s["id"] == state["actor"])
    cards, board = hero["cards"], state["board"]
    if not board:
        from .holdem_abstraction import cached_policy
        table = cached_policy("artifacts/mission5/policy-v2-72001-300000.json.gz")["abstraction"]["preflop_equity"]
        return {"made": "preflop " + hand_class(cards), "equity": table[hand_class(cards)], "strong": table[hand_class(cards)] >= 0.65}
    made = _EVAL.class_to_string(_EVAL.get_rank_class(_EVAL.evaluate([Card.new(c) for c in board],
                                                                       [Card.new(c) for c in cards])))
    value = equity(cards, board, rng, samples)
    return {"made": made, "equity": value, "strong": made in STRONG_CLASSES}


def review(plan: list[dict], answers: dict, cfr_answers: dict) -> dict:
    """``answers`` / ``cfr_answers``: request hash -> probabilities over action ids."""
    rng = random.Random(74001)
    rows = []
    for request in plan:
        b = body(request)
        h = request_hash(b)
        if h not in answers:
            continue
        criteria, state = b["questions"]["action"]["criteria"], b["state"]
        jev, cfr = answers[h], cfr_answers[h]
        fj, fc = families(jev, criteria), families(cfr, criteria)
        rows.append({"hash": h[:12], "street": state["street"], "facing_bet": bool(state["to_call"]),
                     "opponent": request["meta"]["opponent"], "criteria": criteria, "state": state,
                     "jev": jev, "cfr": cfr, "jev_family": fj, "cfr_family": fc,
                     "jev_spread": raise_spread(jev, criteria), "cfr_spread": raise_spread(cfr, criteria),
                     "top_same": max(jev, key=jev.get) == max(cfr, key=cfr.get),
                     "family_same": top(fj) == top(fc),
                     "tv": 0.5 * sum(abs(jev.get(k, 0) - cfr.get(k, 0)) for k in criteria),
                     "family_tv": 0.5 * sum(abs(fj[f] - fc[f]) for f in FAMILIES),
                     "strength": strength(state, rng)})

    def mean_mass(selected, who):
        return {f: statistics.mean(r[f"{who}_family"][f] for r in selected) for f in FAMILIES} if selected else None

    def block(selected):
        return {"decisions": len(selected), "cfr": mean_mass(selected, "cfr"), "jev": mean_mass(selected, "jev"),
                "top_action_agreement": sum(r["top_same"] for r in selected) / len(selected) if selected else None,
                "family_agreement": sum(r["family_same"] for r in selected) / len(selected) if selected else None,
                "mean_family_tv": statistics.mean(r["family_tv"] for r in selected) if selected else None}

    groups = {"all": rows}
    for key in ("street", "facing_bet", "opponent"):
        for value in sorted({r[key] for r in rows}, key=str):
            groups[f"{key}={value}"] = [r for r in rows if r[key] == value]
    family_table = {k: block(v) for k, v in groups.items()}
    confusion = Counter(f"{top(r['cfr_family'])}→{top(r['jev_family'])}" for r in rows)

    # Size split: is Jev's passivity partly an artefact of spreading raise mass over sizes?
    hidden = [r for r in rows if r["criteria"][max(r["jev"], key=r["jev"].get)]["action"] != "raise"
              and top(r["jev_family"]) == "bet/raise"]
    cfr_aggr = [r for r in rows if top(r["cfr_family"]) == "bet/raise"]
    jev_raising = [r for r in rows if r["jev_spread"]["mass"] > 0.05]
    size_split = {
        "jev_top_action_raise": sum(r["criteria"][max(r["jev"], key=r["jev"].get)]["action"] == "raise" for r in rows),
        "jev_top_family_raise": sum(top(r["jev_family"]) == "bet/raise" for r in rows),
        "cfr_top_family_raise": len(cfr_aggr),
        "hidden_aggression_decisions": len(hidden),
        "cfr_aggressive_where_jev_family_also_raises": sum(top(r["jev_family"]) == "bet/raise" for r in cfr_aggr),
        "cfr_aggressive_where_jev_top_action_raises": sum(
            r["criteria"][max(r["jev"], key=r["jev"].get)]["action"] == "raise" for r in cfr_aggr),
        "mean_jev_raise_mass_when_cfr_aggressive": statistics.mean(r["jev_family"]["bet/raise"] for r in cfr_aggr) if cfr_aggr else None,
        "mean_cfr_raise_mass_when_cfr_aggressive": statistics.mean(r["cfr_family"]["bet/raise"] for r in cfr_aggr) if cfr_aggr else None,
        "jev_sizes_used_mean": statistics.mean(r["jev_spread"]["sizes_used"] for r in jev_raising) if jev_raising else None,
        "jev_largest_size_share_mean": statistics.mean(r["jev_spread"]["largest_share"] for r in jev_raising) if jev_raising else None,
        "cfr_sizes_used_mean": statistics.mean(r["cfr_spread"]["sizes_used"] for r in rows if r["cfr_spread"]["mass"] > 0.05),
        "sizes_offered_mean": statistics.mean(r["jev_spread"]["sizes_offered"] for r in rows),
    }

    def entropy(d):
        n = len(d)
        return -sum(p * math.log(p) for p in d.values() if p > 0) / math.log(n) if n > 1 else 0.0

    def uniform_family(r):
        n = len(r["criteria"])
        return families({a: 1 / n for a in r["criteria"]}, r["criteria"])

    # Is the raise mass a preference, or just many near-equal probabilities?
    uniformity = {
        "jev_normalized_entropy": statistics.mean(entropy(r["jev"]) for r in rows),
        "cfr_normalized_entropy": statistics.mean(entropy(r["cfr"]) for r in rows),
        "jev_tv_to_uniform": statistics.mean(0.5 * sum(abs(r["jev"][a] - 1 / len(r["criteria"])) for a in r["criteria"]) for r in rows),
        "cfr_tv_to_uniform": statistics.mean(0.5 * sum(abs(r["cfr"].get(a, 0) - 1 / len(r["criteria"])) for a in r["criteria"]) for r in rows),
        "jev_max_probability_mean": statistics.mean(max(r["jev"].values()) for r in rows),
        "cfr_max_probability_mean": statistics.mean(max(r["cfr"].values()) for r in rows),
        "uniform_raise_family_mass_mean": statistics.mean(uniform_family(r)["bet/raise"] for r in rows),
        "jev_raise_family_mass_mean": statistics.mean(r["jev_family"]["bet/raise"] for r in rows),
        "cfr_raise_family_mass_mean": statistics.mean(r["cfr_family"]["bet/raise"] for r in rows),
        # Jev's raise mass relative to what an indifferent (uniform) answer would put there.
        "jev_raise_over_uniform": statistics.mean(r["jev_family"]["bet/raise"] - uniform_family(r)["bet/raise"] for r in rows),
        "cfr_raise_over_uniform": statistics.mean(r["cfr_family"]["bet/raise"] - uniform_family(r)["bet/raise"] for r in rows),
        "jev_equity_raise_correlation": statistics.correlation([r["strength"]["equity"] for r in rows],
                                                               [r["jev_family"]["bet/raise"] for r in rows]),
        "cfr_equity_raise_correlation": statistics.correlation([r["strength"]["equity"] for r in rows],
                                                               [r["cfr_family"]["bet/raise"] for r in rows]),
        "jev_equity_fold_correlation": statistics.correlation([r["strength"]["equity"] for r in rows if r["facing_bet"]],
                                                              [r["jev_family"]["fold"] for r in rows if r["facing_bet"]]),
        "cfr_equity_fold_correlation": statistics.correlation([r["strength"]["equity"] for r in rows if r["facing_bet"]],
                                                              [r["cfr_family"]["fold"] for r in rows if r["facing_bet"]]),
    }

    strong = [r for r in rows if r["strength"]["strong"]]
    strong_folds = [r for r in strong if r["facing_bet"] and r["jev_family"]["fold"] >= 0.25]
    river_raises = [r for r in rows if r["street"] == "river" and r["cfr_family"]["bet/raise"] >= 0.5]
    hand_strength = {
        "strong_decisions": len(strong),
        "strong_facing_bet": sum(r["facing_bet"] for r in strong),
        "strong_jev_fold_mass_mean": statistics.mean(r["jev_family"]["fold"] for r in strong if r["facing_bet"])
        if any(r["facing_bet"] for r in strong) else None,
        "strong_cfr_fold_mass_mean": statistics.mean(r["cfr_family"]["fold"] for r in strong if r["facing_bet"])
        if any(r["facing_bet"] for r in strong) else None,
        "strong_folds_jev_ge_25pct": len(strong_folds),
        "strong_folds_cfr_ge_25pct": sum(r["facing_bet"] and r["cfr_family"]["fold"] >= 0.25 for r in strong),
        "river_cfr_raises": len(river_raises),
        "river_cfr_raises_value": sum(r["strength"]["strong"] for r in river_raises),
        "river_jev_raise_mass_mean": statistics.mean(r["jev_family"]["bet/raise"] for r in river_raises) if river_raises else None,
        "river_cfr_raise_mass_mean": statistics.mean(r["cfr_family"]["bet/raise"] for r in river_raises) if river_raises else None,
        "equity_buckets": {},
    }
    by_equity = defaultdict(list)
    for r in rows:
        if r["facing_bet"]:
            by_equity[min(4, int(r["strength"]["equity"] * 5))].append(r)
    for bucket, selected in sorted(by_equity.items()):
        hand_strength["equity_buckets"][f"{bucket * 20}-{bucket * 20 + 20}%"] = {
            "decisions": len(selected),
            "cfr_fold": statistics.mean(r["cfr_family"]["fold"] for r in selected),
            "jev_fold": statistics.mean(r["jev_family"]["fold"] for r in selected),
            "cfr_raise": statistics.mean(r["cfr_family"]["bet/raise"] for r in selected),
            "jev_raise": statistics.mean(r["jev_family"]["bet/raise"] for r in selected)}

    def describe(r):
        s, hero = r["state"], next(x for x in r["state"]["seats"] if x["id"] == r["state"]["actor"])
        return {"hash": r["hash"], "street": r["street"], "opponent": r["opponent"], "position": hero["position"],
                "cards": hero["cards"], "board": s["board"], "pot": s["pot"], "to_call": s["to_call"],
                "made": r["strength"]["made"], "equity": round(r["strength"]["equity"], 3),
                "cfr_family": {k: round(v, 3) for k, v in r["cfr_family"].items()},
                "jev_family": {k: round(v, 3) for k, v in r["jev_family"].items()},
                "jev_raise_sizes_used": r["jev_spread"]["sizes_used"], "tv": round(r["tv"], 3),
                "family_tv": round(r["family_tv"], 3),
                "history": " ".join(f"{e['player'][-1]}:{e['kind']}{e['to'] if e['kind'] == 'raise' else ''}"
                                    for e in s["history"])}

    return {"decisions": len(rows), "families": family_table, "family_confusion_cfr_to_jev": dict(confusion),
            "size_split": size_split, "uniformity": uniformity, "hand_strength": hand_strength,
            "top15": [describe(r) for r in sorted(rows, key=lambda r: -r["tv"])[:15]],
            "strong_hand_folds": [describe(r) for r in sorted(strong_folds, key=lambda r: -r["jev_family"]["fold"])],
            "river_raises": [describe(r) for r in river_raises]}


async def load(plan: list[dict], answers_path: Path) -> tuple[dict, dict]:
    rows = [json.loads(line) for line in Path(answers_path).read_text().splitlines()]
    jev = {r["request_hash"]: r["response"]["answers"]["action"]["probabilities"] for r in rows if r["response"]}
    cfr, advisor = {}, CFRAdvisor("cfr-v2-adapt")
    for request in plan:
        b = body(request)
        cfr[request_hash(b)] = (await advisor(b))["answers"]["action"]["probabilities"]
    return jev, cfr


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("answers", type=Path); p.add_argument("--plan", type=Path, default=PLAN)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    plan = read_plan(a.plan)
    result = review(plan, *asyncio.run(load(plan, a.answers)))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("decisions", "size_split", "uniformity")}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
