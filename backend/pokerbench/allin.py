"""Experimental all-in defense on top of the V2 adaptive overlay.

Uses only public counters: the opponent's hands played and how many of them
contained an all-in (exposed under ``public_statistics`` as ``all_in``), plus
the usual PFR. Hidden cards are never used.

Facing an all-in or a bet of at least half the effective stack, preflop only:
1. shove frequency f = (all_in + 0.05 x 10) / (hands + 10): a weak 5 % prior
   worth 10 hands, so a frequent shover is recognized after a few hands;
2. the opponent's shoving range follows one of two explicit hypotheses:
   ``top``: their top-f hands by equity against a random hand (selective);
   ``any``: any two cards (an indiscriminate shover). No hypothesis is right in
   general; the range shapes the calling threshold, so both are evaluated;
3. our equity against that range is estimated by Monte Carlo, and we call iff
   equity >= to_call / (pot + to_call) + 0.02, using the real amount to call.
The rule acts only when f >= 15 % (TAG-like opponents stay below), otherwise
and in every other spot the V2 adaptive overlay plays unchanged. Postflop
shoves are left to the overlay: the preflop range model does not transfer.
"""
from .adaptive import AdaptiveCFRAgent
from .holdem_abstraction import DECK, _CARD, _EVALUATOR

PRIOR_SHOVE, PRIOR_HANDS, ACTIVE_FROM, MARGIN, SAMPLES = 0.05, 10, 0.15, 0.02, 300
_COMBOS = None


def shove_frequency(observation) -> float:
    stats = observation.get("public_statistics") or {}
    other = next((s["id"] for s in observation["seats"] if s["id"] != observation["actor"]), None)
    row = stats.get(other) or {}
    return (row.get("all_in", 0) + PRIOR_SHOVE * PRIOR_HANDS) / (row.get("hands", 0) + PRIOR_HANDS)


def ranked_combos(preflop_equity):
    """All 1,326 starting hands, strongest first by equity against a random hand."""
    global _COMBOS
    if _COMBOS is None:
        from .holdem_abstraction import hand_class
        combos = [(a, b) for i, a in enumerate(DECK) for b in DECK[i + 1:]]
        _COMBOS = sorted(combos, key=lambda c: (-preflop_equity[hand_class(c)], c))
    return _COMBOS


def equity_against_top(hole, fraction, preflop_equity, rng, samples=SAMPLES) -> float:
    combos = ranked_combos(preflop_equity)
    blocked = set(hole)
    top = [c for c in combos[:max(1, round(fraction * len(combos)))] if not blocked & set(c)]
    if not top:
        return 0.0
    own = [_CARD[c] for c in hole]
    score = 0.0
    for _ in range(samples):
        other = rng.choice(top)
        deck = [c for c in DECK if c not in blocked and c not in other]
        board = [_CARD[c] for c in rng.sample(deck, 5)]
        mine, theirs = _EVALUATOR.evaluate(board, own), _EVALUATOR.evaluate(board, [_CARD[c] for c in other])
        score += 1 if mine < theirs else 0.5 if mine == theirs else 0
    return score / samples


def facing_all_in(observation) -> bool:
    call = observation["to_call"]
    if not call:
        return False
    hero = next(s for s in observation["seats"] if s["id"] == observation["actor"])
    last = observation["history"][-1] if observation["history"] else {}
    return bool(last.get("all_in")) or call >= (hero["stack"] + hero["bet"]) / 2


class AllInAwareAgent(AdaptiveCFRAgent):
    def __init__(self, base, range_model: str = "top"):
        if range_model not in ("top", "any"):
            raise ValueError("range_model must be 'top' or 'any'")
        super().__init__(base)
        self.range_model = range_model
        self.overrides = 0

    async def choose_action(self, observation: dict) -> str:
        if observation["street"] == "preflop" and facing_all_in(observation):
            f = shove_frequency(observation)
            if f >= ACTIVE_FROM:
                hero = next(s for s in observation["seats"] if s["id"] == observation["actor"])
                actions = {a["kind"]: a for a in observation["legal_actions"]}
                if "call" in actions and "fold" in actions:
                    # Keep the base agent's random stream in step with the overlay path.
                    self.base.distribution(observation)
                    call = observation["to_call"]
                    price = call / (observation["pot"] + call)
                    width = f if self.range_model == "top" else 1.0
                    equity = equity_against_top(hero["cards"], width, self.base.abs.preflop_equity, self.base.rng)
                    self.overrides += 1
                    self.base.stats["decisions"] += 1
                    return actions["call" if equity >= price + MARGIN else "fold"]["id"]
        return await super().choose_action(observation)
