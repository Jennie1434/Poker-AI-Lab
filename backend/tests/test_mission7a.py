import asyncio
import json
import random

import pytest

from pokerbench import compare as cmp
from pokerbench import slumbot as sb
from pokerbench.costs import halfwidth, hands_for_halfwidth, sd_from_interval
from pokerbench.engine import Hand
from pokerbench.holdem_abstraction import cached_policy
from pokerbench.holdem_v2 import agent_for
from pokerbench.hybrid import HybridAgent, Rule, consult_rate
from pokerbench.local_agents import LOCAL_POLICIES
from pokerbench.translation import pseudo_harmonic, translate


@pytest.fixture(scope="module")
def requests():
    return asyncio.run(cmp.collect(4, 11, opponents=("tag", "hyper")))


def run(coro):
    return asyncio.run(coro)


# Slumbot protocol -----------------------------------------------------------

def test_tokenize_accepts_the_grammar_and_rejects_anything_else():
    assert sb.tokenize("b200c/kk/kb400") == ["b200", "c", "/", "k", "k", "/", "k", "b400"]
    assert sb.tokenize("") == []
    for bad in ("x", "b", "b20a", "r300"):
        with pytest.raises(sb.SlumbotError):
            sb.tokenize(bad)


def test_replay_follows_slumbot_actions_with_pokerkit_as_judge():
    # We are the big blind: Slumbot (button) raised to 300, we called, flop dealt, checks.
    hand = sb.replay({"client_pos": 0, "hole_cards": ["Ah", "Kd"], "board": ["2c", "7d", "9h"],
                      "action": "b300c/k"})
    assert hand.street == "flop" and hand.actor == sb.BOT
    assert hand.committed == {sb.HERO: 300, sb.BOT: 300}
    obs = hand.observation()
    assert [s["cards"] for s in obs["seats"] if s["id"] != obs["actor"]] == [["??", "??"]]
    # Off-grid sizes are accepted when PokerKit allows them...
    assert sb.replay({"client_pos": 1, "hole_cards": ["Ah", "Kd"], "board": [], "action": "b237"}).committed[sb.HERO] == 237
    # ...illegal ones are not: a raise below the minimum, a check facing a bet, missing board cards.
    for action, board in (("b150", []), ("b300k", []), ("b300c/k", [])):
        with pytest.raises(sb.SlumbotError):
            sb.replay({"client_pos": 1, "hole_cards": ["Ah", "Kd"], "board": board, "action": action})


def test_encode_maps_every_legal_action():
    hand = sb.new_hand(1, ["Ah", "Kd"])
    assert {a.id: sb.encode(a.id) for a in hand.legal()}["raise_to_300"] == "b300"
    assert [sb.encode(x) for x in ("fold", "check", "call")] == ["f", "k", "c"]
    with pytest.raises(sb.SlumbotError):
        sb.encode("raise_to_x")


def test_settlement_comes_from_pokerkit_and_catches_the_implied_fold():
    shove = {"client_pos": 1, "hole_cards": ["As", "Ad"], "bot_hole_cards": ["Kc", "Kd"],
             "board": ["2c", "7d", "9h", "3s", "4h"], "action": "b20000c///", "winnings": 20000}
    hand = sb.settled_hand(shove)
    assert not hand.state.status and hand.snapshot()["board"] == shove["board"]
    assert {s["id"]: s["payoff"] for s in hand.snapshot()["seats"]}[sb.HERO] == 20000
    # Slumbot folded but the answer only carries the winnings.
    hand = sb.settled_hand({"client_pos": 1, "hole_cards": ["As", "Ad"], "board": [], "action": "b300",
                            "winnings": 100})
    assert hand.implied_fold and {s["id"]: s["payoff"] for s in hand.snapshot()["seats"]}[sb.HERO] == 100
    # A showdown without the bot's cards cannot be verified.
    assert sb.settled_hand({**shove, "bot_hole_cards": None}) is None
    with pytest.raises(sb.SlumbotError):
        sb.settled_hand({**shove, "board": ["2c", "7d", "9h", "3s", "5h"], "action": "b20000c"[:-1]})


@pytest.mark.parametrize("bot,separators", [("hyper", True), ("hyper", False), ("tag", True), ("station", True)])
def test_offline_session_plays_and_balances_every_hand(bot, separators):
    seen = []

    def factory(seed):
        agent = sb.local_agent("cfr-v2-adapt")(seed)

        class Spy:
            async def choose_action(self, observation):
                seen.append(observation)
                return await agent.choose_action(observation)
        return Spy()

    session = sb.SlumbotSession(sb.OfflineSlumbot(sb.local_agent(bot), 3, separators), factory, 3)
    result = run(session.run(60))
    assert result["hands"] == 60 and result["errors"] == 0
    assert result["accounting_checked"] == 60 and result["accounting_mismatches"] == 0
    assert {r["client_pos"] for r in session.records} == {0, 1}
    for obs in seen:
        assert all(s["cards"] == s["public_cards"] for s in obs["seats"] if s["id"] != obs["actor"])
    assert session.stats and all(row["hands"] == 60 for row in session.stats.values())


