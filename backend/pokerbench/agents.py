"""Local agent boundary. Agents receive observations, never the authoritative Hand.

These trusted, in-process plugins are not a sandbox for untrusted Python code.
The async protocol also allows a future remote or trained policy implementation.
"""
from copy import deepcopy
import random
from typing import Protocol

from .engine import Hand


class Agent(Protocol):
    async def choose_action(self, observation: dict) -> str:
        """Return an offered action ID using only this actor's observation."""
        ...


class RandomAgent:
    """Uniform over offered action IDs, not over all possible raise amounts."""

    def __init__(self, seed: int):
        # Policy randomness must be independent of the private deck seed.
        self.rng = random.Random(seed)

    async def choose_action(self, observation: dict) -> str:
        actions = observation["legal_actions"]
        if not actions:
            raise ValueError("No legal actions")
        return self.rng.choice(actions)["id"]


class HeuristicAgent:
    """Weak passive baseline: check; call up to 1/3 of the pot; otherwise fold.

    This is a price threshold, not an equity estimate or a winning strategy.
    It deliberately ignores hand strength and never raises.
    """

    async def choose_action(self, observation: dict) -> str:
        actions = {a["kind"]: a for a in observation["legal_actions"]}
        if "check" in actions:
            return actions["check"]["id"]
        if "call" in actions and actions["call"]["pay"] * 3 <= observation["pot"]:
            return actions["call"]["id"]
        if "fold" in actions:
            return actions["fold"]["id"]
        raise ValueError("No supported legal action")


class EquityHeuristicAgent:
    """Heads-up Monte Carlo equity versus a uniform opponent, not a range solver.

    Only the actor's cards and public board enter the estimate. Randomness is
    local to the policy, independent of the real deck. Ties count as half wins.
    """

    def __init__(self, seed: int, samples: int = 64):
        if samples < 1:
            raise ValueError("samples must be positive")
        self.rng = random.Random(seed)
        self.samples = samples

    def estimate_equity(self, observation: dict) -> float:
        from treys import Card, Evaluator

        if len(observation["seats"]) != 2:
            raise ValueError("Equity heuristic supports heads-up only")
        hero = next(s for s in observation["seats"] if s["id"] == observation["actor"])
        hole = [Card.new(c) for c in hero["cards"]]
        board = [Card.new(c) for c in observation["board"]]
        known = set(hole + board)
        deck = [Card.new(r+s) for r in "23456789TJQKA" for s in "cdhs"
                if Card.new(r+s) not in known]
        evaluator = Evaluator()
        score = 0.0
        for _ in range(self.samples):
            draw = self.rng.sample(deck, 2 + 5 - len(board))
            runout = board + draw[2:]
            own = evaluator.evaluate(runout, hole)
            other = evaluator.evaluate(runout, draw[:2])
            score += 1 if own < other else 0.5 if own == other else 0
        return score / self.samples

    async def choose_action(self, observation: dict) -> str:
        equity = self.estimate_equity(observation)
        actions = observation["legal_actions"]
        raises = [a for a in actions if a["kind"] == "raise" and not a["all_in"]]
        if equity >= 0.65 and raises:
            return min(raises, key=lambda a: a["to"])["id"]
        for action in actions:
            if action["kind"] == "check":
                return action["id"]
            if action["kind"] == "call":
                price = action["pay"] / (observation["pot"] + action["pay"])
                if equity >= price + 0.02:
                    return action["id"]
        folds = [a for a in actions if a["kind"] == "fold"]
        if folds:
            return folds[0]["id"]
        raise ValueError("No supported legal action")


async def play_action(hand: Hand, agent: Agent) -> str:
    """Server-side bridge; reject illegal or stale choices before state mutation.

    The caller owns exclusive access to the hand while a decision is pending.
    A defensive copy prevents a plugin from mutating engine-owned card lists.
    """
    if hand.actor is None or not hand.state.status:
        raise ValueError("No acting player")
    turn = (hand.actor, len(hand.actions))
    legal = {action.id for action in hand.legal()}
    action_id = await agent.choose_action(deepcopy(hand.observation()))
    if turn != (hand.actor, len(hand.actions)):
        raise ValueError("Stale agent decision")
    if not isinstance(action_id, str) or action_id not in legal:
        raise ValueError("Agent returned an illegal action")
    hand.apply(action_id)
    return action_id


