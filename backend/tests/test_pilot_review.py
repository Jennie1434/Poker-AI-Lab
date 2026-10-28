import asyncio

import pytest

from pokerbench import pilot_review as pr
from pokerbench.compare import CFRAdvisor, request_hash
from pokerbench.jev_pilot import PLAN, body, read_plan

CRITERIA = {"fold": {"action": "fold"}, "call": {"action": "call"}, "raise_to_300": {"action": "raise"},
            "raise_to_600": {"action": "raise"}, "raise_to_20000": {"action": "raise"}}


def test_families_sum_raise_sizes():
    probs = {"fold": 0.2, "call": 0.35, "raise_to_300": 0.15, "raise_to_600": 0.15, "raise_to_20000": 0.15}
    mass = pr.families(probs, CRITERIA)
    assert mass == pytest.approx({"fold": 0.2, "check/call": 0.35, "bet/raise": 0.45})
    # The top single action is passive, but the raise family is the largest.
    assert max(probs, key=probs.get) == "call" and pr.top(mass) == "bet/raise"
    spread = pr.raise_spread(probs, CRITERIA)
    assert spread["sizes_used"] == 3 and spread["largest_share"] == pytest.approx(1 / 3)
    assert pr.raise_spread({"fold": 1.0}, {"fold": {"action": "fold"}})["largest_share"] is None


def test_strength_reads_made_hands_and_preflop_table():
    river = {"actor": "p", "seats": [{"id": "p", "cards": ["As", "Ks"]}], "board": ["Qs", "Js", "Ts", "2d", "3c"]}
    s = pr.strength(river, __import__("random").Random(1), samples=50)
    assert s["made"] == "Royal Flush" and s["strong"] and s["equity"] == 1.0
    pre = pr.strength({"actor": "p", "seats": [{"id": "p", "cards": ["Ah", "Ad"]}], "board": []},
                      __import__("random").Random(1))
    assert pre["strong"] and pre["equity"] > 0.8


@pytest.fixture(scope="module")
def sample():
    plan = read_plan(PLAN)[::25]
    cfr = {request_hash(body(r)): asyncio.run(CFRAdvisor("cfr-v2-adapt")(body(r)))["answers"]["action"]["probabilities"]
           for r in plan}
    return plan, cfr


def test_review_of_a_uniform_answerer(sample):
    plan, cfr = sample
    uniform = {request_hash(body(r)): {a: 1 / len(body(r)["questions"]["action"]["criteria"])
                                       for a in body(r)["questions"]["action"]["criteria"]} for r in plan}
    result = pr.review(plan, uniform, cfr)
    u = result["uniformity"]
    assert result["decisions"] == len(plan) and u["jev_tv_to_uniform"] == pytest.approx(0)
    assert u["jev_normalized_entropy"] == pytest.approx(1) and u["jev_raise_over_uniform"] == pytest.approx(0)
    assert u["jev_raise_family_mass_mean"] == pytest.approx(u["uniform_raise_family_mass_mean"])
    assert len(result["top15"]) == min(15, len(plan))
    total = sum(result["family_confusion_cfr_to_jev"].values())
    assert total == len(plan) and result["families"]["all"]["decisions"] == len(plan)


def test_review_of_cfr_against_itself_agrees_everywhere(sample):
    plan, cfr = sample
    result = pr.review(plan, cfr, cfr)
    assert result["families"]["all"]["family_agreement"] == 1
    assert result["families"]["all"]["top_action_agreement"] == 1
    assert result["size_split"]["hidden_aggression_decisions"] == sum(
        1 for r in plan if pr.top(pr.families(cfr[request_hash(body(r))], body(r)["questions"]["action"]["criteria"]))
        == "bet/raise" and body(r)["questions"]["action"]["criteria"][max(cfr[request_hash(body(r))],
                                                                         key=cfr[request_hash(body(r))].get)]["action"] != "raise")
