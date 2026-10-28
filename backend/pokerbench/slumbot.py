"""Slumbot benchmark client: protocol, PokerKit replay and accounting audit.

What the client relies on (sources and their limits in MISSION_7A.md; nothing
here is an official specification):
- ``POST {base}/new_hand`` with an optional ``token``, ``POST {base}/act`` with
  ``token`` and ``incr``; both return ``token``, ``client_pos``, ``hole_cards``,
  ``board``, ``action`` and, once the hand is over, ``winnings`` (and usually
  ``bot_hole_cards``);
- heads-up no-limit, blinds 50/100, 20,000 chips each, reset every hand, no rake;
- ``client_pos`` 0: we are the big blind; 1: we are the small blind (button);
- ``action`` is the whole hand so far: ``k`` check, ``c`` call, ``f`` fold,
  ``bN`` bet or raise to a total of N on the current street, ``/`` street end.

Every response is replayed from scratch into a PokerKit hand (manual mode, the
opponent's cards unknown): an action PokerKit refuses aborts the hand, so
PokerKit stays the judge of legality. The agent only ever sees that hand's
filtered observation. Once a hand is over it is replayed again with full
information (the bot's revealed cards) and the reported winnings are checked
against PokerKit's own settlement.

Live play needs an explicit ``Authorization``; nothing in this module contacts
slumbot.com by default, and ``OfflineSlumbot`` lets the whole loop run locally.
"""
import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets
import time

from .agents import play_action
from .benchmark import derive_seed, update_public_stats
from .engine import Hand

SB, BB, STACK = 50, 100, 20000
HERO, BOT = "hero", "slumbot"
BASE_URL = "https://slumbot.com/slumbot/api"
BOARD_SEGMENTS = ((0, 3), (3, 4), (4, 5))
_TOKEN = re.compile(r"k|c|f|/|b\d+")


class SlumbotError(Exception):
    pass


def tokenize(action: str) -> list[str]:
    tokens, at = [], 0
    while at < len(action):
        match = _TOKEN.match(action, at)
        if not match:
            raise SlumbotError(f"Unknown action character at {at}: {action!r}")
        tokens.append(match.group())
        at = match.end()
    return tokens


def new_hand(client_pos: int, hole_cards: list[str]) -> Hand:
    if client_pos not in (0, 1):
        raise SlumbotError("client_pos must be 0 or 1")
    # Seat 0 is ours; the button (small blind) is seat 0 when client_pos is 1.
    return Hand([{"id": HERO, "stack": STACK}, {"id": BOT, "stack": STACK}], 0 if client_pos == 1 else 1,
                (SB, BB, 0), 0, manual=True, hero=HERO, hole_cards=list(hole_cards), chip_unit=SB)


def _deal_next(hand: Hand, board: list[str], dealt: int) -> int:
    for start, end in BOARD_SEGMENTS:
        if start == dealt:
            if len(board) < end:
                raise SlumbotError("Street ended before its board cards arrived")
            hand.add_board(board[start:end])
            return end
    raise SlumbotError("More streets than a hold'em board allows")


def _stuck(hand: Hand) -> bool:
    """An all-in showdown the manual hand cannot run out: the bot's cards are unknown."""
    return hand.state.board_dealing_count is None and not hand.state.can_burn_card()


def replay(response: dict, partial: bool = False) -> Hand:
    """Rebuild the hand from a cumulative response; PokerKit checks every step.

    ``partial`` stops at a showdown the manual hand cannot settle (unknown bot cards).
    """
    hand = new_hand(response["client_pos"], response["hole_cards"])
    board, dealt = list(response.get("board") or []), 0
    try:
        for token in tokenize(response.get("action", "")):
            if token == "/":
                if hand.actor is None and hand.state.status and not (partial and _stuck(hand)):
                    dealt = _deal_next(hand, board, dealt)
                continue
            if hand.actor is None:
                if not hand.state.status:
                    raise SlumbotError("Action after the end of the hand")
                dealt = _deal_next(hand, board, dealt)
            ids = {"k": "check", "c": "call", "f": "fold"}
            hand.apply(ids.get(token) or f"raise_to_{token[1:]}")
        # All-in runouts may arrive as board cards without separators.
        while dealt < len(board) and hand.actor is None and hand.state.status and not _stuck(hand):
            dealt = _deal_next(hand, board, dealt)
    except ValueError as exc:
        raise SlumbotError(f"PokerKit rejected the action string {response.get('action')!r}: {exc}") from None
    if partial:
        return hand
    if dealt != len(board):
        raise SlumbotError("Board cards do not match the action string")
    return hand


