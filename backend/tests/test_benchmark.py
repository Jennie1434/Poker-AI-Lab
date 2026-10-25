import csv
from dataclasses import replace
import json
import math
from pathlib import Path

import pytest

from pokerbench.agents import EquityHeuristicAgent
from pokerbench.benchmark import Config, derive_seed, experiment, performance, settle_rake
from pokerbench.benchmark_dashboard import build
from pokerbench.engine import Hand


def hand(deck=None):
    return Hand([{"id": "a", "stack": 20000}, {"id": "b", "stack": 20000}],
                0, (50, 100, 0), 42, deck=deck, chip_unit=50)


def finish_passive(h):
    while h.state.status:
        h.apply("check" if any(a.id == "check" for a in h.legal()) else "call")
    return h


@pytest.mark.parametrize("cfg", [Config(hands=3), Config(hands=0), Config(rake_percent="-1"),
                                  Config(rake_percent="101"), Config(rake_cap_bb="-1"),
                                  Config(rake_percent="NaN"), Config(rake_cap_bb="Infinity"),
                                  Config(equity_samples=0), Config(agent_a="unknown")])
def test_invalid_configuration(cfg):
    with pytest.raises(ValueError):
        cfg.validate()


def test_rng_domains_and_hand_seeds_are_separate():
    seeds = {derive_seed(1, domain, i) for domain in ("deck", "policy:a", "policy:b") for i in range(20)}
    assert len(seeds) == 60
    assert derive_seed(1, "deck", 4) == derive_seed(1, "deck", 4)


def test_rake_excludes_uncalled_bet_and_no_flop_no_drop():
    h = hand()
    h.apply("raise_to_20000")
    h.apply("fold")
    cfg = Config(rake_percent="5", rake_cap_bb="3", no_flop_no_drop=False)
    result = settle_rake(h, cfg)
    assert result["pot"] == 200  # Not the uncalled 20,000-chip bet.
    assert result["rake"] == 10
    assert result["gross"] == {"a": 100, "b": -100}
    assert result["net"] == {"a": 90, "b": -100}
    assert settle_rake(h, replace(cfg, no_flop_no_drop=True))["rake"] == 0
    assert settle_rake(h, replace(cfg, rake_percent="0"))["net"] == result["gross"]


def test_rake_cap_all_in_and_conservation():
    h = hand()
    h.apply("raise_to_20000")
    h.apply("call")
    result = settle_rake(h, Config())
    assert result["pot"] == 40000
    assert result["saw_flop"]
    assert result["rake"] == 300
    assert sum(result["net"].values()) == -300


def test_tied_board_allocates_rake_exactly_with_integer_remainder():
    prefix = ["2c", "3c", "4d", "5d", "6c", "Th", "Jh", "Qh", "7c", "Kh", "8c", "Ah"]
    deck = prefix + [r+s for r in "23456789TJQKA" for s in "cdhs" if r+s not in prefix]
    h = finish_passive(hand(deck))
    result = settle_rake(h, Config(rake_percent="2.99"))
    assert h.snapshot()["board"] == ["Th", "Jh", "Qh", "Kh", "Ah"]
    assert result["gross"] == {"a": 0, "b": 0}
    assert result["rake"] == 5  # floor(200 * .0299)
    assert result["net"] == {"a": -3, "b": -2}


def test_rake_rejects_live_hand():
    with pytest.raises(ValueError, match="completed"):
        settle_rake(hand(), Config())


def test_known_statistics_and_block_standard_error():
    # Two block means: 1 and 3 BB; mean=2, sample SD=sqrt(2), SE=1.
    result = performance([0, 200, 200, 400])
    assert result["profit_bb"] == 8
    assert result["bb_per_100"] == 200
    assert result["standard_error_bb_per_100"] == pytest.approx(100)
    assert result["ci95_bb_per_100"] == pytest.approx([4.0036015459946, 395.9963984540054])
    assert result["win_rate"] == 0.75
    assert result["break_even_rate"] == 0.25
    assert performance([100] * 4)["ci95_bb_per_100"] == [100, 100]
    with pytest.raises(ValueError):
        performance([100] * 3)


