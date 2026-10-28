"""Compare two deciders (CFR, Jev, any model) on identical observations.

Each sample is one request exactly as a room sends it to a model
(``Hand.request``): the acting player's filtered observation and the legal
actions as criteria. Every advisor answers with probabilities over those
action ids, so CFR and Jev are compared on the same object, not on outcomes.

Advisors:
- ``CFRAdvisor``: a local frozen policy (optionally with the adaptive overlay);
  its abstract distribution is mapped onto the concrete legal actions. Free.
- ``RecordedAdvisor``: answers saved from an earlier run, matched by request
  hash. Free; lets a paid run be analysed again without new calls.
- ``ProviderAdvisor``: the application's ``Provider`` (Jev, DeepSeek, ...).
  Paid: refused unless ``allow_paid`` is set, and bounded by a budget.

``estimate`` prices a request set before any paid call.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from .adaptive import HIGH, LOW, adjust, equity_estimate, opponent_pfr
from .agents import play_action
from .benchmark import BB, derive_seed, update_public_stats
from .engine import Hand

KINDS = {"fold": "fold", "check": "passive", "call": "passive", "raise": "aggressive"}


def request_hash(request: dict) -> str:
    body = {k: v for k, v in request.items() if k != "model"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def request_for(observation: dict) -> dict:
    """The model request for an observation (same criteria as ``Hand.request``)."""
    criteria = {a["id"]: {"action": a["kind"], "pay_now": a["pay"], "total_street_contribution": a["to"],
                          "all_in": a["all_in"]} for a in observation["legal_actions"]}
    return {"model": "", "state": observation, "questions": {"action": {
        "type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria}}}


# Same wording as ``Hand.request`` (a test keeps them identical).
INSTRUCTIONS = ("Choose the legal poker action with the best expected strategic outcome under the stated rules "
                "and objective. Return preference probabilities over ALL offered actions. Use only information "
                "available to the acting player. Opponents' unknown hole cards are not known. These probabilities "
                "are action preferences, not hand winning probabilities.")


def cfr_abstract(agent, observation: dict, adaptive: bool = False):
    """(abstract actions, probabilities, bucket, overlay weight), exactly as the agent plays them."""
    actions, probabilities, bucket = agent.distribution(observation)
    weight = 0.0
    if adaptive and actions is not None:
        pfr, _ = opponent_pfr(observation)
        weight = min(1.0, max(0.0, (pfr - LOW) / (HIGH - LOW)))
        if weight > 0:
            call = observation["to_call"]
            price = call / (observation["pot"] + call) if call else 0.0
            probabilities = adjust(actions, probabilities, weight, equity_estimate(agent, observation, bucket), price)
    return actions, probabilities, bucket, weight


def concrete(agent, observation: dict, actions, probabilities, bucket) -> tuple[dict, dict]:
    """Abstract distribution mapped onto the concrete legal action ids."""
    if actions is None:
        return {agent.fallback(bucket, observation): 1.0}, {"source": "fallback", "bucket": bucket}
    result = defaultdict(float)
    for abstract, p in zip(actions, probabilities):
        if p > 0:
            result[agent.map_action(abstract, observation)] += p
    # Stored strategies are rounded to four decimals; sampling uses them as weights.
    total = sum(result.values())
    return {k: v / total for k, v in result.items()}, {"source": "policy", "bucket": bucket}


def cfr_distribution(agent, observation: dict, adaptive: bool = False) -> tuple[dict, dict]:
    """CFR's probabilities over the concrete legal action ids, and how they were obtained.

    Same steps as ``CFRAgent.choose_action`` (and the adaptive overlay), but
    the abstract distribution is mapped onto action ids instead of sampled.
    """
    actions, probabilities, bucket, weight = cfr_abstract(agent, observation, adaptive)
    dist, meta = concrete(agent, observation, actions, probabilities, bucket)
    return dist, {**meta, "overlay_weight": weight}


class CFRAdvisor:
    paid = False

    def __init__(self, name: str = "cfr-v2-adapt", seed: int = 0):
        from .holdem_abstraction import cached_policy
        from .local_agents import ADAPTIVE, LOCAL_POLICIES
        if name not in LOCAL_POLICIES:
            raise ValueError(f"Unknown local policy {name}")
        self.name, self.seed = name, seed
        self.policy = cached_policy(LOCAL_POLICIES[name][1])
        self.adaptive = name in ADAPTIVE

    async def __call__(self, request: dict) -> dict:
        from .holdem_v2 import agent_for
        # Seeded by the request: the same observation always gets the same answer.
        seed = derive_seed(self.seed, "compare:" + request_hash(request), 0)
        probabilities, meta = cfr_distribution(agent_for(seed, self.policy), request["state"], self.adaptive)
        legal = request["questions"]["action"]["criteria"]
        probabilities = {k: probabilities.get(k, 0.0) for k in legal}
        return {"answers": {"action": {"probabilities": probabilities,
                                       "choice": max(probabilities, key=probabilities.get)}},
                "cost_cny_estimate": 0.0, "meta": meta}


class RecordedAdvisor:
    paid = False

    def __init__(self, path: Path):
        self.answers = {}
        with Path(path).open() as f:
            for line in f:
                row = json.loads(line)
                self.answers[row["request_hash"]] = row["response"]

    @classmethod
    def from_answers(cls, answers: dict) -> "RecordedAdvisor":
        advisor = cls.__new__(cls)
        advisor.answers = dict(answers)
        return advisor

    async def __call__(self, request: dict) -> dict:
        try:
            return self.answers[request_hash(request)]
        except KeyError:
            raise KeyError("No recorded answer for this request") from None


class ProviderAdvisor:
    """A real model through the application's Provider: costs money."""
    paid = True

    def __init__(self, provider, entry, budget_cny: float, allow_paid: bool = False, run_id: str = "compare"):
        if not allow_paid:
            raise PermissionError("ProviderAdvisor makes paid calls; pass allow_paid=True explicitly")
        if not budget_cny > 0:
            raise ValueError("A positive budget is required")
        self.provider, self.entry, self.budget, self.run_id = provider, entry, budget_cny, run_id
        self.spent = 0.0

    async def __call__(self, request: dict) -> dict:
        if self.spent >= self.budget:
            raise RuntimeError("Comparison budget exhausted")
        decision_id = f"compare-{self.entry.id}-{request_hash(request)[:24]}"
        result = await self.provider.call(self.entry, request, decision_id=decision_id, run_id=self.run_id,
                                          run_budget=self.budget - self.spent)
        self.spent += result.get("cost_cny_estimate") or 0.0
        return result


