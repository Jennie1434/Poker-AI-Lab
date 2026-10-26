"""Abstraction V2: more raise sizes and draw-aware buckets; V1 stays unchanged.

Differences from ``holdem-hu-abstract-v1``:
- raise sizes: an opening bet or raise may be half pot ``h``, pot ``r`` or, postflop,
  1.5x pot ``o``; facing a raise only pot ``r``; all-in ``a`` always; each equals a
  size PokerKit offers in the benchmark format;
- flop/turn buckets: 6 equity buckets x {no draw, flush draw or open-ended
  straight draw} = 12; river: 8 equity buckets; preflop: the V1 table;
- opponent raises are translated to the nearest abstract size by pot
  fraction (log distance) instead of a single symbol;
- same depth caps: 2 sized raises and 3 raises (all-in included) per street;
- action recall: earlier streets are summarized by their raise count (0-3),
  the current street keeps its exact action sequence.

Still imperfect recall for cards and still not a GTO strategy for full NLHE.
"""
from fractions import Fraction
import math

from .agents import TightAggressiveAgent
from .holdem_abstraction import (BB, BOARD_AT, SB, STACK, STREETS, UNIT, Abstraction, CFRAgent,
                                 HoldemAbstractGame, equity, hand_class, infoset_key, postflop_bucket)

V2_CONFIG = {"version": 2, "sizes": {"h": "1/2", "r": "1", "o": "3/2"}, "postflop_only": ["o"],
             "equity_buckets": 6, "river_buckets": 8, "postflop_buckets": 12}


def sized_target(committed, street_bet, player, fraction: Fraction) -> int:
    """Raise-to amount, rounded exactly like the engine's pot-fraction options."""
    to_call = street_bet[1 - player] - street_bet[player]
    pot = committed[0] + committed[1]
    value = street_bet[player] + to_call + round(fraction * (pot + to_call))
    return max(UNIT, round(value / UNIT) * UNIT)


class AbstractionV2(Abstraction):
    def __init__(self, config: dict | None = None, preflop: dict | None = None):
        super().__init__({**V2_CONFIG, **(config or {})}, preflop)

    def sizes(self, street, opening=True):
        if not opening:
            return [("r", Fraction(self.config["sizes"]["r"]))]
        # Canonical order (smallest fraction first): it must not depend on dict
        # order, which a JSON round trip with sorted keys changes.
        return sorted(((s, Fraction(f)) for s, f in self.config["sizes"].items()
                       if street > 0 or s not in self.config["postflop_only"]), key=lambda item: (item[1], item[0]))

    def bucket(self, hole, board, rng) -> int:
        if not board:
            return self.preflop[hand_class(hole)]
        value = equity(hole, board, rng, self.config["postflop_samples"])
        if len(board) == 5:
            return postflop_bucket(value, self.config["river_buckets"])
        draw = TightAggressiveAgent.has_draw(list(hole), list(board))
        return postflop_bucket(value, self.config["equity_buckets"]) * 2 + int(draw)


def legal_v2(abstraction, committed, street_bet, player, street, raises, sized_raises):
    config = abstraction.config
    opp = 1 - player
    to_call = street_bet[opp] - street_bet[player]
    remaining = STACK - committed[player]
    actions = ["f"] if to_call > 0 else []
    actions.append("c")
    if remaining > to_call and STACK - committed[opp] > 0 and raises < config["max_raises"]:
        if sized_raises < config["max_pot_raises"]:
            seen = set()
            for symbol, fraction in abstraction.sizes(street, raises == 0):
                target = sized_target(committed, street_bet, player, fraction)
                if target - street_bet[player] < remaining and target not in seen:
                    seen.add(target)
                    actions.append(symbol)
        actions.append("a")
    return tuple(actions)


def v2_key(player, street, bucket, history, legal) -> str:
    # The legal abstract actions disambiguate states that share a summarized history.
    prior = "".join(str(min(3, sum(symbol in "hroa" for symbol in actions))) for actions in history[:-1])
    return f"{'BO'[player]}{street}{bucket}:{prior}|{history[-1]}#{''.join(legal)}"


