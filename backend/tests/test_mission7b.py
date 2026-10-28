import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from pokerbench import jev_pilot, mission7
from pokerbench.config import ROOT, Entry, Settings
from pokerbench.provider import Provider, ProviderError
from pokerbench.store import Store

KEY = "jev-secret-key-123456"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def jev_provider(tmp_path, monkeypatch):
    from pokerbench import provider as module
    slept = []

    async def no_sleep(seconds):
        slept.append(seconds)
    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setenv("JEV_API_KEY", KEY)
    provider = Provider(Settings(_env_file=None, pokerbench_usd_cny_rate=7.0), Store(str(tmp_path / "calls.db")))
    provider.slept = slept
    return provider


def fake_jev(monkeypatch, responses, sent):
    """Patch the HTTP layer: each call pops the next (status, body, headers)."""
    async def post(client, url, **kw):
        sent.append({"url": url, "json": kw["json"], "headers": kw["headers"]})
        status, body, headers = responses.pop(0) if len(responses) > 1 else responses[0]
        return httpx.Response(status, json=body, headers=headers)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)


def answer(request, model="jev-1.14.0", tokens=1000):
    legal = list(request["questions"]["action"]["criteria"])
    probs = {k: 1 / len(legal) for k in legal}
    return {"model": model, "answers": {"action": {"type": "choice", "choice": legal[0], "confidence": 0.5,
                                                   "probabilities": probs}},
            "usage": {"input_tokens": tokens, "output_tokens": 40}}


def request():
    from pokerbench.engine import Hand
    hand = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}], 0, (50, 100, 0), 3, chip_unit=50)
    return hand.request("")


def leaked(tmp_path) -> bool:
    for path in Path(tmp_path).rglob("*"):
        if path.is_file() and KEY.encode() in path.read_bytes():
            return True
    return False


# Configuration ------------------------------------------------------------------

def test_jev_entries_get_official_defaults_and_usd_prices():
    e = Entry(id="jev", name="Jev", provider="jev")
    assert (e.base_url, e.key_env, e.model) == ("https://api.typesafe.ai", "JEV_API_KEY", "jev-1.14.0")
    assert (e.input_usd_per_million, e.output_usd_per_million) == (0.042, 0.0)
    assert e.prices_cny(7.0) == pytest.approx((0.294, 0.0))
    with pytest.raises(ValueError):
        e.prices_cny(0)
    # Explicit choices are kept, including a CNY price chosen by an operator.
    custom = Entry(id="j", name="J", provider="jev", model="jev-latest", input_cny_per_million=1, output_cny_per_million=0)
    assert custom.model == "jev-latest" and custom.input_usd_per_million is None and custom.prices_cny(0) == (1, 0)


def test_other_providers_keep_their_own_prices():
    deepseek = Entry(id="d", name="D")
    assert (deepseek.input_cny_per_million, deepseek.output_cny_per_million) == (2.16, 8.64)
    assert deepseek.input_usd_per_million is None and deepseek.prices_cny(0) == (2.16, 8.64)
    assert deepseek.key_env == "DEEPSEEK_API_KEY" and deepseek.base_url == "https://api.deepseek.com"
    usd = Entry(id="o", name="O", provider="openai_compatible", input_usd_per_million=1, output_usd_per_million=2)
    assert usd.prices_cny(7.0) == (7.0, 14.0)
    with pytest.raises(ValueError):
        Entry(id="o", name="O", provider="openai_compatible", input_usd_per_million=1)


def test_example_registry_pins_jev_1_14_0():
    entries = [Entry.model_validate(e) for e in json.loads((ROOT / "examples" / "entries.example.json").read_text())]
    jev = next(e for e in entries if e.provider == "jev")
    assert jev.model == jev.expected_model == "jev-1.14.0"
    assert (jev.input_usd_per_million, jev.output_usd_per_million) == (0.042, 0.0)
    assert Settings(_env_file=None).pokerbench_usd_cny_rate > 0


# Provider: authentication, tokens, budget, errors ---------------------------------

