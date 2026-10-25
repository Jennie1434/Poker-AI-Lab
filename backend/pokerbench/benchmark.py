"""Reproducible offline heads-up experiments; no network or private room data."""
import argparse
import asyncio
import csv
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import time

from .agents import EquityHeuristicAgent, HeuristicAgent, RandomAgent, TightAggressiveAgent, play_action
from .engine import Hand

ROOT = Path(__file__).resolve().parents[2]
BB = 100
POLICIES = ("random", "heuristic", "equity", "tag", "cfr")


def derive_seed(master: int, domain: str, hand: int) -> int:
    return int.from_bytes(hashlib.sha256(f"v1:{master}:{domain}:{hand}".encode()).digest()[:16], "big")


@dataclass(frozen=True)
class Config:
    hands: int = 10000
    agent_a: str = "random"
    agent_b: str = "heuristic"
    deck_seed: int = 1234
    policy_seed: int = 5678
    equity_samples: int = 64
    tag_samples: int = 64
    measure_time: bool = False
    rake_percent: str = "5"
    rake_cap_bb: str = "3"
    no_flop_no_drop: bool = True
    cfr_policy: str = ""

    def validate(self):
        if self.hands < 4 or self.hands % 2:
            raise ValueError("hands must be even and >= 4 (>= 10000 for a benchmark)")
        if self.agent_a not in POLICIES or self.agent_b not in POLICIES:
            raise ValueError("Unknown policy")
        if self.equity_samples < 1 or self.tag_samples < 1:
            raise ValueError("equity_samples must be positive")
        percent, cap = Decimal(self.rake_percent), Decimal(self.rake_cap_bb)
        if not percent.is_finite() or not cap.is_finite() or not 0 <= percent <= 100 or cap < 0:
            raise ValueError("Invalid rake percentage or cap")
        if "cfr" in (self.agent_a, self.agent_b) and not self.cfr_policy:
            raise ValueError("cfr policy requires --cfr-policy")


def make_agent(name, seed, samples, tag_samples=64, cfr_policy=""):
    if name == "random":
        return RandomAgent(seed)
    if name == "heuristic":
        return HeuristicAgent()
    if name == "equity":
        return EquityHeuristicAgent(seed, samples)
    if name == "tag":
        return TightAggressiveAgent(seed, tag_samples)
    if name == "cfr":
        from .holdem_abstraction import CFRAgent, cached_policy
        return CFRAgent(seed, cached_policy(cfr_policy))
    raise ValueError("Unknown policy")