class HoldemAbstractGameV2(HoldemAbstractGame):
    name = "holdem-hu-abstract-v2"

    def infoset(self, h):
        return v2_key(h.player, h.street, h.deal[0][h.player][h.street], h.history, self.actions(h))

    def actions(self, h):
        return legal_v2(self.abs, h.committed, h.street_bet, h.player, h.street, h.raises, h.pot_raises)

    def child(self, h, action):
        if h is None or action in ("f", "c", "a"):
            return super().child(h, action)
        s = h.copy()
        p, opp = s.player, 1 - s.player
        s.history = s.history[:-1] + (s.history[-1] + action,)
        fraction = dict(self.abs.sizes(s.street, s.raises == 0))[action]
        pay = sized_target(s.committed, s.street_bet, p, fraction) - s.street_bet[p]
        s.committed[p] += pay
        s.street_bet[p] += pay
        s.acted[p], s.acted[opp] = True, False
        s.raises += 1
        s.pot_raises += 1
        s.player = opp
        return s


class CFRAgentV2(CFRAgent):
    """Same contract as V1; translates real raise sizes to the nearest abstract size."""

    def __init__(self, seed: int, policy: dict):
        super().__init__(seed, policy)
        self.abs = AbstractionV2(policy["abstraction"]["config"], policy["abstraction"]["preflop_equity"])

    def abstract_view(self, obs):
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        button = next(s["id"] for s in obs["seats"] if "BTN" in s["position"])
        index = lambda pid: 0 if pid == button else 1
        street = STREETS.index(obs["street"])
        committed, street_bet = [SB, BB], [SB, BB]
        per_street, current = [""] * (street + 1), 0
        raises = sized = 0
        for event in obs["history"]:
            at = STREETS.index(event["street"])
            if at != current:
                current, street_bet, raises, sized = at, [0, 0], 0, 0
            p = index(event["player"])
            if event["kind"] == "fold":
                symbol = "f"
            elif event["kind"] in ("check", "call"):
                symbol = "c"
            elif event["all_in"]:
                symbol = "a"
            else:
                symbol = self.nearest_size(committed, street_bet, p, at, event["to"], raises == 0)
            if symbol in "hroa":
                raises += 1
                sized += symbol != "a"
            committed[p] += event["pay"]
            street_bet[p] += event["pay"]
            per_street[at] += symbol
        if current != street:
            street_bet, raises, sized = [0, 0], 0, 0
        self.legal = legal_v2(self.abs, committed, street_bet, index(hero["id"]), street, raises, sized)
        bucket = self.abs.bucket(hero["cards"], obs["board"], self.rng)
        return index(hero["id"]), street, bucket, tuple(per_street), raises, sized

    def nearest_size(self, committed, street_bet, player, street, to, opening):
        to_call = street_bet[1 - player] - street_bet[player]
        pot = committed[0] + committed[1]
        increment = max(1, to - street_bet[player] - to_call)
        actual = increment / (pot + to_call)
        return min(self.abs.sizes(street, opening), key=lambda s: (abs(math.log(actual / float(s[1]))), s[0]))[0]

    def key(self, player, street, bucket, history):
        return v2_key(player, street, bucket, history, self.legal)

    def map_action(self, abstract, obs):
        if abstract in ("f", "c", "a"):
            return super().map_action(abstract, obs)
        actions = obs["legal_actions"]
        raises = [a for a in actions if a["kind"] == "raise" and not a["all_in"]] or \
                 [a for a in actions if a["kind"] == "raise"]
        if not raises:
            return super().map_action("c", obs)
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        call = next((a["pay"] for a in actions if a["kind"] == "call"), 0)
        street = STREETS.index(obs["street"])
        opening = not any(e["street"] == obs["street"] and e["kind"] == "raise" for e in obs["history"])
        fraction = dict(self.abs.sizes(street, opening))[abstract]
        target = round((hero["bet"] + call + round(fraction * (obs["pot"] + call))) / UNIT) * UNIT
        return min(raises, key=lambda a: (abs(a["to"] - target), a["to"]))["id"]


def agent_for(seed: int, policy: dict):
    """Pick the agent matching the policy's abstraction."""
    return CFRAgentV2(seed, policy) if policy["game"] == HoldemAbstractGameV2.name else CFRAgent(seed, policy)


def game_for(version: int, config: dict | None = None, preflop=None):
    if version == 2:
        abstraction = AbstractionV2(config, preflop)
        return abstraction, HoldemAbstractGameV2(abstraction)
    abstraction = Abstraction(config, preflop)
    return abstraction, HoldemAbstractGame(abstraction)
