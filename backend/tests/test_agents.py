from copy import deepcopy
import json

import pytest

from pokerbench.agents import HeuristicAgent, RandomAgent, play_action
from pokerbench.engine import Hand
from pokerbench.local_play import run


def new_hand(seed=42):
    return Hand([{"id": "private-model-a", "stack": 20000},
                 {"id": "private-model-b", "stack": 20000}],
                button=0, blinds=(50, 100, 0), seed=seed, chip_unit=50)


@pytest.mark.asyncio
async def test_agent_gets_only_actor_information_and_cannot_mutate_cards():
    hand = new_hand()
    before = deepcopy(hand.original_holes)

    class InspectingAgent:
        async def choose_action(self, observation):
            encoded = json.dumps(observation)
            assert "private-model" not in encoded
            assert not {"seed", "deck", "spec", "decision"} & observation.keys()
            for seat in observation["seats"]:
                if seat["id"] == observation["actor"]:
                    assert "??" not in seat["cards"]
                    seat["cards"][0] = "INVALID"
                else:
                    assert seat["cards"] == ["??", "??"]
            observation["legal_actions"].clear()
            return "call"

    assert await play_action(hand, InspectingAgent()) == "call"
    assert hand.original_holes == before
    assert hand.actions[-1]["id"] == "call"


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", ["raise_to_1", "invented", None, {}])
async def test_illegal_agent_choice_does_not_change_hand(choice):
    hand = new_hand()
    before = deepcopy(hand.record())

    class InvalidAgent:
        async def choose_action(self, observation):
            return choice

    with pytest.raises(ValueError, match="illegal"):
        await play_action(hand, InvalidAgent())
    assert hand.record() == before


@pytest.mark.asyncio
async def test_stale_decision_is_rejected():
    hand = new_hand()

    class DelayedAgent:
        async def choose_action(self, observation):
            hand.apply("call")  # Simulate another server task advancing the hand.
            return "call"

    with pytest.raises(ValueError, match="Stale"):
        await play_action(hand, DelayedAgent())
    assert len(hand.actions) == 1


@pytest.mark.asyncio
async def test_finished_hand_never_calls_agent():
    hand = new_hand()
    hand.apply("fold")

    class NeverCalled:
        async def choose_action(self, observation):
            pytest.fail("Finished hand reached agent")

    with pytest.raises(ValueError, match="No acting"):
        await play_action(hand, NeverCalled())


@pytest.mark.asyncio
async def test_heuristic_price_threshold_and_check():
    agent = HeuristicAgent()
    hand = new_hand()
    assert await agent.choose_action(hand.observation()) == "call"
    hand.apply("raise_to_20000")
    assert await agent.choose_action(hand.observation()) == "fold"
    hand = new_hand()
    hand.apply("call")
    assert await agent.choose_action(hand.observation()) == "check"


@pytest.mark.asyncio
async def test_random_agent_reproducible_and_covers_offered_actions():
    observation = new_hand().observation()
    a, b = RandomAgent(7), RandomAgent(7)
    choices = [await a.choose_action(observation) for _ in range(200)]
    assert choices == [await b.choose_action(observation) for _ in range(200)]
    assert set(choices) == {action["id"] for action in observation["legal_actions"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", [0, 19, 235])
async def test_real_heads_up_hands_complete_conserve_chips_and_repeat(seed):
    result = await run(20, deck_seed=seed, policy_seed=99)
    assert result == await run(20, deck_seed=seed, policy_seed=99)
    assert result["hands"] == 20
    assert result["decisions"] >= 20
    assert sum(result["profit_chips"].values()) == 0


@pytest.mark.asyncio
async def test_smoke_rejects_empty_run():
    with pytest.raises(ValueError, match="positive"):
        await run(0)
