"""Private bot-versus-bot exhibitions a signed-in user can watch hand by hand.

Hands use the benchmark format (heads-up, 200 BB reset each hand, alternating
button) and the same bridge: each agent receives only its own filtered
observation and PokerKit validates every action. The spectator, who is not a
player, sees both hands. Sessions live in memory only and never enter the
benchmark results or the public match list.
"""
import asyncio
import secrets
import time

from .agents import play_action
from .benchmark import BB, derive_seed, make_agent, update_public_stats
from .engine import Hand
from .local_agents import ADAPTIVE, LOCAL_POLICIES

AGENTS = {**{key: name for key, (name, _, _) in LOCAL_POLICIES.items()},
          "tag": "TightAggressive", "hyper": "HyperAggressive", "station": "CallingStation",
          "equity": "EquityHeuristic", "heuristic": "Heuristic", "random": "Random"}
MAX_SESSIONS_PER_USER, MAX_HANDS = 5, 2000


def agent(name: str, seed: int):
    if name in LOCAL_POLICIES:
        return make_agent("cfr", seed, 64, cfr_policy=LOCAL_POLICIES[name][1], cfr_adaptive=name in ADAPTIVE)
    return make_agent(name, seed, 64)


class Spectator:
    def __init__(self):
        self.sessions: dict[str, dict] = {}

    def create(self, owner: str, a: str, b: str) -> dict:
        if a not in AGENTS or b not in AGENTS:
            raise ValueError("请选择列表中的智能体")
        mine = sorted((s for s in self.sessions.values() if s["owner"] == owner), key=lambda s: s["created"])
        for old in mine[:max(0, len(mine) - MAX_SESSIONS_PER_USER + 1)]:
            self.sessions.pop(old["id"], None)
        session = {"id": secrets.token_urlsafe(12), "owner": owner, "created": time.time(),
                   "agents": {"a": a, "b": b}, "deck_seed": secrets.randbelow(2**62),
                   "policy_seed": secrets.randbelow(2**62), "hands": [], "lock": asyncio.Lock(), "public": {},
                   "stats": {seat: {"hands": 0, "net_chips": 0, "won": 0} for seat in "ab"}}
        self.sessions[session["id"]] = session
        return self.public(session)

    def get(self, owner: str, session_id: str) -> dict:
        session = self.sessions.get(session_id)
        if session is None or session["owner"] != owner:
            raise KeyError(session_id)
        return session

    async def hand(self, owner: str, session_id: str, number: int) -> dict:
        """Hand ``number`` (1-based); plays the next one when asked for it."""
        session = self.get(owner, session_id)
        async with session["lock"]:
            return await self._hand(session, number)

    async def _hand(self, session: dict, number: int) -> dict:
        played = len(session["hands"])
        if number < 1 or number > played + 1 or number > MAX_HANDS:
            raise ValueError("只能观看已发的手牌或下一手")
        if number == played + 1:
            index = played
            seats = {seat: agent(name, derive_seed(session["policy_seed"], f"policy:{seat}", index))
                     for seat, name in session["agents"].items()}
            hand = Hand([{"id": "a", "stack": 200 * BB}, {"id": "b", "stack": 200 * BB}], index % 2, (BB // 2, BB, 0),
                        derive_seed(session["deck_seed"], "deck", index), number, chip_unit=50)
            # Agents see the same public counters a room exposes (VPIP, PFR, 3-bet).
            while hand.state.status:
                await play_action(hand, seats[hand.actor], session["public"])
            update_public_stats(session["public"], hand)
            payoffs = {s["id"]: s["payoff"] for s in hand.snapshot()["seats"]}
            for seat, payoff in payoffs.items():
                row = session["stats"][seat]
                row["hands"] += 1
                row["net_chips"] += payoff
                row["won"] += payoff > 0
            session["hands"].append({"number": number, "events": hand.record()["events"], "payoffs": payoffs})
        return {"hand": session["hands"][number - 1], "session": self.public(session)}

    def public(self, session: dict) -> dict:
        stats = {seat: {**row, "bb_per_100": row["net_chips"] / BB / row["hands"] * 100 if row["hands"] else None}
                 for seat, row in session["stats"].items()}
        names = {seat: AGENTS[name] for seat, name in session["agents"].items()}
        if names["a"] == names["b"]:
            names = {seat: f"{name} ({seat.upper()})" for seat, name in names.items()}
        return {"id": session["id"], "agents": session["agents"], "names": names,
                "hands_played": len(session["hands"]), "max_hands": MAX_HANDS, "stats": stats}
