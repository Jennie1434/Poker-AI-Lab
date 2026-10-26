"""In-process CFR opponents for private human rooms; no network, keys or cost.

Each registry entry names a frozen policy file. The decision is computed from
the room's filtered observation only (the same one sent to remote models), and
PokerKit validates the returned action like any other model's answer.
"""
import asyncio
import hashlib
import time

from .config import Entry
from .holdem_abstraction import cached_policy, resolve_policy
from .holdem_v2 import agent_for

# id -> (display name, repository-relative policy file, description)
LOCAL_POLICIES = {
    "cfr-v1": ("CFR V1 · 200k", "artifacts/mission4/policy-71001-200000.json.gz",
               "MCCFR self-play, 200,000 iterations, abstraction v1"),
    "cfr-v1-20k": ("CFR V1 · 20k", "artifacts/mission4/policy-71001-20000.json.gz",
                   "Early snapshot of the same training, 20,000 iterations"),
    "cfr-v2": ("CFR V2 · 300k", "artifacts/mission5/policy-v2-72001-300000.json.gz",
               "MCCFR self-play, 300,000 iterations, abstraction v2 (three raise sizes, draw-aware)"),
}
# Entries played through the public-statistics overlay (adaptive.py).
ADAPTIVE: set[str] = set()
COLOR = "#2f7d6d"


def policy_path(entry: Entry):
    return resolve_policy(LOCAL_POLICIES[entry.model][1])


def local_entries() -> list[Entry]:
    entries = []
    for key, (name, path, _) in LOCAL_POLICIES.items():
        file = resolve_policy(path)
        revision = hashlib.sha256(file.read_bytes()).hexdigest()[:16] if file.exists() else "missing"
        entries.append(Entry(id=key, name=name, color=COLOR, provider="local_cfr", model=key, base_url="",
                             key_env="", proxy=False, revision=revision,
                             input_cny_per_million=0, output_cny_per_million=0))
    return entries


def available(entry: Entry) -> bool:
    return entry.model in LOCAL_POLICIES and policy_path(entry).exists()


async def decide(entry: Entry, request: dict, decision_id: str, request_hash: str) -> dict:
    """Seeded by the decision id: replays and restarts reproduce the same action."""
    started = time.monotonic()
    policy = cached_policy(LOCAL_POLICIES[entry.model][1])
    seed = int.from_bytes(hashlib.sha256(f"local-cfr:{decision_id}".encode()).digest()[:8], "big")
    agent = agent_for(seed, policy)
    if entry.model in ADAPTIVE:
        from .adaptive import AdaptiveCFRAgent
        agent = AdaptiveCFRAgent(agent)
    choice = await agent.choose_action(request["state"])
    if choice not in request["questions"]["action"]["criteria"]:
        raise ValueError("CFR policy returned an action that is not offered")
    await asyncio.sleep(0)
    return {"model": entry.model, "model_revision": entry.revision,
            "answers": {"action": {"choice": choice, "probabilities": {choice: 1.0}}},
            "usage": {"input_tokens": 0, "output_tokens": 0}, "latency": time.monotonic() - started,
            "cost_cny_estimate": 0.0, "request_hash": request_hash, "decision_id": decision_id,
            "provider": "local_cfr", "proxy": False, "probability_source": "sampled_cfr_policy",
            "thinking": "provider_default", "entry_id": entry.id, "attempts": [], "retry_count": 0,
            "fallback": bool(agent.stats["fallback"]), "abstention_policy": entry.abstention_policy}
