"""Offline strategic diagnosis of a CFR seat from benchmark decision logs.

Each hand is rebuilt from its recorded deck seed and actions. The opponent's
real cards are used here, after the fact, to measure how good the CFR seat's
decisions were; they never reach any agent. Outputs aggregate statistics only.
"""
import argparse
from collections import Counter, defaultdict
import json
from itertools import groupby
from pathlib import Path
import random

from treys import Card, Evaluator

from .benchmark import BB, Config, derive_seed
from .engine import Hand
from .holdem_abstraction import DECK, cached_policy
from .holdem_v2 import agent_for

POT_CLASSES = ((0, 5), (5, 20), (20, 60), (60, 150), (150, 401))
_EVAL = Evaluator()


def real_equity(own, other, board, rng, samples=100):
    """Equity of ``own`` against the opponent's actual cards (offline only)."""
    known = set(own) | set(other) | set(board)
    deck = [c for c in DECK if c not in known]
    runs = [()] if len(board) == 5 else [tuple(rng.sample(deck, 5 - len(board))) for _ in range(samples)]
    score = 0.0
    for run in runs:
        full = [Card.new(c) for c in list(board) + list(run)]
        a, b = _EVAL.evaluate(full, [Card.new(c) for c in own]), _EVAL.evaluate(full, [Card.new(c) for c in other])
        score += 1 if a < b else 0.5 if a == b else 0
    return score / len(runs)


def pot_class(pot_bb):
    return next(f"{lo}-{hi - 1 if hi == 401 else hi}" for lo, hi in POT_CLASSES if lo <= pot_bb < hi)


