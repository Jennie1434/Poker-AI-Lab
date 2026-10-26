"""Abstraction V3: finer buckets, partial card recall, deeper and richer raises.

Built on V2 (which, like V1, stays unchanged), from the Mission 6 diagnosis:
- buckets: preflop 10, flop/turn 8 equity x draw = 16, river 10;
- partial recall: postflop keys also hold the preflop strength tier (3 levels),
  so the strategy can reason about its own range after the flop;
- facing a raise: half-pot ``h`` or pot ``r`` re-raise (V2: pot only);
- depth: up to 4 raises per street (V2: 3), 2 of them sized.
Still an abstraction, still not GTO for full no-limit Hold'em.
"""
from .holdem_abstraction import hand_class
from .holdem_v2 import AbstractionV2, CFRAgentV2, HoldemAbstractGameV2, legal_v2, v2_key
from fractions import Fraction

V3_CONFIG = {"version": 3, "preflop_buckets": 10, "equity_buckets": 8, "river_buckets": 10, "postflop_buckets": 16,
             "max_raises": 4, "facing_sizes": {"h": "1/2", "r": "1"}, "tiers": 3}


class AbstractionV3(AbstractionV2):
    def __init__(self, config: dict | None = None, preflop: dict | None = None):
        super().__init__({**V3_CONFIG, **(config or {})}, preflop)

    def sizes(self, street, opening=True):
        if not opening:
            return sorted(((s, Fraction(f)) for s, f in self.config["facing_sizes"].items()), key=lambda i: (i[1], i[0]))
        return super().sizes(street, opening)

    def tier(self, preflop_bucket: int) -> int:
        return preflop_bucket * self.config["tiers"] // self.config["preflop_buckets"]


def v3_key(player, street, bucket, tier, history, legal) -> str:
    base = v2_key(player, street, bucket, history, legal)
    return base if street == 0 else base.replace(":", f"t{tier}:", 1)


class HoldemAbstractGameV3(HoldemAbstractGameV2):
    name = "holdem-hu-abstract-v3"

    def infoset(self, h):
        buckets = h.deal[0][h.player]
        return v3_key(h.player, h.street, buckets[h.street], self.abs.tier(buckets[0]), h.history, self.actions(h))


class CFRAgentV3(CFRAgentV2):
    def __init__(self, seed: int, policy: dict):
        super().__init__(seed, policy)
        self.abs = AbstractionV3(policy["abstraction"]["config"], policy["abstraction"]["preflop_equity"])

    def abstract_view(self, obs):
        view = super().abstract_view(obs)
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        self.tier = self.abs.tier(self.abs.preflop[hand_class(hero["cards"])])
        return view

    def key(self, player, street, bucket, history):
        return v3_key(player, street, bucket, self.tier, history, self.legal)
