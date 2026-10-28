"""Cost model for Mission 7A: CPU per decision, API spend and sample sizes.

Only the CPU timings are measured here; prices, latencies and Slumbot pacing
are explicit inputs, never presented as observed values.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import time

Z95 = 1.959963984540054


def hands_for_halfwidth(sd_bb_per_hand: float, halfwidth_bb100: float) -> int:
    """Hands for a 95 % interval of +/- ``halfwidth`` bb/100 (independent hands)."""
    return math.ceil((Z95 * sd_bb_per_hand * 100 / halfwidth_bb100) ** 2)


def halfwidth(sd_bb_per_hand: float, hands: int) -> float:
    return Z95 * sd_bb_per_hand / math.sqrt(hands) * 100


def sd_from_interval(halfwidth_bb100: float, hands: int) -> float:
    """Per-hand standard deviation implied by a published interval."""
    return halfwidth_bb100 * math.sqrt(hands) / (Z95 * 100)


def api_cost(hands: int, decisions_per_hand: float, consult_rate: float, cny_per_decision: float) -> float:
    return hands * decisions_per_hand * consult_rate * cny_per_decision


def slumbot_hours(hands: int, requests_per_hand: float, min_interval: float = 0.5,
                  latency: float = 0.0, cpu_ms_per_decision: float = 0.0, decisions_per_hand: float = 0.0) -> float:
    """Lower bound on wall time for one paced session (no concurrency)."""
    per_hand = requests_per_hand * max(min_interval, latency) + decisions_per_hand * cpu_ms_per_decision / 1000
    return hands * per_hand / 3600


async def time_decisions(requests, policy: str) -> dict:
    """Measured CPU per decision for a local CFR entry on the given observations."""
    from .compare import CFRAdvisor
    advisor = CFRAdvisor(policy)
    start = time.process_time()
    for request in requests:
        await advisor({k: v for k, v in request.items() if k != "meta"})
    cpu = time.process_time() - start
    return {"policy": policy, "decisions": len(requests), "cpu_ms_per_decision": 1000 * cpu / max(1, len(requests))}


def report(requests, input_cny_per_million: float, output_cny_per_million: float, output_tokens: int,
           consult_rates: dict, slumbot_sd: float, local_sd: float) -> dict:
    from .compare import estimate
    # Hands where the opponent folded first leave no request: count hands by their numbers.
    played = {}
    for r in requests:
        played[r["meta"]["opponent"]] = max(played.get(r["meta"]["opponent"], 0), r["meta"]["hand"])
    decisions_per_hand = len(requests) / sum(played.values())
    timing = asyncio.run(time_decisions(requests, "cfr-v2-adapt"))
    price = estimate(requests, input_cny_per_million, output_cny_per_million, output_tokens)
    per_decision = price["expected_cny_per_decision"]
    sizes = (1000, 10000, 50000)
    return {
        "decisions_per_hand_hero": decisions_per_hand,
        "cfr": timing,
        "api_price_assumptions": price["assumptions"],
        "api_cny_per_decision": per_decision,
        "api_reserve_cny_per_decision": price["reserve_cny"] / price["requests"],
        "api_cny_by_rule": {rule: {str(n): api_cost(n, decisions_per_hand, rate, per_decision) for n in sizes}
                            for rule, rate in consult_rates.items()},
        "hands_needed": {
            "slumbot_unpaired": {str(w): hands_for_halfwidth(slumbot_sd, w) for w in (10, 20, 50)},
            "local_paired": {str(w): hands_for_halfwidth(local_sd, w) for w in (10, 20, 50)}},
        "slumbot_hours_lower_bound": {str(n): slumbot_hours(n, decisions_per_hand + 1, 0.5) for n in sizes},
        "sd_inputs_bb_per_hand": {"slumbot": slumbot_sd, "local_paired": local_sd},
    }


def main():
    from .compare import read_jsonl
    from .hybrid import Rule, consult_rate
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("requests", type=Path)
    p.add_argument("--input-cny-per-million", type=float, required=True)
    p.add_argument("--output-cny-per-million", type=float, required=True)
    p.add_argument("--output-tokens", type=int, default=300)
    p.add_argument("--slumbot-sd", type=float, default=round(sd_from_interval(14.0, 86000), 1),
                   help="bb/hand; default implied by robopoker's published +/-14.0 over 86 K hands")
    p.add_argument("--local-sd", type=float, default=15.9, help="bb/hand of a paired difference (Mission 6, vs TAG)")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    requests = read_jsonl(a.requests)
    rates = {"cfr": 0.0, "advisor": 1.0, "mix": 1.0}
    for threshold in (0.5, 0.7):
        rates[f"gate-{threshold}"] = consult_rate(requests, Rule("gate", threshold=threshold))["consult_rate"]
    result = report(requests, a.input_cny_per_million, a.output_cny_per_million, a.output_tokens, rates,
                    a.slumbot_sd, a.local_sd)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
