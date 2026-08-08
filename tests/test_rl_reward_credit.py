"""
Component 2.5 — the bandit must learn from the arm it actually pulled.

`MasterPlanner.process_command` selects a routing arm when the intent classifier
is not confident, then feeds the outcome back as a reward. It used to credit
`ROUTING_ACTIONS.index("direct_dispatch")` on both the success and the failure
branch, regardless of which arm was selected. The consequence was not a cosmetic
one: three of the four arms were never updated, so their Q-values stayed at their
initial zero and `get_policy()`'s argmax was decided by array initialisation
rather than by anything the bandit had observed. The component could not learn.

These tests pin the wiring, not the policy — which arm wins is up to the data.
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner
from ml.rl_router import ROUTING_ACTIONS, EpsilonGreedyBandit


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clear_state(planner):
    planner.pending_clarification = None
    yield
    planner.pending_clarification = None


class _FixedArmBandit(EpsilonGreedyBandit):
    """A bandit that always pulls one chosen arm and records every update."""

    def __init__(self, arm: int) -> None:
        super().__init__()
        self._arm = arm
        self.updates: list[tuple[int, float]] = []

    def select_action(self) -> int:
        return self._arm

    def update(self, action: int, reward: float) -> None:
        self.updates.append((action, reward))
        super().update(action, reward)


@pytest.mark.parametrize("arm", range(len(ROUTING_ACTIONS)))
def test_reward_goes_to_the_arm_that_was_pulled(planner, arm, monkeypatch):
    """
    Whichever arm the bandit selects is the arm the outcome describes. A command
    the classifier is unsure of is what puts the bandit in the loop at all.
    """
    spy = _FixedArmBandit(arm)
    monkeypatch.setattr(planner, "rl_bandit", spy)

    # Gibberish: low classifier confidence, so `fallback` is True and the bandit
    # is consulted. If the classifier ever grows confident about this string the
    # assertion below stops testing anything, so check that first.
    planner.process_command("qwzx plorble frotz vimble")

    assert spy.updates, "bandit was never consulted — pick a less classifiable command"
    credited = {action for action, _ in spy.updates}
    assert credited == {arm}, (
        f"selected arm {arm} ({ROUTING_ACTIONS[arm]}) but credited {credited}"
    )


def test_confident_commands_credit_direct_dispatch(planner, monkeypatch):
    """
    When the classifier is confident the bandit is not asked to choose, and the
    outcome is evidence about direct dispatch specifically.
    """
    spy = _FixedArmBandit(ROUTING_ACTIONS.index("clarify_user"))
    monkeypatch.setattr(planner, "rl_bandit", spy)

    result = planner.process_command("what time is it")

    if result["intent_classification"]["llm_fallback"]:
        pytest.skip("classifier was not confident about this command")

    assert result["rl_routing"]["strategy"] == "direct_dispatch"
    assert {a for a, _ in spy.updates} == {ROUTING_ACTIONS.index("direct_dispatch")}


def test_every_arm_is_reachable_by_the_learner():
    """
    The regression in one line: with rewards credited correctly, pulling an arm
    moves that arm's Q-value and leaves the others alone.
    """
    bandit = EpsilonGreedyBandit()
    arm = ROUTING_ACTIONS.index("hybrid_check")
    bandit.update(arm, 1.0)

    assert bandit.q_values[arm] > 0
    assert all(
        bandit.q_values[i] == 0 for i in range(len(ROUTING_ACTIONS)) if i != arm
    )