def encode(action_id: str) -> str:
    """Our legal action id as a Slumbot increment."""
    if action_id in ("fold", "check", "call"):
        return {"fold": "f", "check": "k", "call": "c"}[action_id]
    if action_id.startswith("raise_to_") and action_id[9:].isdigit():
        return f"b{action_id[9:]}"
    raise SlumbotError(f"Cannot encode {action_id!r}")


_POSITIONS: dict = {}


def deal_positions(client_pos: int) -> dict:
    """Deck indices PokerKit deals to our cards, the bot's cards and the board (burns included)."""
    if client_pos not in _POSITIONS:
        from pokerkit import Deck
        deck = [repr(c) for c in Deck.STANDARD]
        hand = Hand([{"id": HERO, "stack": STACK}, {"id": BOT, "stack": STACK}], 0 if client_pos == 1 else 1,
                    (SB, BB, 0), 0, deck=deck, chip_unit=SB)
        while hand.state.status:
            hand.apply("call" if any(a.id == "call" for a in hand.legal()) else "check")
        _POSITIONS[client_pos] = {"hero": [deck.index(c) for c in hand.original_holes[HERO]],
                                  "bot": [deck.index(c) for c in hand.original_holes[BOT]],
                                  "board": [deck.index(c) for c in hand.snapshot()["board"]]}
    return _POSITIONS[client_pos]


def settled_hand(response: dict) -> Hand | None:
    """Full-information replay of a finished hand; PokerKit settles it.

    The bot's cards are the revealed ones, or any unused cards when the hand
    ended by a fold (they cannot matter then). None when a showdown happened
    but the bot's cards were not revealed.
    """
    from pokerkit import Deck
    hole, board = list(response["hole_cards"]), list(response.get("board") or [])
    bot = list(response.get("bot_hole_cards") or [])
    unused = [repr(c) for c in Deck.STANDARD if repr(c) not in hole + board + bot]
    bot = bot or unused[:2]
    unused = [c for c in unused if c not in bot]
    positions = deal_positions(response["client_pos"])
    deck = [None] * 52
    for key, cards in (("hero", hole), ("bot", bot), ("board", board)):
        for index, card in zip(positions[key], cards):
            deck[index] = card
    rest = iter(unused)
    deck = [card or next(rest) for card in deck]
    hand = Hand([{"id": HERO, "stack": STACK}, {"id": BOT, "stack": STACK}], 0 if response["client_pos"] == 1 else 1,
                (SB, BB, 0), 0, deck=deck, chip_unit=SB)
    try:
        for token in tokenize(response.get("action", "")):
            if token == "/":
                continue
            if not hand.state.status:
                raise SlumbotError("Action after the end of the hand")
            action = {"k": "check", "c": "call", "f": "fold"}.get(token) or f"raise_to_{token[1:]}"
            if action in {a.id for a in hand.legal()}:
                hand.apply(action)
            else:
                # Off-grid sizes: the manual path lets PokerKit judge any raise target.
                hand.manual = True
                try:
                    hand.apply(action)
                finally:
                    hand.manual = False
                hand.advance()
    except ValueError as exc:
        raise SlumbotError(f"PokerKit rejected the action string {response.get('action')!r}: {exc}") from None
    if hand.state.status and hand.actor == BOT:
        # Winnings can arrive one response ahead of the bot's fold.
        hand.apply("fold")
        hand.implied_fold = True
    if hand.state.status:
        raise SlumbotError("Hand reported over but PokerKit expects more actions")
    shown = hand.snapshot()["board"]
    if not response.get("bot_hole_cards") and not hand.folded:
        return None
    if shown[:len(board)] != board or len(board) > len(shown) or (not hand.folded and shown != board):
        raise SlumbotError("Board does not match the replay")
    return hand


@dataclass(frozen=True)
class Authorization:
    """Written permission for live play: who granted it and what it covers."""
    reference: str
    max_hands: int
    min_interval: float = 0.5

    def __post_init__(self):
        if len(self.reference.strip()) < 8:
            raise ValueError("Live play needs a reference to a written authorization")
        if not 1 <= self.max_hands <= 100000 or self.min_interval < 0.5:
            raise ValueError("Authorization limits out of range")


