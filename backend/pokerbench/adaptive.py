"""Exploitative overlay on a frozen CFR policy, driven by public statistics only.

The opponent's preflop raise frequency (PFR) comes from the public counters a
room or benchmark exposes (``public_statistics``); hidden cards are never used.
It is shrunk toward a 25 % prior worth 20 hands, so a few hands cannot trigger
the overlay. Against a very aggressive opponent (estimated PFR above 40 %,
full weight at 75 %), whose betting range is close to a random hand:

- facing a bet, fold probability moves to call when the hand's equity against a
  random hand beats the pot odds by 3 points (blind defense included);
- strong hands (equity >= 75 %) move half of their call mass to a raise;
- weak hands (equity < 35 %) halve their bets when not facing one: bluffing an
  opponent who rarely folds is not justified.

Below the threshold the base policy is played unchanged. The overlay is a
fixed, documented rule, not learned, and is not an equilibrium strategy.
"""
from .holdem_abstraction import hand_class

PRIOR_PFR, PRIOR_HANDS = 0.25, 20
LOW, HIGH = 0.40, 0.75


def opponent_pfr(observation) -> tuple[float, int]:
    stats = observation.get("public_statistics") or {}
    other = next((s["id"] for s in observation["seats"] if s["id"] != observation["actor"]), None)
    row = stats.get(other) or {}
    hands = row.get("hands", 0)
    return (row.get("pfr", 0) + PRIOR_PFR * PRIOR_HANDS) / (hands + PRIOR_HANDS), hands


def equity_estimate(agent, observation, bucket) -> float:
    """Equity against a random hand implied by the bucket (exact table preflop)."""
    if observation["street"] == "preflop":
        hero = next(s for s in observation["seats"] if s["id"] == observation["actor"])
        return agent.abs.preflop_equity[hand_class(hero["cards"])]
    config = agent.abs.config
    if config.get("version") == 2:
        if len(observation["board"]) == 5:
            return (bucket + 0.5) / config["river_buckets"]
        return (bucket // 2 + 0.5) / config["equity_buckets"]
    return (bucket + 0.5) / config["postflop_buckets"]


def adjust(actions, probabilities, weight, equity, price):
    """Pure function: the adjusted distribution over the same abstract actions."""
    p = dict(zip(actions, probabilities))
    raise_symbol = next((a for a in ("r", "a") if a in p), None)
    if "f" in p and "c" in p and equity >= price + 0.03:
        moved = weight * p["f"]
        p["f"] -= moved
        p["c"] += moved
    if equity >= 0.75 and "c" in p and raise_symbol and "f" in p:
        moved = weight * 0.5 * p["c"]
        p["c"] -= moved
        p[raise_symbol] += moved
    if "f" not in p and equity < 0.35:
        bets = [a for a in p if a in "hroa"]
        moved = sum(weight * 0.5 * p[a] for a in bets)
        for a in bets:
            p[a] *= 1 - weight * 0.5
        p["c"] += moved
    total = sum(p.values())
    return [p[a] / total for a in actions]


class AdaptiveCFRAgent:
    def __init__(self, base):
        self.base = base
        self.stats = base.stats
        self.adjusted = 0

    async def choose_action(self, observation: dict) -> str:
        actions, probabilities, bucket = self.base.distribution(observation)
        pfr, _ = opponent_pfr(observation)
        weight = min(1.0, max(0.0, (pfr - LOW) / (HIGH - LOW)))
        if actions is not None and weight > 0:
            call = observation["to_call"]
            price = call / (observation["pot"] + call) if call else 0.0
            probabilities = adjust(actions, probabilities, weight, equity_estimate(self.base, observation, bucket), price)
            self.adjusted += 1
        return self.base.sample(actions, probabilities, bucket, observation)