def test_jev_call_authenticates_counts_tokens_and_never_stores_the_key(jev_provider, monkeypatch, tmp_path):
    sent, req = [], request()
    fake_jev(monkeypatch, [(200, answer(req, tokens=1000), {"x-typesafe-request-id": "req-1"})], sent)
    out = run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d1", run_id="r"))
    assert sent[0]["url"] == "https://api.typesafe.ai/v1/systemone"
    assert sent[0]["headers"] == {"Authorization": f"Bearer {KEY}"} and sent[0]["json"]["model"] == "jev-1.14.0"
    assert out["usage"] == {"input_tokens": 1000, "output_tokens": 40}
    # Output is free: only input tokens are billed, at 0.042 USD/M converted at 7 CNY/USD.
    assert out["cost_cny_estimate"] == pytest.approx(1000 * 0.042 / 1e6 * 7.0)
    call = json.loads(jev_provider.store.calls()[0]["body"])
    assert call["charge_usd"] == pytest.approx(1000 * 0.042 / 1e6) and call["request_id"] == "req-1"
    assert not leaked(tmp_path)


def test_wrong_model_is_rejected_before_any_action(jev_provider, monkeypatch):
    sent, req = [], request()
    fake_jev(monkeypatch, [(200, answer(req, model="jev-1.13.0"), {})], sent)
    with pytest.raises(ProviderError, match="模型身份不符"):
        run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d2", run_id="r"))
    assert len(sent) == 1 and jev_provider.store.decision("d2") is None


def test_auth_failure_is_not_retried_and_does_not_echo_the_key(jev_provider, monkeypatch, tmp_path):
    sent, req = [], request()
    fake_jev(monkeypatch, [(401, {"error": f"invalid key {KEY}"}, {})], sent)
    with pytest.raises(ProviderError) as error:
        run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d3", run_id="r"))
    assert len(sent) == 1 and KEY not in str(error.value) and not leaked(tmp_path)


def test_rate_limit_waits_as_asked_then_succeeds(jev_provider, monkeypatch):
    sent, req = [], request()
    fake_jev(monkeypatch, [(429, {"error": "slow down"}, {"retry-after": "4"}),
                           (503, {}, {"retry-after-ms": "120000"}), (200, answer(req), {})], sent)
    out = run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d4", run_id="r"))
    assert len(sent) == 3 and out["retry_count"] == 2
    assert jev_provider.slept == [4.0, 30.0]


def test_budget_and_missing_rate_stop_before_the_network(jev_provider, monkeypatch):
    sent, req = [], request()
    fake_jev(monkeypatch, [(200, answer(req), {})], sent)
    with pytest.raises(ValueError, match="预算不足"):
        run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d5", run_id="r", run_budget=1e-9))
    jev_provider.settings.pokerbench_usd_cny_rate = 0
    with pytest.raises(ProviderError, match="USD_CNY_RATE"):
        run(jev_provider.call(jev_pilot.jev_entry(), req, decision_id="d6", run_id="r"))
    assert sent == []


# Pilot ------------------------------------------------------------------------------

def test_committed_pilot_plan_is_the_preregistered_sample():
    plan = jev_pilot.read_plan(jev_pilot.PLAN)
    assert len(plan) == 500
    streets = {s: sum(r["state"]["street"] == s for r in plan) for s in jev_pilot.QUOTAS}
    assert streets == jev_pilot.QUOTAS
    assert {r["meta"]["opponent"] for r in plan} == {"tag", "hyper", "station", "equity"}
    assert len({json.dumps(r, sort_keys=True) for r in plan}) == 500
    for r in plan:
        assert all(s["cards"] == s["public_cards"] for s in r["state"]["seats"] if s["id"] != r["state"]["actor"])


def test_plan_building_is_deterministic(tmp_path):
    small = {"preflop": 3, "flop": 2}
    a, b = (jev_pilot.build_plan(5, 3, small) for _ in range(2))
    assert a == b and len(a) == 5
    assert jev_pilot.write_plan(tmp_path / "a.gz", a) == jev_pilot.write_plan(tmp_path / "b.gz", b)
    assert (tmp_path / "a.gz").read_bytes() == (tmp_path / "b.gz").read_bytes()


def test_pilot_estimate_is_an_upper_bound_in_usd():
    plan = jev_pilot.read_plan(jev_pilot.PLAN)
    e = jev_pilot.estimate(plan, 7.0)
    assert e["requests"] == 500 and e["output_usd_per_million"] == 0
    assert e["expected_usd"] < e["upper_bound_usd"] < 0.15
    assert e["upper_bound_cny"] == pytest.approx(e["upper_bound_usd"] * 7.0)