class TightAggressiveAgent(EquityHeuristicAgent):
    """Fixed HU TAG reference, not an equilibrium strategy or a learned range.

    Explicit preflop tiers; postflop equity, pressure-sensitive calls, sized
    value bets, limited draw semibluffs and river bluffs. Own RNG only.
    """

    @staticmethod
    def preflop_tier(cards: list[str]) -> int:
        ranks = sorted(("23456789TJQKA".index(c[0]) + 2 for c in cards), reverse=True)
        high, low = ranks
        suited = cards[0][1] == cards[1][1]
        if (high == low and high >= 12) or (high, low) == (14, 13):
            return 4  # QQ+, AK
        if (high == low and high >= 9) or (high, low) == (14, 12) or (suited and (high, low) in ((14, 11), (13, 12))):
            return 3  # 99-JJ, AQ, AJs, KQs
        if high == low or (high >= 11 and low >= 10) or (high == 14 and (suited or low >= 9)):
            return 2  # pairs, broadways, suited aces, A9+
        if suited and high >= 6 and high - low <= 1:
            return 1  # suited connectors 65s+
        return 0

    @staticmethod
    def has_draw(cards: list[str], board: list[str]) -> bool:
        if len(board) not in (3, 4):
            return False
        combined = cards + board
        flush = any(sum(c[1] == suit for c in combined) == 4 for suit in "cdhs")
        ranks = {"23456789TJQKA".index(c[0]) + 2 for c in combined}
        if 14 in ranks:
            ranks.add(1)
        straight = any(len(ranks & set(range(low, low + 5))) == 4 for low in range(1, 11))
        return flush or straight

    async def choose_action(self, observation: dict) -> str:
        obs = observation
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        actions = obs["legal_actions"]
        by_kind = {a["kind"]: a for a in actions}
        raises = [a for a in actions if a["kind"] == "raise"]
        street_history = [a for a in obs["history"] if a["street"] == obs["street"]]
        aggression = sum(a["kind"] == "raise" for a in street_history)
        own_raises = sum(a["kind"] == "raise" and a["player"] == obs["actor"] for a in street_history)
        bb = obs["big_blind"]
        call = by_kind.get("call", {}).get("pay", 0)

        def passive(allow_call):
            if "check" in by_kind:
                return by_kind["check"]["id"]
            if allow_call and "call" in by_kind:
                return by_kind["call"]["id"]
            if "fold" in by_kind:
                return by_kind["fold"]["id"]
            raise ValueError("No supported legal action")

        def sized_raise(target, max_pay, allow_all_in=False):
            candidates = [a for a in raises if a["pay"] <= max_pay and (allow_all_in or not a["all_in"])]
            if not candidates:
                return None
            return min(candidates, key=lambda a: (abs(a["to"] - target), a["to"]))["id"]

        if obs["street"] == "preflop":
            tier = self.preflop_tier(hero["cards"])
            if aggression == 0 and tier >= (1 if "BTN" in hero["position"] else 2):
                action = sized_raise(3 * bb, 4 * bb)
                if action:
                    return action
            if tier >= 3 and own_raises == 0 and aggression < 2:
                target = 3 * max(s["bet"] for s in obs["seats"])
                action = sized_raise(target, (40 if tier == 4 else 20) * bb)
                if action:
                    return action
            # Large commitments need premiums; speculative calls are tightly capped.
            limit = {0: 0, 1: 2, 2: 3, 3: 10, 4: 200}[tier] * bb
            return passive(call <= limit and tier > 0)

        equity = self.estimate_equity(obs)
        pot = obs["pot"]
        price = call / (pot + call) if call else 0
        pressure = call / max(pot, bb)
        capital = hero["stack"] + hero["committed"]
        # Uniform-range equity needs a margin against selective aggression.
        required = price + 0.08 + 0.08 * min(2, aggression) + 0.08 * min(1, pressure)
        if call > capital / 4:
            required = max(required, 0.75)
        if call > capital / 2:
            required = max(required, 0.85)
        value_threshold = 0.82 if call else 0.72
        if equity >= value_threshold and own_raises == 0:
            target = hero["bet"] + call + round(2 * (pot + call) / 3)
            action = sized_raise(target, capital if equity >= 0.92 else capital / 4, equity >= 0.92)
            if action:
                return action
        if not call and not own_raises and "BTN" in hero["position"]:
            draw = self.has_draw(hero["cards"], obs["board"])
            bluff = (draw and equity >= 0.35 and self.rng.random() < 0.20)
            if obs["street"] == "river" and equity < 0.40 and street_history and street_history[-1]["kind"] == "check":
                bluff = self.rng.random() < 0.08
            if bluff:
                action = sized_raise(hero["bet"] + round(pot / 2), capital / 10)
                if action:
                    return action
        return passive(equity >= required)