class HttpTransport:
    """The only class that reaches slumbot.com; one request at a time, paced."""

    def __init__(self, authorization: Authorization, base_url: str = BASE_URL, retries: int = 4):
        if not isinstance(authorization, Authorization):
            raise ValueError("HttpTransport requires an Authorization")
        self.authorization, self.base_url, self.retries = authorization, base_url.rstrip("/"), retries
        self.last = 0.0
        self.requests = 0

    async def post(self, route: str, body: dict) -> dict:
        import httpx
        for attempt in range(self.retries + 1):
            wait = self.authorization.min_interval - (time.monotonic() - self.last)
            if wait > 0:
                await asyncio.sleep(wait)
            self.last = time.monotonic()
            self.requests += 1
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(f"{self.base_url}/{route}", json=body)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and "error_msg" not in data:
                        return data
                    raise SlumbotError(f"Slumbot error: {data.get('error_msg') if isinstance(data, dict) else data!r}")
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    raise SlumbotError(f"HTTP {response.status_code}")
            except httpx.HTTPError:
                pass
            if attempt < self.retries:
                await asyncio.sleep(min(300, 2 ** (attempt + 1)))
        raise SlumbotError("Slumbot unavailable after retries")


class OfflineSlumbot:
    """Local stand-in speaking the same protocol, for dry runs and tests.

    The bot is any local agent; the deal is a seeded full-information PokerKit
    hand, so the reported winnings come from PokerKit's own settlement.
    ``separators`` controls whether an all-in runout is written with ``/``.
    """

    def __init__(self, bot_factory, seed: int = 0, separators: bool = True):
        self.bot_factory, self.seed, self.separators = bot_factory, seed, separators
        self.token, self.hands, self.hand = None, 0, None

    async def post(self, route: str, body: dict) -> dict:
        if route == "new_hand":
            if body.get("token") not in (None, self.token):
                raise SlumbotError("Unknown token")
            self.token = self.token or secrets.token_hex(8)
            index = self.hands
            self.hands += 1
            # Slumbot alternates positions; seat 0 here is the client.
            self.client_pos = 1 - index % 2
            self.hand = Hand([{"id": HERO, "stack": STACK}, {"id": BOT, "stack": STACK}],
                             0 if self.client_pos == 1 else 1, (SB, BB, 0),
                             derive_seed(self.seed, "slumbot-deck", index), index + 1, chip_unit=SB)
            self.bot = self.bot_factory(derive_seed(self.seed, "slumbot-bot", index))
        elif route == "act":
            if body.get("token") != self.token or self.hand is None or self.hand.actor != HERO:
                raise SlumbotError("Not the client's turn")
            incr = body.get("incr", "")
            action = {"k": "check", "c": "call", "f": "fold"}.get(incr) or (
                f"raise_to_{incr[1:]}" if re.fullmatch(r"b\d+", incr) else None)
            if action is None:
                raise SlumbotError("Bad incr")
            self.hand.apply(action)
        else:
            raise SlumbotError("Unknown route")
        while self.hand.state.status and self.hand.actor == BOT:
            await play_action(self.hand, self.bot)
        return self.response()

    def response(self) -> dict:
        hand = self.hand
        snap = hand.snapshot(reveal=True)
        parts, street = [], "preflop"
        for event in hand.actions:
            if event["street"] != street:
                parts.append("/")
                street = event["street"]
            parts.append(encode(event["id"]))
        board = snap["board"]
        if self.separators and not hand.state.status:
            # Streets dealt after the last action (all-in runout).
            last = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]
            parts += ["/" for _, end in BOARD_SEGMENTS if last < end <= len(board)]
        data = {"token": self.token, "client_pos": self.client_pos, "hole_cards": hand.original_holes[HERO],
                "board": board, "action": "".join(parts)}
        if not hand.state.status:
            seats = {s["id"]: s for s in snap["seats"]}
            data["winnings"] = seats[HERO]["payoff"]
            if not hand.folded:
                data["bot_hole_cards"] = hand.original_holes[BOT]
        return data