@pytest.mark.asyncio
async def test_reproducible_exports_balanced_positions_and_private_trace(tmp_path):
    cfg = Config(hands=20)
    report = await experiment(cfg, tmp_path / "first")
    repeated = await experiment(cfg, tmp_path / "repeat")
    assert report == repeated
    assert report["status"] == "complete"
    for name in ("experiment.json", "hands.csv", "decisions.jsonl"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "repeat" / name).read_bytes()
    rows = list(csv.DictReader((tmp_path / "first/hands.csv").open()))
    assert len(rows) == 20
    assert [r["button"] for r in rows] == ["a", "b"] * 10
    for r in rows:
        assert int(r["a_gross_chips"]) + int(r["b_gross_chips"]) == 0
        assert int(r["a_net_chips"]) + int(r["b_net_chips"]) == -int(r["rake_chips"])
    for seat in ("a", "b"):
        stats = report["summary"]["agents"][seat]
        assert stats["button_hands"] == stats["big_blind_hands"] == 10
        assert stats["net"] == performance([int(r[f"{seat}_net_chips"]) for r in rows])
    trace = [json.loads(line) for line in (tmp_path / "first/decisions.jsonl").read_text().splitlines()]
    assert len(trace) == sum(int(r["decisions"]) for r in rows)
    for entry in trace:
        obs = entry["observation"]
        assert not {"seed", "deck", "spec"} & obs.keys()
        for seat in obs["seats"]:
            if seat["id"] != obs["actor"]:
                assert seat["cards"] == seat["public_cards"]
        assert entry["action"] in {a["id"] for a in obs["legal_actions"]}
    with pytest.raises(FileExistsError):
        await experiment(cfg, tmp_path / "first")


@pytest.mark.asyncio
async def test_failure_is_recorded_and_not_comparable(tmp_path, monkeypatch):
    async def broken(*args):
        raise RuntimeError("deliberate failure")
    monkeypatch.setattr("pokerbench.benchmark.play_action", broken)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="deliberate"):
        await experiment(Config(hands=4), output)
    report = json.loads((output / "experiment.json").read_text())
    assert report["status"] == "failed"
    assert report["completed_hands"] == 0
    with pytest.raises(ValueError, match="completed"):
        build([output / "experiment.json"], tmp_path / "dashboard.html")


@pytest.mark.asyncio
async def test_dashboard_has_only_aggregate_results_and_escapes_labels(tmp_path):
    output = tmp_path / "<script>injected"
    await experiment(Config(hands=4), output)
    page = tmp_path / "dashboard.html"
    build([output / "experiment.json"], page)
    html = page.read_text()
    assert "<script>injected" not in html
    assert "observation" not in html
    assert '"source_sha256"' not in html
    assert '"completed_hands": 4' in html
    with pytest.raises(FileExistsError):
        build([output / "experiment.json"], page)


def equity_observation(hole, board):
    return {"actor": "a", "seats": [{"id": "a", "cards": hole}, {"id": "b", "cards": ["??", "??"]}],
            "board": board}


def test_equity_royal_flush_and_board_tie():
    agent = EquityHeuristicAgent(1, 32)
    assert agent.estimate_equity(equity_observation(["Ah", "Kh"], ["Qh", "Jh", "Th", "2c", "3d"])) == 1
    assert agent.estimate_equity(equity_observation(["2c", "3d"], ["Ah", "Kh", "Qh", "Jh", "Th"])) == 0.5


def test_equity_reproducible_uses_no_opponent_private_cards():
    obs = equity_observation(["As", "Ah"], [])
    first = EquityHeuristicAgent(9, 100).estimate_equity(obs)
    obs["seats"][1]["cards"] = ["Ac", "Ad"]  # Malicious extra data must be ignored.
    assert EquityHeuristicAgent(9, 100).estimate_equity(obs) == first
    assert 0.6 < first < 1
    with pytest.raises(ValueError):
        EquityHeuristicAgent(1, 0)


@pytest.mark.asyncio
async def test_equity_policy_price_and_value_raise(monkeypatch):
    agent = EquityHeuristicAgent(1)
    h = hand()
    monkeypatch.setattr(agent, "estimate_equity", lambda _: 0.1)
    assert await agent.choose_action(h.observation()) == "fold"
    monkeypatch.setattr(agent, "estimate_equity", lambda _: 0.5)
    assert await agent.choose_action(h.observation()) == "call"
    monkeypatch.setattr(agent, "estimate_equity", lambda _: 0.9)
    choice = await agent.choose_action(h.observation())
    assert choice == min((a for a in h.legal() if a.kind == "raise" and not a.all_in), key=lambda a: a.to).id


@pytest.mark.asyncio
async def test_equity_agent_completes_real_benchmark_hands(tmp_path):
    report = await experiment(Config(hands=10, agent_b="equity", equity_samples=8), tmp_path / "equity")
    assert report["summary"]["completed_hands"] == 10
    assert report["summary"]["agents"]["b"]["policy"] == "equity"
