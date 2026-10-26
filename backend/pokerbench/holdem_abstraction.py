"""Heads-up no-limit Hold'em abstraction for MCCFR, and the agent that plays it.

The abstract game mirrors the benchmark format (200 BB stacks reset each hand,
blinds 0.5/1 BB, 50-chip unit) but limits it deliberately:
- actions: fold, check/call, one pot-sized raise ``r`` and all-in ``a``;
- depth: at most 2 pot raises and 3 raises (all-in included) per street;
- cards: 8 preflop buckets (equity vs a uniform hand, combo-weighted quantiles)
  and 8 postflop buckets (Monte Carlo equity vs a uniform hand, equal-width);
- imperfect recall: a key holds only the current street's bucket, plus the
  full abstract public betting history and the player's position.

Convergence of MCCFR in this abstraction says nothing about exploitability in
full no-limit Hold'em; the abstraction is not a GTO strategy. The agent maps
real observations onto this tree; PokerKit remains the only rules authority.
"""
import gzip
import hashlib
import json
from pathlib import Path
import random

from treys import Card, Evaluator

STACK, SB, BB, UNIT = 20000, 50, 100, 50
STREETS = ("preflop", "flop", "turn", "river")
BOARD_AT = (0, 3, 4, 5)
RANKS = "23456789TJQKA"
DECK = [r + s for r in RANKS for s in "cdhs"]
POLICY_FORMAT = "pokerbench-cfr-policy-v1"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = {"preflop_buckets": 8, "postflop_buckets": 8, "postflop_samples": 32,
                  "max_pot_raises": 2, "max_raises": 3, "preflop_table_samples": 4000,
                  "preflop_table_seed": 20261101}

_EVALUATOR = Evaluator()
_CARD = {c: Card.new(c) for c in DECK}


def hand_class(cards) -> str:
    """Strategic class among the 169: 'AA', 'AKs', 'AKo'."""
    a, b = sorted(cards, key=lambda c: RANKS.index(c[0]), reverse=True)
    if a[0] == b[0]:
        return a[0] + b[0]
    return a[0] + b[0] + ("s" if a[1] == b[1] else "o")


def equity(hole, board, rng, samples) -> float:
    """Monte Carlo equity against one uniformly random unknown hand."""
    known = set(hole) | set(board)
    deck = [_CARD[c] for c in DECK if c not in known]
    own, public = [_CARD[c] for c in hole], [_CARD[c] for c in board]
    missing = 5 - len(board)
    score = 0.0
    for _ in range(samples):
        draw = rng.sample(deck, 2 + missing)
        runout = public + draw[2:]
        mine, theirs = _EVALUATOR.evaluate(runout, own), _EVALUATOR.evaluate(runout, draw[:2])
        score += 1 if mine < theirs else 0.5 if mine == theirs else 0
    return score / samples


