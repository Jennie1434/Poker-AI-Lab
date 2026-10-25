"""Kuhn and Leduc poker: small games with exactly computable exploitability.

They validate the CFR machinery before any Hold'em abstraction. Histories are
immutable tuples. Information set keys contain only the acting player's private
card, public cards and the public action history; never the opponent's card.
"""
from itertools import permutations

KUHN_CARDS = ("J", "Q", "K")
KUHN_VALUE = -1 / 18  # player-0 equilibrium value (Kuhn 1950)


class KuhnPoker:
    """Ante 1, one bet of 1. Actions: p (pass/check/fold), b (bet/call)."""

    name = "kuhn"
    TERMINAL = ("pp", "bp", "bb", "pbp", "pbb")

    def root(self):
        return ((), "")

    def is_chance(self, h):
        return not h[0]

    def chance_outcomes(self, h):
        deals = list(permutations(range(3), 2))
        return [(deal, 1 / len(deals)) for deal in deals]

    def child(self, h, action):
        cards, history = h
        return (action, history) if not cards else (cards, history + action)

    def is_terminal(self, h):
        return bool(h[0]) and h[1] in self.TERMINAL

    def player(self, h):
        return len(h[1]) % 2

    def actions(self, h):
        return ("p", "b")

    def infoset(self, h):
        return KUHN_CARDS[h[0][self.player(h)]] + ":" + h[1]

    def utility(self, h):
        cards, history = h
        winner = 1 if cards[0] > cards[1] else -1
        if history == "bp":
            return 1
        if history == "pbp":
            return -1
        return winner * (2 if "b" in history else 1)


class LeducPoker:
    """Leduc Hold'em (Southey et al. 2005).

    Six cards J,J,Q,Q,K,K; ante 1; one private card each; a public card after
    the first round. Raise sizes 2 then 4, at most two raises per round, player 0
    acts first in each round. Actions: f fold, c check/call, r bet/raise. A pair
    with the public card wins, else the higher rank; equal ranks split.
    History: (private deal, public card or None, (round-1 actions, round-2 actions)).
    """

    name = "leduc"
    RANKS = "JQK"
    RAISE = (2, 4)
    MAX_RAISES = 2

    @staticmethod
    def rank(card):
        return card // 2

    def root(self):
        return (None, None, ("",))

    @staticmethod
    def _round_state(actions):
        """(complete, raises, outstanding_for_actor) for one betting round."""
        raises, outstanding = 0, 0
        for i, a in enumerate(actions):
            if a == "r":
                raises += 1
                outstanding = 1
            elif a == "c":
                if outstanding or i > 0:
                    return True, raises, 0
            elif a == "f":
                return True, raises, 0
        return False, raises, outstanding

    def is_chance(self, h):
        deal, public, rounds = h
        if deal is None:
            return True
        if public is None and len(rounds) == 1:
            complete, _, _ = self._round_state(rounds[0])
            return complete and not rounds[0].endswith("f")
        return False

    def chance_outcomes(self, h):
        deal, public, rounds = h
        if deal is None:
            deals = list(permutations(range(6), 2))
            return [(d, 1 / len(deals)) for d in deals]
        remaining = [c for c in range(6) if c not in deal]
        return [(c, 1 / len(remaining)) for c in remaining]

    def child(self, h, action):
        deal, public, rounds = h
        if deal is None:
            return (action, None, rounds)
        if self.is_chance(h):
            return (deal, action, rounds + ("",))
        return (deal, public, rounds[:-1] + (rounds[-1] + action,))

    def is_terminal(self, h):
        deal, public, rounds = h
        if deal is None:
            return False
        if rounds[-1].endswith("f"):
            return True
        return len(rounds) == 2 and self._round_state(rounds[1])[0]

    def player(self, h):
        return len(h[2][-1]) % 2

    def actions(self, h):
        _, raises, outstanding = self._round_state(h[2][-1])
        result = ("f", "c") if outstanding else ("c",)
        return result + ("r",) if raises < self.MAX_RAISES else result

    def infoset(self, h):
        deal, public, rounds = h
        own = self.RANKS[self.rank(deal[self.player(h)])]
        board = self.RANKS[self.rank(public)] if public is not None else ""
        return f"{own}{board}:{'/'.join(rounds)}"

    def contributions(self, h):
        spent = [1, 1]
        for index, actions in enumerate(h[2]):
            size = self.RAISE[index]
            bets = [0, 0]
            for i, a in enumerate(actions):
                p = i % 2
                if a == "c":
                    bets[p] = bets[1 - p]
                elif a == "r":
                    bets[p] = bets[1 - p] + size
            spent = [spent[0] + bets[0], spent[1] + bets[1]]
        return spent

    def utility(self, h):
        deal, public, rounds = h
        spent = self.contributions(h)
        last = rounds[-1]
        if last.endswith("f"):
            folder = (len(last) - 1) % 2
            return -spent[0] if folder == 0 else spent[1]
        r0, r1, board = self.rank(deal[0]), self.rank(deal[1]), self.rank(public)
        s0 = (2, r0) if r0 == board else (1, r0)
        s1 = (2, r1) if r1 == board else (1, r1)
        if s0 == s1:
            return 0.0
        return spent[1] if s0 > s1 else -spent[0]


GAMES = {"kuhn": KuhnPoker, "leduc": LeducPoker}