class HyperAggressiveAgent(EquityHeuristicAgent):
    """Test opponent modeled on an observed human: VPIP ~92 %, PFR ~88 %.

    Raises almost every preflop hand with mixed sizes, bets most flops when
    checked to, keeps firing with weak hands at fixed frequencies and folds
    only weak hands facing large bets. A stress test, not a winning strategy.
    """

    def __init__(self, seed: int, samples: int = 32, open_rate: float = 0.95, barrel_rate: float = 0.7):
        super().__init__(seed, samples)
        self.open_rate, self.barrel_rate = open_rate, barrel_rate

    def pick_raise(self, raises, shove_rate):
        normal = [a for a in raises if not a["all_in"]]
        if not normal or self.rng.random() < shove_rate:
            return max(raises, key=lambda a: a["to"])["id"]
        return self.rng.choice(normal[:4])["id"]

    async def choose_action(self, observation: dict) -> str:
        obs = observation
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        by_kind = {a["kind"]: a for a in obs["legal_actions"]}
        raises = [a for a in obs["legal_actions"] if a["kind"] == "raise"]
        call = by_kind.get("call", {}).get("pay", 0)
        if obs["street"] == "preflop":
            trash = TightAggressiveAgent.preflop_tier(hero["cards"]) == 0 and \
                max("23456789TJQKA".index(c[0]) for c in hero["cards"]) < 7
            if trash and call > 2 * obs["big_blind"] and "fold" in by_kind:
                return by_kind["fold"]["id"]
            if raises and self.rng.random() < self.open_rate and not (trash and self.rng.random() < 0.5):
                return self.pick_raise(raises, 0.04)
            return (by_kind.get("check") or by_kind.get("call") or by_kind["fold"])["id"]
        equity = self.estimate_equity(obs)
        if raises and (equity > 0.75 or self.rng.random() < self.barrel_rate * (0.6 if call else 1)):
            return self.pick_raise(raises, 0.15 if equity > 0.8 else 0.03)
        if "check" in by_kind:
            return by_kind["check"]["id"]
        price = call / (obs["pot"] + call)
        if equity >= price or self.rng.random() < 0.5:
            return by_kind["call"]["id"]
        return by_kind["fold"]["id"]


class CallingStationAgent(EquityHeuristicAgent):
    """Loose-passive test opponent: limps and calls almost everything, rarely raises."""

    async def choose_action(self, observation: dict) -> str:
        obs = observation
        by_kind = {a["kind"]: a for a in obs["legal_actions"]}
        raises = [a for a in obs["legal_actions"] if a["kind"] == "raise" and not a["all_in"]]
        if obs["street"] == "preflop":
            return (by_kind.get("check") or by_kind.get("call") or by_kind["fold"])["id"]
        equity = self.estimate_equity(obs)
        if equity > 0.85 and raises:
            return min(raises, key=lambda a: a["to"])["id"]
        if "check" in by_kind:
            return by_kind["check"]["id"]
        if equity > 0.2 or self.rng.random() < 0.3:
            return by_kind["call"]["id"]
        return by_kind["fold"]["id"]
