"""Mission 7B preregistered benchmark: hybrid ``gate(0.5)`` against CFR V2 adaptive alone.

Protocol, fixed before any hand of the main run:
- baseline: CFR V2 adaptive (V2 300k policy, public-statistics overlay);
- arm: ``HybridAgent`` on the same agent with ``Rule("gate", threshold=0.5)``:
  the advisor is consulted when CFR leaves its tree or its top action is
  below 50 %; elsewhere the hybrid plays CFR's own draw (same random stream);
- opponents: hyper, tag, station, equity; seeds never used before:
  decks 175001-175003, policies 185001-185003; strictly alternating button,
  200 BB reset each hand, public statistics exposed; both arms play identical
  deals and identical policy seeds, so the comparison is paired hand by hand;
- metric: net bb/100 at 5 % rake (cap 3 BB, no flop no drop); paired
  per-hand difference arm - baseline, 95 % CI on two-hand blocks, pooled over
  the three seeds;
- decision: the hybrid is accepted only if its paired difference has a CI
  entirely above zero against at least one opponent and entirely below zero
  against none; otherwise CFR V2 adaptive stays the reference.

Advisors:
- ``null``: CFR V2 adaptive itself, evaluated independently (own equity
  samples): no real effect is expected; it checks the harness and measures the
  paired noise used to size the Jev run;
- ``cfr-v3``: a different policy as stand-in: shows the harness detects change;
- ``jev``: TypeSafe Jev 1.14.0 (paid). Refused without ``--approve-paid-calls``
  and a USD ceiling; answers are cached per request, one worker only.
"""
import argparse
import asyncio
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

from .agents import play_action
from .benchmark import BB, Config, derive_seed, make_agent, performance, settle_rake, update_public_stats
from .costs import hands_for_halfwidth
from .engine import Hand

POLICY = "artifacts/mission5/policy-v2-72001-300000.json.gz"
OPPONENTS = ("hyper", "tag", "station", "equity")
SEEDS = ((175001, 185001), (175002, 185002), (175003, 185003))
THRESHOLD = 0.5
RAKE = Config(rake_percent="5", rake_cap_bb="3")
LOCAL_ADVISORS = ("null", "cfr-v3")


def make_advisor(name: str, seed: int, paid=None):
    from .compare import CFRAdvisor
    if name == "null":
        return CFRAdvisor("cfr-v2-adapt", seed)
    if name == "cfr-v3":
        return CFRAdvisor("cfr-v3", seed)
    if name == "jev":
        if paid is None:
            raise PermissionError("The Jev arm makes paid calls; see --approve-paid-calls")
        return paid
    raise ValueError(f"Unknown advisor {name}")


async def series(opponent: str, deck_seed: int, policy_seed: int, hands: int, advisor: str | None, paid=None) -> dict:
    """One seed against one opponent: per-hand net chips of seat a (5 % rake)."""
    from .holdem_abstraction import cached_policy
    from .holdem_v2 import agent_for
    from .hybrid import HybridAgent, Rule
    policy = cached_policy(POLICY)
    advice = make_advisor(advisor, policy_seed, paid) if advisor else None
    public, net, stats = {}, [], {"decisions": 0, "consulted": 0, "advisor_errors": 0, "cost_cny": 0.0}
    for number in range(hands):
        seed_a = derive_seed(policy_seed, "policy:a", number)
        if advice is None:
            hero = make_agent("cfr", seed_a, 64, cfr_policy=POLICY, cfr_adaptive=True)
        else:
            hero = HybridAgent(agent_for(seed_a, policy), advice, Rule("gate", threshold=THRESHOLD))
        agents = {"a": hero, "b": make_agent(opponent, derive_seed(policy_seed, "policy:b", number), 64)}
        hand = Hand([{"id": "a", "stack": 200 * BB}, {"id": "b", "stack": 200 * BB}], number % 2, (BB // 2, BB, 0),
                    derive_seed(deck_seed, "deck", number), number + 1, chip_unit=50)
        while hand.state.status:
            await play_action(hand, agents[hand.actor], public)
        update_public_stats(public, hand)
        net.append(settle_rake(hand, RAKE)["net"]["a"])
        if advice is not None:
            for key in stats:
                stats[key] += hero.stats[key]
    return {"opponent": opponent, "deck_seed": deck_seed, "policy_seed": policy_seed, "advisor": advisor or "baseline",
            "hands": hands, "net": net, "stats": stats}


def _job(args):
    return asyncio.run(series(*args))


def run_local(advisors, hands: int, workers: int, opponents=OPPONENTS, seeds=SEEDS) -> list[dict]:
    jobs = [(o, d, p, hands, a) for a in (None, *advisors) for o in opponents for d, p in seeds]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_job, jobs))