def test_live_play_needs_a_written_authorization():
    with pytest.raises(ValueError):
        sb.HttpTransport(None)
    with pytest.raises(ValueError):
        sb.Authorization("", 100)
    with pytest.raises(ValueError):
        sb.Authorization("email from the operator, 2026-10-01", 100, min_interval=0.1)
    transport = sb.HttpTransport(sb.Authorization("email from the operator, 2026-10-01", 100))
    assert transport.requests == 0 and transport.base_url.startswith("https://slumbot.com")


def test_session_stops_after_repeated_failures():
    class Broken:
        async def post(self, route, body):
            raise sb.SlumbotError("down")
    result = run(sb.SlumbotSession(Broken(), sb.local_agent("cfr-v2"), max_failures=3).run(10))
    assert result["hands"] == 0 and result["errors"] == 3


# Jev / CFR comparison ---------------------------------------------------------

def test_requests_match_what_a_room_sends(requests):
    hand = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}], 0, (50, 100, 0), 5, chip_unit=50)
    expected = hand.request("")
    assert cmp.request_for(hand.observation()) == expected
    assert cmp.INSTRUCTIONS == expected["questions"]["action"]["instructions"]
    for r in requests:
        assert all(s["cards"] == s["public_cards"] for s in r["state"]["seats"] if s["id"] != r["state"]["actor"])


@pytest.mark.parametrize("name", ["cfr-v2", "cfr-v2-adapt", "cfr-v1", "cfr-v3"])
def test_cfr_distribution_is_what_the_agent_samples_from(requests, name):
    from pokerbench.local_agents import ADAPTIVE
    from pokerbench.slumbot import local_agent
    policy = cached_policy(LOCAL_POLICIES[name][1])
    for i, r in enumerate(requests):
        dist, meta = cmp.cfr_distribution(agent_for(i, policy), r["state"], name in ADAPTIVE)
        assert abs(sum(dist.values()) - 1) < 1e-9
        assert set(dist) <= {a["id"] for a in r["state"]["legal_actions"]}
        choice = run(local_agent(name)(i).choose_action(r["state"]))
        assert dist.get(choice, 0) > 0, (name, meta)


def test_compare_reports_agreement(requests):
    same = run(cmp.compare(requests, cmp.CFRAdvisor("cfr-v2"), cmp.CFRAdvisor("cfr-v2")))
    assert same["overall"]["same_action"] == 1 and same["overall"]["mean_tv"] == 0
    other = run(cmp.compare(requests, cmp.CFRAdvisor("cfr-v2-adapt"), cmp.CFRAdvisor("cfr-v3")))
    assert other["overall"]["decisions"] == len(requests) and other["overall"]["mean_tv"] > 0
    assert set(other["by_opponent"]) == {"tag", "hyper"}


def test_paid_advisor_is_explicit_and_bounded(requests):
    class FakeProvider:
        calls = 0

        async def call(self, entry, request, **kw):
            FakeProvider.calls += 1
            legal = list(request["questions"]["action"]["criteria"])
            return {"answers": {"action": {"probabilities": {k: 1 / len(legal) for k in legal},
                                           "choice": legal[0]}}, "cost_cny_estimate": 0.4}

    class Entry:
        id = "jev"

    with pytest.raises(PermissionError):
        cmp.ProviderAdvisor(FakeProvider(), Entry(), 1.0)
    advisor = cmp.ProviderAdvisor(FakeProvider(), Entry(), 1.0, allow_paid=True)
    body = {k: v for k, v in requests[0].items() if k != "meta"}
    for _ in range(3):
        run(advisor(body))
    with pytest.raises(RuntimeError):
        run(advisor(body))
    assert FakeProvider.calls == 3 and advisor.spent == pytest.approx(1.2)


def test_recorded_answers_replay_without_calls(requests, tmp_path):
    body = {k: v for k, v in requests[0].items() if k != "meta"}
    answer = run(cmp.CFRAdvisor("cfr-v2")(body))
    path = tmp_path / "answers.jsonl"
    path.write_text(json.dumps({"request_hash": cmp.request_hash(body), "response": answer}) + "\n")
    assert run(cmp.RecordedAdvisor(path)(body)) == answer
    with pytest.raises(KeyError):
        run(cmp.RecordedAdvisor(path)({k: v for k, v in requests[1].items() if k != "meta"}))


def test_cost_estimate_matches_the_provider_reserve(requests):
    body = {k: v for k, v in requests[0].items() if k != "meta"}
    size = len(json.dumps(body).encode())
    result = cmp.estimate([requests[0]], 2.0, 8.0, 300, max_tokens=1000)
    assert result["reserve_cny"] == pytest.approx((size + 512) * 2.0 / 1e6 + 1000 * 8.0 / 1e6)
    assert result["expected_cny"] == pytest.approx(size / 4 * 2.0 / 1e6 + 300 * 8.0 / 1e6)


# Hybrid agent -------------------------------------------------------------------