def settle_rake(hand: Hand, cfg: Config) -> dict:
    """Counterfactual rake accounting on PokerKit's completed HU settlement.

    Equal matched contributions form the contested pot. Uncalled excess is
    returned, never raked. Allocate the drop proportionally to pot awards,
    using largest remainders for integer chips (stable seat-order tie break).
    """
    if hand.state.status or len(hand.seats) != 2:
        raise ValueError("Rake requires a completed heads-up hand")
    seats = hand.snapshot()["seats"]
    matched = min(hand.committed.values())
    pot = 2 * matched
    gross = {s["id"]: s["payoff"] for s in seats}
    payouts = {pid: profit + matched for pid, profit in gross.items()}
    if sum(gross.values()) != 0 or min(payouts.values()) < 0 or sum(payouts.values()) != pot:
        raise ValueError("Invalid heads-up settlement")
    saw_flop = len(hand.snapshot()["board"]) >= 3
    drop = 0
    if pot and (saw_flop or not cfg.no_flop_no_drop):
        raw = min(Decimal(pot) * Decimal(cfg.rake_percent) / 100,
                  Decimal(cfg.rake_cap_bb) * BB)
        drop = int(raw.to_integral_value(rounding=ROUND_FLOOR))
    charges = {pid: drop * payout // pot if pot else 0 for pid, payout in payouts.items()}
    remainder = drop - sum(charges.values())
    order = sorted(payouts, key=lambda pid: -(drop * payouts[pid] % pot) if pot else 0)
    for pid in order[:remainder]:
        charges[pid] += 1
    net = {pid: gross[pid] - charges[pid] for pid in gross}
    if sum(net.values()) != -drop:
        raise ValueError("Rake conservation failed")
    return {"gross": gross, "net": net, "rake": drop, "pot": pot, "saw_flop": saw_flop}


def performance(values: list[int]) -> dict:
    """CLT interval on independent, position-balanced two-hand block means."""
    if len(values) < 4 or len(values) % 2:
        raise ValueError("Need complete two-hand blocks")
    blocks = [(values[i] + values[i+1]) / (2 * BB) for i in range(0, len(values), 2)]
    mean = statistics.mean(blocks) * 100
    se = statistics.stdev(blocks) / math.sqrt(len(blocks)) * 100
    return {"profit_chips": sum(values), "profit_bb": sum(values) / BB,
            "bb_per_100": mean, "ci95_bb_per_100": [mean - 1.959963984540054 * se,
                                                       mean + 1.959963984540054 * se],
            "standard_error_bb_per_100": se,
            "stddev_hand_bb": statistics.stdev(v / BB for v in values),
            "stddev_block_mean_bb": statistics.stdev(blocks),
            "win_rate": sum(v > 0 for v in values) / len(values),
            "loss_rate": sum(v < 0 for v in values) / len(values),
            "break_even_rate": sum(v == 0 for v in values) / len(values)}


def summarize(rows: list[dict], cfg: Config) -> dict:
    if len(rows) != cfg.hands:
        raise ValueError("Incomplete experiment")
    result = {"completed_hands": len(rows), "independent_blocks": len(rows)//2,
              "rake_chips": sum(r["rake_chips"] for r in rows), "agents": {}}
    for seat, policy in (("a", cfg.agent_a), ("b", cfg.agent_b)):
        result["agents"][seat] = {"policy": policy,
            "button_hands": sum(r["button"] == seat for r in rows),
            "big_blind_hands": sum(r["button"] != seat for r in rows),
            "gross": performance([r[f"{seat}_gross_chips"] for r in rows]),
            "net": performance([r[f"{seat}_net_chips"] for r in rows])}
    return result


def fingerprint() -> dict:
    files = sorted((ROOT / "backend/pokerbench").glob("*.py")) + [ROOT / "pyproject.toml", ROOT / "frontend/package-lock.json"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
            "source_sha256": hashes, "python": platform.python_version(),
            "dependencies": {name: importlib.metadata.version(name) for name in ("pokerkit", "treys", "pokerbench")}}


async def experiment(cfg: Config, output: Path) -> dict:
    cfg.validate()
    # Refuse overwrite, including a previous failed/partial experiment.
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"schema_version": 1, "status": "running", "config": asdict(cfg),
                "rules": {"big_blind_chips": BB, "small_blind_chips": 50,
                          "stack_chips": 20000, "chip_unit": 50, "ante": 0,
                          "reset_stacks_each_hand": True, "duplicate_deals": False,
                          "rake_rounding": "floor to integer chip; proportional awards, largest remainder",
                          "rake_scope": "post-settlement fixed-policy counterfactual, no strategy adaptation"},
                "statistics": {"method": "normal CLT 95% CI on independent two-hand balanced block means",
                               "win_rate": "fraction of hands with strictly positive profit; ties separate",
                               "small_sample": cfg.hands < 10000},
                "provenance": fingerprint()}
    if cfg.cfr_policy:
        from .holdem_abstraction import resolve_policy
        manifest["provenance"]["cfr_policy_sha256"] = hashlib.sha256(resolve_policy(cfg.cfr_policy).read_bytes()).hexdigest()
    manifest_path = output / "experiment.json"
    def save():
        temporary = output / "experiment.tmp"
        temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        temporary.replace(manifest_path)
    save()
    rows = []
    timing = {seat: {"decisions": 0, "cpu_seconds": 0.0} for seat in ("a", "b")}
    try:
        with (output / "hands.csv").open("x", newline="") as hf, (output / "decisions.jsonl").open("x") as df:
            writer = csv.DictWriter(hf, fieldnames=["hand", "block", "button", "decisions", "saw_flop", "contested_pot_chips", "rake_chips", "a_gross_chips", "b_gross_chips", "a_net_chips", "b_net_chips"])
            writer.writeheader()
            for number in range(cfg.hands):
                agents = {seat: make_agent(policy, derive_seed(cfg.policy_seed, f"policy:{seat}", number), cfg.equity_samples, cfg.tag_samples, cfg.cfr_policy)
                          for seat, policy in (("a", cfg.agent_a), ("b", cfg.agent_b))}
                hand = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}],
                            button=number % 2, blinds=(50, BB, 0),
                            seed=derive_seed(cfg.deck_seed, "deck", number), number=number+1, chip_unit=50)
                while hand.state.status:
                    if len(hand.actions) >= 1000:
                        raise RuntimeError("Decision limit exceeded")
                    actor = hand.actor
                    # Only the actor's sanitized view is logged. This private trace
                    # is never embedded in the comparison dashboard or sent to agents.
                    observation = hand.observation()
                    started = time.process_time() if cfg.measure_time else 0
                    action = await play_action(hand, agents[actor])
                    if cfg.measure_time:
                        timing[actor]["cpu_seconds"] += time.process_time() - started
                        timing[actor]["decisions"] += 1
                    df.write(json.dumps({"hand": number+1, "decision": len(hand.actions),
                                         "actor": actor, "action": action, "observation": observation},
                                        separators=(",", ":")) + "\n")
                settled = settle_rake(hand, cfg)
                if sum(hand.state.stacks) != 40000:
                    raise RuntimeError("Chip conservation failed")
                row = {"hand": number+1, "block": number//2, "button": "a" if number % 2 == 0 else "b",
                       "decisions": len(hand.actions), "saw_flop": int(settled["saw_flop"]),
                       "contested_pot_chips": settled["pot"], "rake_chips": settled["rake"]}
                row.update({f"{seat}_{kind}_chips": settled[kind][seat]
                            for seat in ("a", "b") for kind in ("gross", "net")})
                rows.append(row)
                writer.writerow(row)
        manifest["summary"] = summarize(rows, cfg)
        if cfg.measure_time:
            manifest["decision_bridge_timing"] = timing
        manifest["artifacts_sha256"] = {name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                                       for name in ("hands.csv", "decisions.jsonl")}
        manifest["status"] = "complete"
        save()
        return manifest
    except BaseException:
        manifest["status"] = "failed"
        manifest["completed_hands"] = len(rows)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=10000)
    parser.add_argument("--agent-a", choices=POLICIES, default="random")
    parser.add_argument("--agent-b", choices=POLICIES, default="heuristic")
    parser.add_argument("--deck-seed", type=int, default=1234)
    parser.add_argument("--policy-seed", type=int, default=5678)
    parser.add_argument("--equity-samples", type=int, default=64)
    parser.add_argument("--tag-samples", type=int, default=64)
    parser.add_argument("--measure-time", action="store_true")
    parser.add_argument("--rake-percent", default="5")
    parser.add_argument("--rake-cap-bb", default="3")
    parser.add_argument("--no-flop-no-drop", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--cfr-policy", default="", help="frozen policy file for the cfr agent")
    parser.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    output = args.pop("output")
    if args["hands"] < 10000:
        parser.error("CLI benchmark requires at least 10000 hands; small runs are test-only")
    report = asyncio.run(experiment(Config(**args), output))
    print(json.dumps(report["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