def diagnose(folders, seat="a"):
    rng = random.Random(20261026)
    by_pot = defaultdict(lambda: Counter())
    showdown = Counter()
    facing = defaultdict(lambda: {"n": 0, "fold": 0, "call": 0, "raise": 0, "equity_call": 0.0, "equity_fold": 0.0,
                                  "price": 0.0})
    sizes = defaultdict(lambda: {"n": 0, "fold_response": 0, "net_chips": 0})
    draws = Counter()
    preflop = Counter()
    position = defaultdict(lambda: Counter())
    hands_total = 0
    for folder in folders:
        manifest = json.loads((folder / "experiment.json").read_text())
        cfg = Config(**manifest["config"])
        policy = cached_policy(cfg.cfr_policy)
        with (folder / "decisions.jsonl").open() as f:
            for number, entries in groupby((json.loads(line) for line in f), key=lambda e: e["hand"]):
                index = number - 1
                hand = Hand([{"id": "a", "stack": 200 * BB}, {"id": "b", "stack": 200 * BB}], index % 2, (BB // 2, BB, 0),
                            derive_seed(cfg.deck_seed, "deck", index), number, chip_unit=50)
                agent = agent_for(0, policy)
                other = "b" if seat == "a" else "a"
                mine, theirs = hand.original_holes[seat], hand.original_holes[other]
                first_bet = {}
                flop_draw = None
                vpip = pfr = False
                for entry in entries:
                    obs = entry["observation"]
                    actor = entry["actor"]
                    action = next(a for a in obs["legal_actions"] if a["id"] == entry["action"])
                    street = obs["street"]
                    if actor == seat:
                        _, st, bucket, _, _, _ = agent.abstract_view(obs)
                        if street == "flop" and flop_draw is None:
                            flop_draw = bucket % 2 == 1
                        if street == "preflop":
                            vpip |= action["kind"] in ("call", "raise") and not (action["kind"] == "call" and obs["to_call"] == 0)
                            pfr |= action["kind"] == "raise"
                        if street != "preflop" and obs["to_call"]:
                            row = facing[street]
                            eq = real_equity(mine, theirs, obs["board"], rng)
                            row["n"] += 1
                            row["price"] += obs["to_call"] / (obs["pot"] + obs["to_call"])
                            kind = "raise" if action["kind"] == "raise" else action["kind"]
                            row[kind] += 1
                            if kind == "call":
                                row["equity_call"] += eq
                            elif kind == "fold":
                                row["equity_fold"] += eq
                        if street != "preflop" and action["kind"] == "raise" and street not in first_bet and not obs["to_call"]:
                            pot = obs["pot"]
                            fraction = (action["to"] - next(s for s in obs["seats"] if s["id"] == obs["actor"])["bet"]) / pot
                            label = "all-in" if action["all_in"] else "1/2" if fraction < 0.75 else "pot" if fraction < 1.25 else "1.5x"
                            first_bet[street] = label
                    elif street != "preflop" and street in first_bet and first_bet[street] != "answered":
                        sizes[(street, first_bet[street])]["n"] += 1
                        sizes[(street, first_bet[street])]["fold_response"] += action["kind"] == "fold"
                        first_bet[street] = "answered"
                    hand.apply(entry["action"])
                final = hand.snapshot(reveal=True)
                net = next(s["payoff"] for s in final["seats"] if s["id"] == seat)
                pot_bb = 2 * min(hand.committed.values()) / BB
                cls = pot_class(pot_bb)
                went_down = not hand.folded
                by_pot[cls]["hands"] += 1
                by_pot[cls]["net_chips"] += net
                by_pot[cls]["won"] += net > 0
                by_pot[cls]["showdowns"] += went_down
                showdown["showdown_net" if went_down else "no_showdown_net"] += net
                showdown["showdown_hands" if went_down else "no_showdown_hands"] += 1
                if flop_draw is not None:
                    draws[f"{'draw' if flop_draw else 'no_draw'}_hands"] += 1
                    draws[f"{'draw' if flop_draw else 'no_draw'}_net"] += net
                preflop["hands"] += 1
                preflop["vpip"] += vpip
                preflop["pfr"] += pfr
                pos = "BTN" if (index % 2 == 0) == (seat == "a") else "BB"
                position[pos]["hands"] += 1
                position[pos]["net_chips"] += net
                hands_total += 1
    # Attribute first-bet net to sizes in a second view: aggregate only counts here.
    return {
        "hands": hands_total,
        "by_pot": {k: {**v, "bb_per_100_contribution": 100 * v["net_chips"] / BB / hands_total,
                       "win_rate": v["won"] / v["hands"]} for k, v in sorted(by_pot.items(), key=lambda x: int(x[0].split('-')[0]))},
        "showdown": {"showdown_bb_per_100": 100 * showdown["showdown_net"] / BB / hands_total,
                     "no_showdown_bb_per_100": 100 * showdown["no_showdown_net"] / BB / hands_total,
                     "showdown_share": showdown["showdown_hands"] / hands_total},
        "facing_bets": {st: {"decisions": r["n"], "fold_rate": r["fold"] / r["n"], "call_rate": r["call"] / r["n"],
                             "raise_rate": r["raise"] / r["n"], "mean_price": r["price"] / r["n"],
                             "mean_real_equity_when_calling": r["equity_call"] / r["call"] if r["call"] else None,
                             "mean_real_equity_when_folding": r["equity_fold"] / r["fold"] if r["fold"] else None}
                        for st, r in facing.items()},
        "first_bet_sizes": {f"{st}:{size}": {"bets": r["n"], "opponent_fold_rate": r["fold_response"] / r["n"]}
                            for (st, size), r in sorted(sizes.items())},
        "flop_draws": {k: (100 * draws[f"{k}_net"] / BB / draws[f"{k}_hands"] if draws[f"{k}_hands"] else None)
                       for k in ("draw", "no_draw")} | {"draw_share": draws["draw_hands"] / max(1, draws["draw_hands"] + draws["no_draw_hands"])},
        "preflop": {"vpip": preflop["vpip"] / preflop["hands"], "pfr": preflop["pfr"] / preflop["hands"]},
        "position_bb_per_100": {p: 100 * v["net_chips"] / BB / v["hands"] for p, v in position.items()},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folders", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = diagnose(a.folders)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