async def collect(hands: int, seed: int, hero: str = "cfr-v2-adapt", opponents=("tag", "hyper", "station", "equity")):
    """Synthetic decision points: the hero seat's requests over seeded local hands.

    The hands are dealt here (no personal history is involved); only the
    hero's own observations are kept, so no hidden card is recorded.
    """
    from .slumbot import local_agent
    requests = []
    for opponent in opponents:
        stats = {}
        for index in range(hands):
            seats = {"a": local_agent(hero)(derive_seed(seed, f"{opponent}:policy:a", index)),
                     "b": local_agent(opponent)(derive_seed(seed, f"{opponent}:policy:b", index))}
            hand = Hand([{"id": "a", "stack": 200 * BB}, {"id": "b", "stack": 200 * BB}], index % 2,
                        (BB // 2, BB, 0), derive_seed(seed, f"{opponent}:deck", index), index + 1, chip_unit=50)
            while hand.state.status:
                if hand.actor == "a":
                    requests.append({**hand.request("", stats), "meta": {"opponent": opponent, "hand": index + 1}})
                await play_action(hand, seats[hand.actor], stats)
            update_public_stats(stats, hand)
    return requests


def total_variation(p: dict, q: dict) -> float:
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def kind_mass(probabilities: dict, criteria: dict) -> dict:
    mass = Counter()
    for action, p in probabilities.items():
        mass[KINDS[criteria[action]["action"]]] += p
    return dict(mass)


async def compare(requests, advisor_a, advisor_b, examples: int = 10) -> dict:
    rows = []
    for request in requests:
        body = {k: v for k, v in request.items() if k != "meta"}
        criteria = body["questions"]["action"]["criteria"]
        a = (await advisor_a(body))["answers"]["action"]["probabilities"]
        b = (await advisor_b(body))["answers"]["action"]["probabilities"]
        top_a, top_b = max(a, key=a.get), max(b, key=b.get)
        ka, kb = kind_mass(a, criteria), kind_mass(b, criteria)
        rows.append({"street": body["state"]["street"], "opponent": request.get("meta", {}).get("opponent"),
                     "facing_bet": bool(body["state"]["to_call"]), "same_action": top_a == top_b,
                     "same_kind": KINDS[criteria[top_a]["action"]] == KINDS[criteria[top_b]["action"]],
                     "tv": total_variation(a, b), "kind_tv": total_variation(ka, kb),
                     "top_a": top_a, "top_b": top_b, "hash": request_hash(body)})

    def block(selected):
        n = len(selected)
        return {"decisions": n,
                "same_action": sum(r["same_action"] for r in selected) / n if n else None,
                "same_kind": sum(r["same_kind"] for r in selected) / n if n else None,
                "mean_tv": sum(r["tv"] for r in selected) / n if n else None,
                "mean_kind_tv": sum(r["kind_tv"] for r in selected) / n if n else None}

    by = lambda key: {str(v): block([r for r in rows if r[key] == v]) for v in sorted({r[key] for r in rows}, key=str)}
    disagreements = sorted(rows, key=lambda r: -r["tv"])[:examples]
    return {"overall": block(rows), "by_street": by("street"), "by_opponent": by("opponent"),
            "by_facing_bet": by("facing_bet"),
            "largest_disagreements": [{k: r[k] for k in ("hash", "street", "top_a", "top_b", "tv")}
                                      for r in disagreements]}


def estimate(requests, input_cny_per_million: float, output_cny_per_million: float,
             output_tokens: int, max_tokens: int = 8192, bytes_per_token: float = 4.0) -> dict:
    """Price a request set before calling a paid model.

    ``reserve`` reproduces the Provider's conservative budget hold (one token
    per input byte, ``max_tokens`` of output); ``expected`` uses ~4 bytes per
    token and the given output length. Prices are inputs: the repository holds
    no verified price for Jev.
    """
    sizes = [len(json.dumps({k: v for k, v in r.items() if k != "meta"}).encode()) for r in requests]
    n = len(sizes)
    reserve = sum((s + 512) * input_cny_per_million / 1e6 + max_tokens * output_cny_per_million / 1e6 for s in sizes)
    expected = sum(s / bytes_per_token * input_cny_per_million / 1e6 + output_tokens * output_cny_per_million / 1e6
                   for s in sizes)
    return {"requests": n, "mean_request_bytes": sum(sizes) / n if n else 0, "max_request_bytes": max(sizes, default=0),
            "reserve_cny": reserve, "expected_cny": expected,
            "expected_cny_per_decision": expected / n if n else 0,
            "assumptions": {"input_cny_per_million": input_cny_per_million,
                            "output_cny_per_million": output_cny_per_million, "output_tokens": output_tokens,
                            "bytes_per_token": bytes_per_token, "max_tokens": max_tokens}}


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path):
    with Path(path).open() as f:
        return [json.loads(line) for line in f]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("collect", help="synthetic decision points from seeded local hands")
    s.add_argument("--hands", type=int, default=50); s.add_argument("--seed", type=int, default=0)
    s.add_argument("--output", type=Path, required=True)
    s = sub.add_parser("estimate", help="price a request set for a paid model (no call)")
    s.add_argument("requests", type=Path)
    s.add_argument("--input-cny-per-million", type=float, required=True)
    s.add_argument("--output-cny-per-million", type=float, required=True)
    s.add_argument("--output-tokens", type=int, default=300)
    s = sub.add_parser("local", help="compare two local CFR policies (free)")
    s.add_argument("requests", type=Path); s.add_argument("--a", default="cfr-v2-adapt"); s.add_argument("--b", default="cfr-v2")
    s.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.command == "collect":
        write_jsonl(a.output, asyncio.run(collect(a.hands, a.seed)))
    elif a.command == "estimate":
        print(json.dumps(estimate(read_jsonl(a.requests), a.input_cny_per_million, a.output_cny_per_million,
                                  a.output_tokens), indent=1))
    else:
        result = asyncio.run(compare(read_jsonl(a.requests), CFRAdvisor(a.a), CFRAdvisor(a.b)))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=1))
        print(json.dumps(result["overall"]))


if __name__ == "__main__":
    main()
