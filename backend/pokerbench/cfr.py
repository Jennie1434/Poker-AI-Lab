"""Counterfactual regret minimization for two-player zero-sum extensive games.

Games expose histories, chance, actions and the acting player's information set
key. Utilities are always for player 0; player 1 receives the negation.

Three trainers share one regret/strategy table:
- ``vanilla``: CFR with full tree traversal and simultaneous updates;
- ``plus``: CFR+ (alternating updates, regrets floored at zero, linear averaging);
- ``external``: external-sampling Monte Carlo CFR, for games too large to traverse.

Exploitability is exact (full best response), so it is only available for games
whose tree can be enumerated (Kuhn, Leduc). A sampled trainer that converges on
those games is not thereby proven to converge on an abstracted Hold'em game.
"""
import hashlib
import json
from pathlib import Path
import random
from typing import Protocol

FORMAT = "pokerbench-cfr-v1"
VARIANTS = ("vanilla", "plus", "external")


class Game(Protocol):
    name: str

    def root(self): ...
    def is_terminal(self, h) -> bool: ...
    def utility(self, h) -> float: ...
    def is_chance(self, h) -> bool: ...
    def chance_outcomes(self, h) -> list: ...
    def player(self, h) -> int: ...
    def actions(self, h) -> tuple: ...
    def child(self, h, action): ...
    def infoset(self, h) -> str: ...


def regret_matching(regrets: list[float]) -> list[float]:
    positive = [r if r > 0 else 0.0 for r in regrets]
    total = sum(positive)
    if total <= 0:
        return [1.0 / len(regrets)] * len(regrets)
    return [r / total for r in positive]


