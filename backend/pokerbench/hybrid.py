"""Hybrid agent: a frozen CFR policy that consults an advisor (Jev) by a fixed rule.

The rule decides, from CFR's own distribution only, whether the advisor is
consulted, then how the two distributions are combined. Rules are pure and
parameterized up front, so each one is a preregistered arm of a paired
benchmark (MISSION_7A.md): the consultation rate, hence the API cost, can be
measured on CFR alone before any paid call.

- ``cfr``: never consults (the baseline, CFR V2 adaptive);
- ``advisor``: always follows the advisor;
- ``gate``: consults when CFR left its abstract tree (fallback) or its top
  action has probability below ``threshold``, then follows the advisor;
- ``mix``: always consults and plays ``(1 - weight) * CFR + weight * advisor``.

The advisor sees the same request a room would send it. An advisor failure
falls back to CFR's distribution and is counted, never hidden.
"""
from dataclasses import dataclass
import random

from .compare import cfr_distribution, request_for


@dataclass(frozen=True)
class Rule:
    name: str
    threshold: float = 0.0
    weight: float = 0.0

    def __post_init__(self):
        if self.name not in ("cfr", "advisor", "gate", "mix"):
            raise ValueError("Unknown rule")
        if not (0 <= self.threshold <= 1 and 0 <= self.weight <= 1):
            raise ValueError("Rule parameters must be in [0, 1]")

    def consult(self, cfr: dict, meta: dict) -> bool:
        if self.name == "cfr":
            return False
        if self.name == "gate":
            return meta["source"] == "fallback" or max(cfr.values()) < self.threshold
        return True

    def combine(self, cfr: dict, advisor: dict) -> dict:
        if self.name == "mix":
            keys = set(cfr) | set(advisor)
            return {k: (1 - self.weight) * cfr.get(k, 0.0) + self.weight * advisor.get(k, 0.0) for k in keys}
        return dict(advisor)


def normalized(probabilities: dict, legal: list[str]) -> dict:
    p = {k: max(0.0, float(probabilities.get(k, 0.0))) for k in legal}
    total = sum(p.values())
    if total <= 0:
        raise ValueError("No probability on a legal action")
    return {k: v / total for k, v in p.items()}


class HybridAgent:
    def __init__(self, cfr, advisor, rule: Rule, seed: int, adaptive: bool = True):
        self.cfr, self.advisor, self.rule, self.adaptive = cfr, advisor, rule, adaptive
        self.rng = random.Random(seed)
        self.stats = {"decisions": 0, "consulted": 0, "advisor_errors": 0, "fallback": 0, "cost_cny": 0.0}

    async def distribution(self, observation: dict) -> tuple[dict, dict]:
        legal = [a["id"] for a in observation["legal_actions"]]
        cfr, meta = cfr_distribution(self.cfr, observation, self.adaptive)
        cfr = normalized(cfr, legal)
        self.stats["decisions"] += 1
        self.stats["fallback"] += meta["source"] == "fallback"
        info = {"cfr": cfr, "consulted": False, "advisor": None}
        if not self.rule.consult(cfr, meta):
            return cfr, info
        self.stats["consulted"] += 1
        info["consulted"] = True
        try:
            answer = await self.advisor(request_for(observation))
            self.stats["cost_cny"] += answer.get("cost_cny_estimate") or 0.0
            advice = normalized(answer["answers"]["action"]["probabilities"], legal)
        except Exception:  # an advisor failure must never block the hand
            self.stats["advisor_errors"] += 1
            return cfr, info
        info["advisor"] = advice
        return normalized(self.rule.combine(cfr, advice), legal), info

    async def choose_action(self, observation: dict) -> str:
        final, _ = await self.distribution(observation)
        actions = sorted(final)
        return self.rng.choices(actions, [final[a] for a in actions])[0]


def consult_rate(requests, rule: Rule, policy: str = "cfr-v2-adapt") -> dict:
    """How often a rule would consult the advisor, from CFR alone (no call)."""
    from .benchmark import derive_seed
    from .compare import request_hash
    from .holdem_abstraction import cached_policy
    from .holdem_v2 import agent_for
    from .local_agents import ADAPTIVE, LOCAL_POLICIES
    table = cached_policy(LOCAL_POLICIES[policy][1])
    consulted, by_street = 0, {}
    for request in requests:
        obs = request["state"]
        agent = agent_for(derive_seed(0, "compare:" + request_hash(request), 0), table)
        cfr, meta = cfr_distribution(agent, obs, policy in ADAPTIVE)
        hit = rule.consult(cfr, meta)
        consulted += hit
        row = by_street.setdefault(obs["street"], [0, 0])
        row[0] += hit
        row[1] += 1
    n = len(requests)
    return {"rule": vars(rule), "decisions": n, "consult_rate": consulted / n if n else None,
            "by_street": {s: c / t for s, (c, t) in by_street.items()}}