def test_pilot_refuses_paid_calls_without_explicit_approval(tmp_path, monkeypatch):
    plan = jev_pilot.read_plan(jev_pilot.PLAN)[:3]
    with pytest.raises(PermissionError):
        run(jev_pilot.run(plan, tmp_path / "out", 0.1))
    with pytest.raises(ValueError):
        run(jev_pilot.run(plan, tmp_path / "out", 50, approve_paid_calls=True))
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    with pytest.raises(PermissionError, match="JEV_API_KEY"):
        run(jev_pilot.run(plan, tmp_path / "out", 0.1, approve_paid_calls=True,
                          settings=Settings(_env_file=None, jev_api_key="")))


def test_pilot_end_to_end_with_a_simulated_endpoint(tmp_path, monkeypatch):
    plan = jev_pilot.read_plan(jev_pilot.PLAN)[::50]
    monkeypatch.setenv("JEV_API_KEY", KEY)
    sent = []

    async def post(client, url, **kw):
        sent.append(kw["json"])
        # A stand-in that always prefers the most passive action.
        legal = kw["json"]["questions"]["action"]["criteria"]
        pick = next(k for k in ("check", "call", "fold") if k in legal)
        body = {"model": "jev-1.14.0", "usage": {"input_tokens": 900, "output_tokens": 30},
                "answers": {"action": {"type": "choice", "choice": pick, "confidence": 0.7,
                                       "probabilities": {k: float(k == pick) for k in legal}}}}
        return httpx.Response(200, json=body)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    settings = Settings(_env_file=None, pokerbench_usd_cny_rate=7.0)
    out = tmp_path / "pilot"
    summary = run(jev_pilot.run(plan, out, 0.05, approve_paid_calls=True, settings=settings))
    assert summary["answered"] == len(plan) == len(sent) and summary["errors"] == 0
    assert summary["spent_usd"] == pytest.approx(len(plan) * 900 * 0.042 / 1e6)
    # A rerun reuses the recorded answers: no new call.
    run(jev_pilot.run(plan, out, 0.05, approve_paid_calls=True, settings=settings))
    assert len(sent) == len(plan)
    result = run(jev_pilot.analyze(plan, out / "answers.jsonl"))
    assert result["answered"] == len(plan) and result["models"] == {"jev-1.14.0": len(plan)}
    assert 0 <= result["agreement"]["overall"]["same_action"] <= 1
    assert sum(result["kind_confusion_cfr_to_jev"].values()) == len(plan)
    report = jev_pilot.report_markdown(result, jev_pilot.estimate(plan, 7.0))
    assert "Plus grands désaccords" in report and "jev-1.14.0" in report
    assert not leaked(tmp_path)


def test_pilot_stops_when_the_model_is_not_the_pinned_version(tmp_path, monkeypatch):
    plan = jev_pilot.read_plan(jev_pilot.PLAN)[:12]
    monkeypatch.setenv("JEV_API_KEY", KEY)
    sent = []

    async def post(client, url, **kw):
        sent.append(1)
        return httpx.Response(200, json=answer(kw["json"], model="jev-latest"))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    summary = run(jev_pilot.run(plan, tmp_path / "p", 0.05, approve_paid_calls=True, concurrency=1,
                                settings=Settings(_env_file=None)))
    assert summary["stopped_early"] and summary["answered"] == 0 and len(sent) == 1


# Hybrid benchmark --------------------------------------------------------------------

def test_hybrid_without_consultation_replays_cfr_exactly():
    from pokerbench.agents import play_action
    from pokerbench.benchmark import derive_seed, make_agent
    from pokerbench.engine import Hand
    from pokerbench.holdem_abstraction import cached_policy
    from pokerbench.holdem_v2 import agent_for
    from pokerbench.hybrid import HybridAgent, Rule

    class Failing:
        async def __call__(self, request):
            raise RuntimeError("down")

    policy = cached_policy(mission7.POLICY)

    async def play(kind):
        public, results = {}, []
        for n in range(24):
            seed = derive_seed(9, "policy:a", n)
            if kind == "baseline":
                hero = make_agent("cfr", seed, 64, cfr_policy=mission7.POLICY, cfr_adaptive=True)
            else:
                hero = HybridAgent(agent_for(seed, policy), Failing(), Rule(kind))
            other = make_agent("hyper", derive_seed(9, "policy:b", n), 64)
            hand = Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}], n % 2, (50, 100, 0),
                        derive_seed(8, "deck", n), n + 1, chip_unit=50)
            while hand.state.status:
                await play_action(hand, hero if hand.actor == "a" else other, public)
            results.append([a["id"] for a in hand.actions])
        return results

    baseline = run(play("baseline"))
    # Never consulting, or consulting an advisor that always fails, plays CFR's own draws.
    assert run(play("cfr")) == baseline
    assert run(play("advisor")) == baseline