class OneHot:
    """Advisor that always prefers the most passive legal action."""
    def __init__(self):
        self.calls = 0

    async def __call__(self, request):
        self.calls += 1
        legal = request["questions"]["action"]["criteria"]
        pick = next(k for k in ("check", "call", "fold") if k in legal)
        return {"answers": {"action": {"probabilities": {k: float(k == pick) for k in legal}, "choice": pick}},
                "cost_cny_estimate": 0.01}


class Failing:
    async def __call__(self, request):
        raise RuntimeError("timeout")


def test_rules_are_validated():
    for bad in (dict(name="vote"), dict(name="gate", threshold=1.5), dict(name="mix", weight=-0.1)):
        with pytest.raises(ValueError):
            Rule(**bad)


def test_hybrid_rules_on_identical_observations(requests):
    policy = cached_policy(LOCAL_POLICIES["cfr-v2-adapt"][1])
    for i, r in enumerate(requests):
        obs = r["state"]
        base = cmp.cfr_distribution(agent_for(i, policy), obs, True)[0]
        advisor = OneHot()
        cfr_only, info = run(HybridAgent(agent_for(i, policy), advisor, Rule("cfr"), 0).distribution(obs))
        assert advisor.calls == 0 and not info["consulted"]
        assert cfr_only == pytest.approx({k: base.get(k, 0.0) for k in cfr_only})
        follow, _ = run(HybridAgent(agent_for(i, policy), advisor, Rule("advisor"), 0).distribution(obs))
        assert max(follow, key=follow.get) in ("check", "call", "fold") and max(follow.values()) == 1
        mixed, _ = run(HybridAgent(agent_for(i, policy), advisor, Rule("mix", weight=0.25), 0).distribution(obs))
        assert sum(mixed.values()) == pytest.approx(1)
        for k in mixed:
            assert mixed[k] == pytest.approx(0.75 * base.get(k, 0) + 0.25 * follow.get(k, 0))


def test_advisor_failure_falls_back_to_cfr_and_is_counted(requests):
    policy = cached_policy(LOCAL_POLICIES["cfr-v2-adapt"][1])
    agent = HybridAgent(agent_for(1, policy), Failing(), Rule("advisor"), 0)
    for r in requests[:5]:
        assert run(agent.choose_action(r["state"])) in {a["id"] for a in r["state"]["legal_actions"]}
    assert agent.stats["advisor_errors"] == 5 and agent.stats["consulted"] == 5


def test_hybrid_plays_complete_hands_through_the_bridge():
    from pokerbench.agents import play_action
    from pokerbench.benchmark import make_agent
    policy = cached_policy(LOCAL_POLICIES["cfr-v2-adapt"][1])

    async def play():
        advisor = OneHot()
        hero = HybridAgent(agent_for(0, policy), advisor, Rule("gate", threshold=0.6), 0)
        for index in range(20):
            hand = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}], index % 2, (50, 100, 0),
                        index, chip_unit=50)
            other = make_agent("hyper", index, 32)
            while hand.state.status:
                await play_action(hand, hero if hand.actor == "a" else other)
            assert sum(s["payoff"] for s in hand.snapshot()["seats"]) == 0
        return hero, advisor
    hero, advisor = run(play())
    assert hero.stats["consulted"] == advisor.calls > 0
    assert hero.stats["cost_cny"] == pytest.approx(0.01 * advisor.calls)


def test_consult_rate_grows_with_the_gate_threshold(requests):
    rates = [consult_rate(requests, Rule("gate", threshold=t))["consult_rate"] for t in (0.0, 0.5, 0.8, 1.0)]
    assert rates == sorted(rates) and rates[-1] <= 1
    assert consult_rate(requests, Rule("cfr"))["consult_rate"] == 0
    assert consult_rate(requests, Rule("advisor"))["consult_rate"] == 1


# Translation and costs --------------------------------------------------------

def test_pseudo_harmonic_translation():
    assert pseudo_harmonic(0.5, 1.0, 0.75) == pytest.approx((0.25 * 1.5) / (0.5 * 1.75))
    assert pseudo_harmonic(0.5, 1.0, 0.5) == 1 and pseudo_harmonic(0.5, 1.0, 1.0) == 0
    assert translate(0.1, [0.5, 1.0]) == 0.5 and translate(5, [0.5, 1.0]) == 1.0
    assert translate(0.7, [0.5, 1.0]) == 0.5 and translate(0.9, [0.5, 1.0]) == 1.0
    rng = random.Random(1)
    share = sum(translate(0.75, [0.5, 1.0], rng) == 0.5 for _ in range(20000)) / 20000
    assert share == pytest.approx(pseudo_harmonic(0.5, 1.0, 0.75), abs=0.02)
    with pytest.raises(ValueError):
        pseudo_harmonic(1.0, 0.5, 0.7)


def test_sample_size_arithmetic():
    assert sd_from_interval(14.0, 86000) == pytest.approx(20.94, abs=0.01)
    n = hands_for_halfwidth(15.9, 20)
    assert halfwidth(15.9, n) <= 20 < halfwidth(15.9, n - 1)