def analyze(results: list[dict], halfwidth: float = 20.0) -> dict:
    by = {(r["advisor"], r["opponent"], r["deck_seed"]): r for r in results}
    advisors = sorted({r["advisor"] for r in results} - {"baseline"})
    opponents = sorted({r["opponent"] for r in results})
    decks = sorted({r["deck_seed"] for r in results})
    out = {"baseline": {}, "arms": {}, "decision_rule": "accepted iff paired CI > 0 vs >= 1 opponent and < 0 vs none"}
    for o in opponents:
        out["baseline"][o] = performance([x for d in decks for x in by[("baseline", o, d)]["net"]])
    for a in advisors:
        arm, verdicts = {}, {}
        for o in opponents:
            base = [x for d in decks for x in by[("baseline", o, d)]["net"]]
            mine = [x for d in decks for x in by[(a, o, d)]["net"]]
            diff = [m - b for m, b in zip(mine, base)]
            paired = performance(diff)
            low, high = paired["ci95_bb_per_100"]
            verdicts[o] = "better" if low > 0 else "worse" if high < 0 else "inconclusive"
            stats = {k: sum(by[(a, o, d)]["stats"][k] for d in decks) for k in by[(a, o, decks[0])]["stats"]}
            arm[o] = {"hands": len(base), "hybrid": performance(mine), "paired_difference": paired, "verdict": verdicts[o],
                      "identical_hands": sum(m == b for m, b in zip(mine, base)) / len(base),
                      "consult_rate": stats["consulted"] / max(1, stats["decisions"]), "stats": stats,
                      "hands_for_halfwidth": hands_for_halfwidth(paired["stddev_hand_bb"], halfwidth)
                      if paired["stddev_hand_bb"] > 0 else 0}
        consulted = sum(v["stats"]["consulted"] for v in arm.values())
        errors = sum(v["stats"]["advisor_errors"] for v in arm.values())
        # Preregistered: more than 1 % failed consultations makes the arm invalid (it mostly played CFR).
        valid = errors <= 0.01 * consulted
        out["arms"][a] = {"opponents": arm, "valid": valid, "advisor_errors": errors, "consulted": consulted,
                          "accepted": valid and any(v == "better" for v in verdicts.values())
                          and not any(v == "worse" for v in verdicts.values())}
    return out


def jev_cost_plan(analysis: dict, usd_per_call: float, reference: str = "null") -> dict:
    """Jev calls and USD for a main run sized at ``hands_for_halfwidth``, from a local arm.

    The rule consults on CFR's distribution only, so a local arm's
    consultation rate is the Jev arm's rate until play diverges.
    """
    plan = {}
    for o, v in analysis["arms"][reference]["opponents"].items():
        per_hand = v["stats"]["consulted"] / v["hands"]
        hands = v["hands_for_halfwidth"]
        plan[o] = {"calls_per_hand": per_hand, "hands_needed": hands, "calls": round(hands * per_hand),
                   "usd": hands * per_hand * usd_per_call}
    return {"by_opponent": plan, "total_usd": sum(r["usd"] for r in plan.values()),
            "total_calls": sum(r["calls"] for r in plan.values()), "usd_per_call": usd_per_call}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("local", help="baseline and local stand-in advisors (free)")
    s.add_argument("--advisors", default="null,cfr-v3"); s.add_argument("--hands", type=int, default=2000)
    s.add_argument("--workers", type=int, default=4); s.add_argument("--output", type=Path, required=True)
    s = sub.add_parser("jev", help="PAID: the Jev arm (one worker, cached answers)")
    s.add_argument("--hands", type=int, required=True); s.add_argument("--output", type=Path, required=True)
    s.add_argument("--max-usd", type=float, required=True); s.add_argument("--approve-paid-calls", action="store_true")
    s.add_argument("--opponents", default=",".join(OPPONENTS))
    a = p.parse_args()
    if a.command == "local":
        advisors = [x for x in a.advisors.split(",") if x]
        if not set(advisors) <= set(LOCAL_ADVISORS):
            raise SystemExit("local advisors: " + ", ".join(LOCAL_ADVISORS))
        results = run_local(advisors, a.hands, a.workers)
        a.output.mkdir(parents=True, exist_ok=True)
        (a.output / "series.json").write_text(json.dumps(results))
        analysis = analyze(results)
        (a.output / "analysis.json").write_text(json.dumps(analysis, indent=1))
        print(json.dumps({k: {o: (v["paired_difference"]["bb_per_100"], v["paired_difference"]["ci95_bb_per_100"],
                                  v["consult_rate"]) for o, v in arm["opponents"].items()}
                          for k, arm in analysis["arms"].items()}, indent=1))
    else:
        asyncio.run(run_jev(a.hands, a.output, a.max_usd, a.approve_paid_calls,
                            opponents=tuple(x for x in a.opponents.split(",") if x)))


async def run_jev(hands: int, output: Path, max_usd: float, approve_paid_calls: bool = False, settings=None,
                  opponents=OPPONENTS) -> dict:
    if not approve_paid_calls:
        raise PermissionError("The Jev arm makes paid calls: pass --approve-paid-calls")
    from .compare import ProviderAdvisor
    from .config import Settings
    from .jev_pilot import jev_entry
    from .provider import Provider
    from .store import Store
    settings = settings or Settings()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    provider = Provider(settings, Store(str(output / "calls.db")))
    entry = jev_entry()
    if not provider.available(entry):
        raise PermissionError("JEV_API_KEY is not configured")
    advisor = ProviderAdvisor(provider, entry, max_usd * settings.pokerbench_usd_cny_rate, allow_paid=True,
                              run_id="mission7b-jev")
    if not set(opponents) <= set(OPPONENTS):
        raise ValueError("Unknown opponent")
    results = []
    for o in opponents:
        for d, s in SEEDS:
            results.append(await series(o, d, s, hands, "jev", advisor))
            results.append(await series(o, d, s, hands, None))
            (output / "series.json").write_text(json.dumps(results))
            if advisor.spent >= advisor.budget:
                raise RuntimeError("USD ceiling reached: the run is incomplete and must not be analysed as preregistered")
    analysis = analyze(results)
    (output / "analysis.json").write_text(json.dumps(analysis, indent=1))
    return analysis


if __name__ == "__main__":
    main()
