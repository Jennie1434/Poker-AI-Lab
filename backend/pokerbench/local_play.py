"""Offline integration smoke run, not a statistical strength benchmark."""
import argparse
import asyncio
import json

from .agents import HeuristicAgent, RandomAgent, play_action
from .engine import Hand


async def run(hands: int = 100, deck_seed: int = 1234, policy_seed: int = 5678) -> dict:
    if hands < 1:
        raise ValueError("hands must be positive")
    agents = {"random": RandomAgent(policy_seed), "heuristic": HeuristicAgent()}
    profits = dict.fromkeys(agents, 0)
    decisions = 0
    for number in range(hands):
        hand = Hand(
            [{"id": name, "stack": 20000} for name in agents],
            button=number % 2, blinds=(50, 100, 0), seed=deck_seed + number,
            number=number + 1, chip_unit=50,
        )
        while hand.state.status:
            if len(hand.actions) >= 1000:
                raise RuntimeError("Hand exceeded the smoke-run decision limit")
            await play_action(hand, agents[hand.actor])
            decisions += 1
        for seat in hand.snapshot()["seats"]:
            profits[seat["id"]] += seat["payoff"]
        if sum(hand.state.stacks) != 40000 or sum(profits.values()) != 0:
            raise RuntimeError("Chip conservation failed")
    return {"hands": hands, "decisions": decisions, "profit_chips": profits,
            "big_blind_chips": 100, "rake": 0, "purpose": "integration smoke only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hands", type=int, default=100)
    parser.add_argument("--deck-seed", type=int, default=1234)
    parser.add_argument("--policy-seed", type=int, default=5678)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.hands, args.deck_seed, args.policy_seed)), sort_keys=True))


if __name__ == "__main__":
    main()