def preflop_table(samples: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    table = {}
    for i, high in enumerate(reversed(RANKS)):
        for low in reversed(RANKS[:len(RANKS) - i]):
            if high == low:
                table[high + low] = equity([high + "c", low + "d"], [], rng, samples)
            else:
                table[high + low + "s"] = equity([high + "c", low + "c"], [], rng, samples)
                table[high + low + "o"] = equity([high + "c", low + "d"], [], rng, samples)
    return table


def preflop_buckets(table: dict[str, float], count: int) -> dict[str, int]:
    """Combo-weighted quantiles: each bucket holds about 1326/count combinations."""
    combos = lambda k: 6 if len(k) == 2 else 4 if k[2] == "s" else 12
    ordered = sorted(table, key=lambda k: (table[k], k))
    result, seen = {}, 0
    for key in ordered:
        result[key] = min(count - 1, seen * count // 1326)
        seen += combos(key)
    return result


def postflop_bucket(value: float, count: int) -> int:
    return min(count - 1, int(value * count))


class Abstraction:
    def __init__(self, config: dict | None = None, preflop: dict[str, float] | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.preflop_equity = preflop or preflop_table(self.config["preflop_table_samples"],
                                                       self.config["preflop_table_seed"])
        self.preflop = preflop_buckets(self.preflop_equity, self.config["preflop_buckets"])

    def bucket(self, hole, board, rng) -> int:
        if not board:
            return self.preflop[hand_class(hole)]
        value = equity(hole, board, rng, self.config["postflop_samples"])
        return postflop_bucket(value, self.config["postflop_buckets"])

    def describe(self) -> dict:
        return {"config": self.config, "preflop_equity": self.preflop_equity}


class HoldemState:
    __slots__ = ("deal", "street", "committed", "street_bet", "acted", "player",
                 "history", "raises", "pot_raises", "winner", "folder")

    def copy(self):
        s = HoldemState.__new__(HoldemState)
        for name in self.__slots__:
            value = getattr(self, name)
            setattr(s, name, list(value) if isinstance(value, list) else value)
        return s


def legal_abstract(committed, street_bet, player, raises, pot_raises, config):
    """Abstract actions from chip state; shared by the game and the agent."""
    opp = 1 - player
    to_call = street_bet[opp] - street_bet[player]
    remaining = STACK - committed[player]
    actions = ["f"] if to_call > 0 else []
    actions.append("c")
    if remaining > to_call and STACK - committed[opp] > 0 and raises < config["max_raises"]:
        target = pot_raise_target(committed, street_bet, player)
        if pot_raises < config["max_pot_raises"] and target - street_bet[player] < remaining:
            actions.append("r")
        actions.append("a")
    return tuple(actions)


def pot_raise_target(committed, street_bet, player):
    to_call = street_bet[1 - player] - street_bet[player]
    pot = committed[0] + committed[1]
    raw = street_bet[player] + to_call + pot + to_call
    return max(UNIT, round(raw / UNIT) * UNIT)


class HoldemAbstractGame:
    """Player 0 is the button/small blind, player 1 the big blind."""

    name = "holdem-hu-abstract-v1"

    def __init__(self, abstraction: Abstraction):
        self.abs = abstraction

    def root(self):
        return None

    def is_chance(self, h):
        return h is None

    def chance_outcomes(self, h):
        raise NotImplementedError("Hold'em deals are sampled, not enumerated")

    def sample_chance(self, h, rng):
        cards = rng.sample(DECK, 9)
        holes, board = (cards[0:2], cards[2:4]), cards[4:]
        buckets = tuple(tuple(self.abs.bucket(holes[p], board[:BOARD_AT[s]], rng) for s in range(4))
                        for p in range(2))
        s0 = _EVALUATOR.evaluate([_CARD[c] for c in board], [_CARD[c] for c in holes[0]])
        s1 = _EVALUATOR.evaluate([_CARD[c] for c in board], [_CARD[c] for c in holes[1]])
        state = HoldemState()
        state.deal = (buckets, 1 if s0 < s1 else -1 if s0 > s1 else 0)
        state.street, state.committed, state.street_bet = 0, [SB, BB], [SB, BB]
        state.acted, state.player, state.history = [False, False], 0, ("",)
        state.raises = state.pot_raises = 0
        state.winner = state.folder = None
        return state

    def child(self, h, action):
        if h is None:
            return action
        s = h.copy()
        p, opp = s.player, 1 - s.player
        to_call = s.street_bet[opp] - s.street_bet[p]
        s.history = s.history[:-1] + (s.history[-1] + action,)
        if action == "f":
            s.folder = p
            return s
        if action == "c":
            pay = min(to_call, STACK - s.committed[p])
        elif action == "r":
            pay = pot_raise_target(s.committed, s.street_bet, p) - s.street_bet[p]
            s.pot_raises += 1
        else:
            pay = STACK - s.committed[p]
        s.committed[p] += pay
        s.street_bet[p] += pay
        s.acted[p] = True
        if action in "ra":
            s.raises += 1
            s.acted[opp] = False
        if s.acted[opp] and s.street_bet[0] == s.street_bet[1]:
            if STACK in s.committed or s.street == 3:
                s.winner = s.deal[1]
            else:
                s.street += 1
                s.street_bet, s.acted, s.player = [0, 0], [False, False], 1
                s.raises = s.pot_raises = 0
                s.history = s.history + ("",)
            return s
        s.player = opp
        return s

    def is_terminal(self, h):
        return h is not None and (h.folder is not None or h.winner is not None)

    def utility(self, h):
        if h.folder is not None:
            return (-h.committed[0] if h.folder == 0 else h.committed[1]) / BB
        return h.winner * h.committed[1] / BB

    def player(self, h):
        return h.player

    def actions(self, h):
        return legal_abstract(h.committed, h.street_bet, h.player, h.raises, h.pot_raises, self.abs.config)

    def infoset(self, h):
        return infoset_key(h.player, h.street, h.deal[0][h.player][h.street], h.history)


def infoset_key(player, street, bucket, history) -> str:
    return f"{'BO'[player]}{street}{bucket}:{'/'.join(history)}"


# Frozen policy and agent ----------------------------------------------
def export_policy(trainer, abstraction: Abstraction, path: Path, metadata: dict, digits: int = 4):
    strategy = {k: [round(p, digits) for p in v.values()] for k, v in trainer.average_strategy().items()}
    payload = {"format": POLICY_FORMAT, "game": HoldemAbstractGame.name, "iterations": trainer.iterations,
               "seed": trainer.seed, "abstraction": abstraction.describe(),
               "actions": {k: list(v) for k, v in sorted(trainer.actions.items())},
               "strategy": strategy, "metadata": metadata}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(body.encode()).hexdigest()
    if path.exists():
        raise FileExistsError(path)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f, sort_keys=True, separators=(",", ":"))


def load_policy(path: Path) -> dict:
    with gzip.open(path, "rt") as f:
        payload = json.load(f)
    body = {k: v for k, v in payload.items() if k != "sha256"}
    if payload.get("format") != POLICY_FORMAT or payload.get("sha256") != hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
        raise ValueError("Invalid or corrupted policy file")
    return payload


_POLICIES: dict[str, dict] = {}


def resolve_policy(path) -> Path:
    """Relative policy paths are repository-relative, independent of the cwd."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def cached_policy(path) -> dict:
    key = str(resolve_policy(path))
    if key not in _POLICIES:
        _POLICIES[key] = load_policy(Path(key))
    return _POLICIES[key]


class CFRAgent:
    """Plays a frozen abstract average strategy. Never learns during evaluation.

    Uses only its own cards, the public board and the public action history of
    the observation. Real raises are translated to ``r``/``a`` by their all-in
    flag; histories outside the abstract tree use a documented fallback.
    """

    def __init__(self, seed: int, policy: dict):
        self.rng = random.Random(seed)
        self.policy = policy
        self.abs = Abstraction(policy["abstraction"]["config"], policy["abstraction"]["preflop_equity"])
        self.stats = {"decisions": 0, "fallback": 0}

    def abstract_view(self, obs):
        hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
        player = 0 if "BTN" in hero["position"] else 1
        street = STREETS.index(obs["street"])
        per_street = [""] * (street + 1)
        raises = pot_raises = 0
        for event in obs["history"]:
            index = STREETS.index(event["street"])
            symbol = {"fold": "f", "check": "c", "call": "c"}.get(event["kind"]) or ("a" if event["all_in"] else "r")
            per_street[index] += symbol
            if index == street and symbol in "ra":
                raises += 1
                pot_raises += symbol == "r"
        bucket = self.abs.bucket(hero["cards"], obs["board"], self.rng)
        return player, street, bucket, tuple(per_street), raises, pot_raises

    def map_action(self, abstract, obs):
        actions = obs["legal_actions"]
        by_kind = {a["kind"]: a for a in actions}
        raises = [a for a in actions if a["kind"] == "raise"]
        if abstract == "f":
            return (by_kind.get("fold") or by_kind.get("check") or by_kind["call"])["id"]
        if abstract == "a":
            shove = [a for a in raises if a["all_in"]]
            return (shove[0] if shove else by_kind.get("call") or by_kind["check"])["id"]
        if abstract == "r":
            normal = [a for a in raises if not a["all_in"]] or raises
            if normal:
                hero = next(s for s in obs["seats"] if s["id"] == obs["actor"])
                call = by_kind.get("call", {}).get("pay", 0)
                target = hero["bet"] + call + obs["pot"] + call
                return min(normal, key=lambda a: (abs(a["to"] - target), a["to"]))["id"]
        return (by_kind.get("check") or by_kind["call"])["id"]

    def fallback(self, bucket, obs):
        actions = {a["kind"]: a for a in obs["legal_actions"]}
        if "check" in actions:
            return actions["check"]["id"]
        strong = bucket >= self.abs.config["postflop_buckets"] * 5 // 8
        if "call" in actions and (strong or "fold" not in actions):
            return actions["call"]["id"]
        return actions["fold"]["id"]

    async def choose_action(self, observation: dict) -> str:
        player, street, bucket, history, raises, pot_raises = self.abstract_view(observation)
        key = infoset_key(player, street, bucket, history)
        self.stats["decisions"] += 1
        probabilities = self.policy["strategy"].get(key)
        if probabilities is None:
            self.stats["fallback"] += 1
            return self.fallback(bucket, observation)
        abstract = self.rng.choices(self.policy["actions"][key], probabilities)[0]
        return self.map_action(abstract, observation)