def test_benchmark_harness_and_cost_plan():
    results = [run(mission7.series("tag", 1, 2, 8, a)) for a in (None, "null")]
    analysis = mission7.analyze(results)
    arm = analysis["arms"]["null"]
    assert arm["valid"] and arm["opponents"]["tag"]["hands"] == 8
    assert 0 <= arm["opponents"]["tag"]["consult_rate"] <= 1
    plan = mission7.jev_cost_plan(analysis, 0.0002)
    row = plan["by_opponent"]["tag"]
    assert plan["total_usd"] == pytest.approx(row["hands_needed"] * row["calls_per_hand"] * 0.0002)


def test_jev_arm_is_never_played_without_approval(tmp_path):
    with pytest.raises(PermissionError):
        mission7.make_advisor("jev", 1)
    with pytest.raises(PermissionError):
        run(mission7.run_jev(10, tmp_path / "x", 1.0))


# Two-stage pilot: ten verification calls before the rest --------------------------------

def _serve(monkeypatch, sent, model="jev-1.14.0", usage=True, status=200):
    async def post(client, url, **kw):
        sent.append(kw["json"])
        if status != 200:
            return httpx.Response(status, json={"error": "denied"})
        body = answer(kw["json"], model=model, tokens=950)
        if not usage:
            body.pop("usage")
        return httpx.Response(200, json=body)
    monkeypatch.setattr(httpx.AsyncClient, "post", post)


def _pilot(tmp_path, plan, max_usd=0.25):
    return run(jev_pilot.pilot(plan, tmp_path / "pilot", max_usd, approve_paid_calls=True,
                               settings=Settings(_env_file=None, pokerbench_usd_cny_rate=7.0)))


def test_pilot_verifies_ten_calls_then_runs_the_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    plan, sent = jev_pilot.read_plan(jev_pilot.PLAN)[:40], []
    _serve(monkeypatch, sent)
    result = _pilot(tmp_path, plan)
    assert result["verification"]["passed"] and result["verification"]["calls"] == 10
    assert not result["stopped"] and result["stage2"]["answered"] == 40 and len(sent) == 40
    assert {r["state"]["street"] for r in jev_pilot.verification_sample(jev_pilot.read_plan(jev_pilot.PLAN))} == \
        set(jev_pilot.QUOTAS)
    assert result["stage2"]["spent_usd"] == pytest.approx(40 * 950 * 0.042 / 1e6)
    assert not leaked(tmp_path)


@pytest.mark.parametrize("fault", ["model", "usage", "auth"])
def test_pilot_stops_when_a_verification_fails(tmp_path, monkeypatch, fault):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    plan, sent = jev_pilot.read_plan(jev_pilot.PLAN)[:40], []
    _serve(monkeypatch, sent, model="jev-latest" if fault == "model" else "jev-1.14.0",
           usage=fault != "usage", status=401 if fault == "auth" else 200)
    result = _pilot(tmp_path, plan)
    assert result["stopped"] and result["stage2"] is None and not result["verification"]["passed"]
    assert len(sent) <= 10
    assert not leaked(tmp_path)


def test_pilot_total_spend_never_exceeds_the_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", KEY)
    plan, sent = jev_pilot.read_plan(jev_pilot.PLAN)[:40], []
    _serve(monkeypatch, sent)
    # A ceiling below the plan's cost: the budget hold stops new calls before it is crossed.
    result = _pilot(tmp_path, plan, max_usd=0.0015)
    spent = result["stage2"]["spent_usd"] if result["stage2"] else result["stage1"]["spent_usd"]
    assert spent <= 0.0015 and len(sent) < 40