def normalize(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        return [1.0 / len(values)] * len(values)
    return [v / total for v in values]


class CFRTrainer:
    """Regret tables keyed by information set; deterministic given its seed."""

    def __init__(self, game: Game, variant: str = "vanilla", seed: int = 0):
        if variant not in VARIANTS:
            raise ValueError("Unknown CFR variant")
        self.game, self.variant, self.seed = game, variant, seed
        self.regrets: dict[str, list[float]] = {}
        self.strategy_sum: dict[str, list[float]] = {}
        self.actions: dict[str, tuple] = {}
        self.iterations = 0
        self.rng = random.Random(seed)

    def _tables(self, key, actions):
        known = self.actions.get(key)
        if known is None:
            self.actions[key] = tuple(actions)
            self.regrets[key] = [0.0] * len(actions)
            self.strategy_sum[key] = [0.0] * len(actions)
        elif known != tuple(actions):
            raise ValueError(f"Information set {key!r} has inconsistent actions")
        return self.regrets[key], self.strategy_sum[key]

    def current_strategy(self, key, actions):
        return regret_matching(self._tables(key, actions)[0])

    def average_strategy(self) -> dict[str, dict[str, float]]:
        return {key: dict(zip(self.actions[key], normalize(self.strategy_sum[key])))
                for key in sorted(self.actions)}

    def train(self, iterations: int, callback=None, every: int = 0):
        for _ in range(iterations):
            t = self.iterations + 1
            if self.variant == "vanilla":
                self._pass(None, t)
            elif self.variant == "plus":
                for player in (0, 1):
                    self._pass(player, t)
            else:
                for player in (0, 1):
                    self._external(self.game.root(), player)
            self.iterations = t
            if callback and every and t % every == 0:
                callback(self)
        return self

    def _pass(self, update, t):
        # The current strategy must stay fixed for the whole traversal: an
        # information set spans several histories, so regrets are buffered.
        self._pending = {}
        self._cfr(self.game.root(), 1.0, 1.0, 1.0, update, t)
        for key, delta in self._pending.items():
            regrets = self.regrets[key]
            for i, d in enumerate(delta):
                regrets[i] += d
                if self.variant == "plus" and regrets[i] < 0:
                    regrets[i] = 0.0

    def _cfr(self, h, reach0, reach1, chance, update, t):
        g = self.game
        if g.is_terminal(h):
            return g.utility(h)
        if g.is_chance(h):
            return sum(p * self._cfr(g.child(h, a), reach0, reach1, chance * p, update, t)
                       for a, p in g.chance_outcomes(h))
        player, actions, key = g.player(h), g.actions(h), g.infoset(h)
        regrets, sums = self._tables(key, actions)
        sigma = regret_matching(regrets)
        values = []
        for a, p in zip(actions, sigma):
            if player == 0:
                values.append(self._cfr(g.child(h, a), reach0 * p, reach1, chance, update, t))
            else:
                values.append(self._cfr(g.child(h, a), reach0, reach1 * p, chance, update, t))
        value = sum(p * v for p, v in zip(sigma, values))
        if update is None or update == player:
            sign = 1 if player == 0 else -1
            own, other = (reach0, reach1) if player == 0 else (reach1, reach0)
            weight = t if self.variant == "plus" else 1
            delta = self._pending.setdefault(key, [0.0] * len(actions))
            for i, v in enumerate(values):
                delta[i] += sign * chance * other * (v - value)
                sums[i] += weight * own * sigma[i]
        return value

    def _external(self, h, traverser):
        """Value for the traverser; samples chance and the opponent's actions."""
        g = self.game
        if g.is_terminal(h):
            return g.utility(h) if traverser == 0 else -g.utility(h)
        if g.is_chance(h):
            if hasattr(g, "sample_chance"):
                a = g.sample_chance(h, self.rng)
            else:
                outcomes = g.chance_outcomes(h)
                a = self.rng.choices([o for o, _ in outcomes], [p for _, p in outcomes])[0]
            return self._external(g.child(h, a), traverser)
        player, actions, key = g.player(h), g.actions(h), g.infoset(h)
        regrets, sums = self._tables(key, actions)
        sigma = regret_matching(regrets)
        if player != traverser:
            for i, p in enumerate(sigma):
                sums[i] += p
            a = self.rng.choices(actions, sigma)[0]
            return self._external(g.child(h, a), traverser)
        values = [self._external(g.child(h, a), traverser) for a in actions]
        value = sum(p * v for p, v in zip(sigma, values))
        for i, v in enumerate(values):
            regrets[i] += v - value
        return value

    # Checkpoints -------------------------------------------------------
    def state(self, metadata: dict | None = None) -> dict:
        payload = {"format": FORMAT, "game": self.game.name, "variant": self.variant,
                   "seed": self.seed, "iterations": self.iterations,
                   "actions": {k: list(v) for k, v in sorted(self.actions.items())},
                   "regrets": {k: self.regrets[k] for k in sorted(self.regrets)},
                   "strategy_sum": {k: self.strategy_sum[k] for k in sorted(self.strategy_sum)},
                   "rng_state": _rng_to_json(self.rng.getstate()),
                   "metadata": metadata or {}}
        payload["sha256"] = digest(payload)
        return payload

    def save(self, path: Path, metadata: dict | None = None, overwrite: bool = False):
        save_checkpoint(self.state(metadata), Path(path), overwrite)

    @classmethod
    def load(cls, game: Game, path: Path):
        data = load_checkpoint(Path(path), game.name)
        trainer = cls(game, data["variant"], data["seed"])
        trainer.iterations = data["iterations"]
        trainer.actions = {k: tuple(v) for k, v in data["actions"].items()}
        trainer.regrets = {k: list(v) for k, v in data["regrets"].items()}
        trainer.strategy_sum = {k: list(v) for k, v in data["strategy_sum"].items()}
        trainer.rng.setstate(_rng_from_json(data["rng_state"]))
        return trainer


def _rng_to_json(state):
    version, internal, gauss = state
    return [version, list(internal), gauss]


def _rng_from_json(state):
    version, internal, gauss = state
    return (version, tuple(internal), gauss)


def digest(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save_checkpoint(payload: dict, path: Path, overwrite: bool = False):
    if path.exists() and not overwrite:
        raise FileExistsError(f"Checkpoint {path} exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(path)


def load_checkpoint(path: Path, game_name: str | None = None) -> dict:
    data = json.loads(path.read_text())
    if data.get("format") != FORMAT:
        raise ValueError("Unknown checkpoint format")
    if data.get("sha256") != digest(data):
        raise ValueError("Checkpoint checksum mismatch")
    if game_name is not None and data["game"] != game_name:
        raise ValueError(f"Checkpoint is for {data['game']}, not {game_name}")
    return data


# Exact evaluation -----------------------------------------------------
def _probabilities(strategy, key, actions):
    table = strategy.get(key)
    if table is None:
        return [1.0 / len(actions)] * len(actions)
    return [table[a] for a in actions]


def expected_value(game: Game, strategy: dict) -> float:
    """Player-0 value when both players follow ``strategy``."""
    def walk(h):
        if game.is_terminal(h):
            return game.utility(h)
        if game.is_chance(h):
            return sum(p * walk(game.child(h, a)) for a, p in game.chance_outcomes(h))
        actions = game.actions(h)
        probs = _probabilities(strategy, game.infoset(h), actions)
        return sum(p * walk(game.child(h, a)) for a, p in zip(actions, probs) if p)
    return walk(game.root())


def best_response_value(game: Game, strategy: dict, responder: int) -> float:
    """Value for ``responder`` playing a best response to the fixed opponent strategy.

    Each responder information set chooses the action maximizing the sum over
    its histories of (chance x opponent reach) x value. Perfect recall makes
    that choice depend only on deeper information sets.
    """
    sign = 1 if responder == 0 else -1
    histories: dict[str, list] = {}

    def collect(h, weight):
        if game.is_terminal(h):
            return
        if game.is_chance(h):
            for a, p in game.chance_outcomes(h):
                collect(game.child(h, a), weight * p)
            return
        actions = game.actions(h)
        if game.player(h) == responder:
            histories.setdefault(game.infoset(h), []).append((h, weight))
            for a in actions:
                collect(game.child(h, a), weight)
        else:
            for a, p in zip(actions, _probabilities(strategy, game.infoset(h), actions)):
                if p:
                    collect(game.child(h, a), weight * p)

    collect(game.root(), 1.0)
    choice: dict[str, object] = {}

    def best(key):
        if key not in choice:
            members = histories[key]
            actions = game.actions(members[0][0])
            totals = [sum(w * value(game.child(h, a)) for h, w in members) for a in actions]
            choice[key] = actions[max(range(len(actions)), key=lambda i: (totals[i], -i))]
        return choice[key]

    def value(h):
        if game.is_terminal(h):
            return sign * game.utility(h)
        if game.is_chance(h):
            return sum(p * value(game.child(h, a)) for a, p in game.chance_outcomes(h))
        if game.player(h) == responder:
            return value(game.child(h, best(game.infoset(h))))
        actions = game.actions(h)
        return sum(p * value(game.child(h, a))
                   for a, p in zip(actions, _probabilities(strategy, game.infoset(h), actions)) if p)

    return value(game.root())


def exploitability(game: Game, strategy: dict) -> dict:
    """NashConv / 2: zero exactly at a Nash equilibrium, in game utility units."""
    br0 = best_response_value(game, strategy, 0)
    br1 = best_response_value(game, strategy, 1)
    return {"best_response_p0": br0, "best_response_p1": br1,
            "nash_conv": br0 + br1, "exploitability": (br0 + br1) / 2,
            "value_p0": expected_value(game, strategy)}