class SlumbotSession:
    """Plays hands through a transport with one agent, keeping public statistics."""

    def __init__(self, transport, agent_factory, seed: int = 0, max_failures: int = 3):
        self.transport, self.agent_factory, self.seed = transport, agent_factory, seed
        self.max_failures = max_failures
        self.token, self.stats, self.records = None, {}, []

    async def _request(self, route: str, body: dict) -> dict:
        response = await self.transport.post(route, body)
        if not isinstance(response, dict):
            raise SlumbotError("Response is not a JSON object")
        self.token = response.get("token") or self.token
        return response

    async def play_hand(self) -> dict:
        index = len(self.records)
        agent = self.agent_factory(derive_seed(self.seed, "slumbot-agent", index))
        response = await self._request("new_hand", {"token": self.token} if self.token else {})
        decisions = 0
        while response.get("winnings") is None:
            hand = replay(response)
            if hand.actor != HERO:
                raise SlumbotError("No result and not our turn")
            choice = await agent.choose_action(hand.observation(self.stats))
            if choice not in {a.id for a in hand.legal()}:
                raise SlumbotError("Agent returned an illegal action")
            decisions += 1
            response = await self._request("act", {"token": self.token, "incr": encode(choice)})
        final = settled_hand(response)
        expected = None if final is None else next(s["payoff"] for s in final.snapshot()["seats"] if s["id"] == HERO)
        implied_fold = getattr(final, "implied_fold", False)
        winnings = response["winnings"]
        # Public counters only: every action of the hand is public once it is over.
        update_public_stats(self.stats, final or replay(response, partial=True))
        record = {"hand": index + 1, "client_pos": response["client_pos"], "action": response["action"],
                  "board": response.get("board") or [], "winnings": winnings, "expected": expected,
                  "consistent": None if expected is None else expected == winnings,
                  "implied_fold": implied_fold, "decisions": decisions}
        self.records.append(record)
        return record

    async def run(self, hands: int) -> dict:
        failures = errors = 0
        while len(self.records) < hands:
            try:
                await self.play_hand()
                failures = 0
            except SlumbotError:
                failures += 1
                errors += 1
                # A failed hand restarts the session: the token may hold a half-played hand.
                self.token = None
                if failures >= self.max_failures:
                    break
        return summary(self.records, errors)


def summary(records: list[dict], errors: int = 0) -> dict:
    """Raw-chip result; Slumbot deals cannot be replayed, so there is no paired design."""
    import math
    import statistics
    values = [r["winnings"] / BB for r in records]
    n = len(values)
    mean = statistics.mean(values) * 100 if n else None
    half = 1.959963984540054 * statistics.stdev(values) / math.sqrt(n) * 100 if n > 1 else None
    checked = [r for r in records if r["consistent"] is not None]
    return {"hands": n, "errors": errors, "bb_per_100": mean,
            "ci95_bb_per_100": None if half is None else [mean - half, mean + half],
            "by_position": {pos: sum(r["winnings"] for r in records if r["client_pos"] == cp) / BB
                            for pos, cp in (("SB", 1), ("BB", 0))},
            "accounting_checked": len(checked),
            "accounting_mismatches": sum(not r["consistent"] for r in checked),
            "decisions": sum(r["decisions"] for r in records)}


def local_agent(name: str):
    """Agent factory by name: a local CFR entry or a benchmark profile."""
    from .benchmark import make_agent
    from .local_agents import ADAPTIVE, LOCAL_POLICIES
    if name in LOCAL_POLICIES:
        return lambda seed: make_agent("cfr", seed, 64, cfr_policy=LOCAL_POLICIES[name][1],
                                       cfr_adaptive=name in ADAPTIVE)
    return lambda seed: make_agent(name, seed, 64)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", default="cfr-v2-adapt")
    p.add_argument("--hands", type=int, default=100)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", metavar="BOT", help="local stand-in opponent, e.g. tag")
    mode.add_argument("--live-authorization", metavar="REFERENCE",
                      help="reference of the written permission for live play on slumbot.com")
    a = p.parse_args()
    if a.offline:
        transport = OfflineSlumbot(local_agent(a.offline), a.seed)
    else:
        transport = HttpTransport(Authorization(a.live_authorization, a.hands))
    session = SlumbotSession(transport, local_agent(a.agent), a.seed)
    result = asyncio.run(session.run(a.hands))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"summary": result, "agent": a.agent, "mode": "offline" if a.offline else "live",
                                    "opponent": a.offline or "slumbot.com", "hands": session.records}, indent=1))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
