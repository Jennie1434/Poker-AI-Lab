"""Read-only audit of a human-versus-AI room from its owner's history export.

Input: the JSON returned by ``GET /api/rooms/{id}/history?limit=200`` (owner
only; opponents' cards appear only when shown at showdown). Nothing is
written back and no game result is changed. Bluffs can only be identified
when the bettor's cards were revealed; unrevealed hands are counted separately.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from treys import Card, Evaluator

STREETS = ("preflop", "flop", "turn", "river")
_EVAL = Evaluator()


def made_hand(cards, board):
    """Treys rank class of the final hand (1 = straight flush ... 9 = high card)."""
    if len(board) < 3 or "??" in cards:
        return None
    return _EVAL.get_rank_class(_EVAL.evaluate([Card.new(c) for c in board], [Card.new(c) for c in cards]))


def audit(history: dict, big_blind: int = 100) -> dict:
    hands = sorted(history["hands"], key=lambda h: h["number"])
    players = sorted({p["id"] for h in hands for p in h["players"]})
    seat = {pid: defaultdict(Counter) for pid in players}
    pots = Counter()
    for h in hands:
        pot_bb = h["pot"] / big_blind
        pots["<5 BB" if pot_bb < 5 else "5-20 BB" if pot_bb < 20 else "20-60 BB" if pot_bb < 60 else ">=60 BB"] += 1
        positions = {p["id"]: p["position"] for p in h["players"]}
        cards = {p["id"]: p["cards"] for p in h["players"]}
        payoff = {p["id"]: p["payoff"] or 0 for p in h["players"]}
        for a in h["actions"]:
            pid = a["player"]
            row = seat[pid][a["street"]]
            row["decisions"] += 1
            row[a["kind"]] += 1
            is_facing = a["pay"] > 0 if a["kind"] in ("call", "raise", "fold") else False
            if a["kind"] == "fold" or (a["kind"] in ("call", "raise") and is_facing):
                row["facing_bet"] += 1
                row["fold_facing_bet"] += a["kind"] == "fold"
                row["raise_facing_bet"] += a["kind"] == "raise"
        for pid in players:
            stats = seat[pid]["hand"]
            stats["hands"] += 1
            stats["net_chips"] += payoff.get(pid, 0)
            stats["won"] += payoff.get(pid, 0) > 0
            mine = [a for a in h["actions"] if a["player"] == pid]
            stats["vpip"] += any(a["street"] == "preflop" and a["kind"] in ("call", "raise") and a["pay"] > 0 for a in mine)
            stats["pfr"] += any(a["street"] == "preflop" and a["kind"] == "raise" for a in mine)
            if positions.get(pid) == "BB":
                opened = any(a["street"] == "preflop" and a["kind"] == "raise" and a["player"] != pid for a in h["actions"])
                if opened:
                    stats["bb_facing_open"] += 1
                    stats["bb_fold_to_open"] += any(a["street"] == "preflop" and a["kind"] == "fold" for a in mine)
            aggressive = [a for a in mine if a["kind"] == "raise" and a["street"] != "preflop"]
            if aggressive:
                rank = made_hand(cards.get(pid, ["??"]), h["board"])
                stats["postflop_aggressive_hands"] += 1
                if rank is None:
                    stats["aggression_cards_unknown"] += 1
                elif rank >= 8:  # one pair or worse at the end of the hand
                    stats["aggression_with_weak_showdown_hand"] += 1
            if payoff.get(pid, 0) < 0 and any(a["kind"] == "fold" for a in mine):
                stats["folded_after_investing"] += 1
    result = {"hands": len(hands), "pot_sizes": dict(pots), "players": {}}
    for pid in players:
        s = seat[pid]["hand"]
        n = max(1, s["hands"])
        streets = {}
        for st in STREETS:
            r = seat[pid][st]
            if r["decisions"]:
                streets[st] = {"decisions": r["decisions"], "fold": r["fold"] / r["decisions"],
                               "check": r["check"] / r["decisions"], "call": r["call"] / r["decisions"],
                               "raise": r["raise"] / r["decisions"],
                               "fold_when_facing_bet": r["fold_facing_bet"] / r["facing_bet"] if r["facing_bet"] else None,
                               "raise_when_facing_bet": r["raise_facing_bet"] / r["facing_bet"] if r["facing_bet"] else None}
        result["players"][pid] = {
            "hands": s["hands"], "net_bb": s["net_chips"] / big_blind,
            "bb_per_100": 100 * s["net_chips"] / big_blind / n, "won_rate": s["won"] / n,
            "vpip": s["vpip"] / n, "pfr": s["pfr"] / n,
            "bb_fold_to_open": s["bb_fold_to_open"] / s["bb_facing_open"] if s["bb_facing_open"] else None,
            "postflop_aggressive_hands": s["postflop_aggressive_hands"],
            "aggression_revealed_weak": s["aggression_with_weak_showdown_hand"],
            "aggression_cards_unknown": s["aggression_cards_unknown"], "streets": streets}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("history", type=Path, help="room history JSON export")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = audit(json.loads(a.history.read_text()))
    text = json.dumps(result, indent=2, sort_keys=True)
    if a.output:
        a.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
