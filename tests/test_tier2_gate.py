"""
Tier-2 approval gate — enforcement tests (PRD §9, CLO01).

The pre-existing tests in test_100_ruthless.py assert that
`evaluate_action_permission` *classifies* actions correctly. They passed the
whole time the gate was bypassable, because classification was never the broken
part: the UI posted `user_approved: true` on every command and the planner
honoured it, so nothing ever stopped to ask.

These tests therefore assert the behaviour that actually matters — that an
irreversible action does not run until the user approves it in a separate turn.
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner, parse_confirmation
from core.security import TIER_2_ACTIONS, TIER_2_IMPLEMENTED


@pytest.fixture(scope="module")
def planner():
    """One planner for the module — construction loads the ML pipelines."""
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clear_state(planner):
    """No test may inherit another's pending confirmation."""
    planner.pending_clarification = None
    yield
    planner.pending_clarification = None


def _exec(result):
    return result["execution_result"]


# ── The confirmation vocabulary ──────────────────────────────────────────────
@pytest.mark.parametrize(
    "reply,expected",
    [
        ("yes", "yes"), ("y", "yes"), ("approve", "yes"), ("go ahead", "yes"),
        ("do it", "yes"), ("confirm", "yes"), ("send", "yes"),
        ("no", "no"), ("cancel", "no"), ("abort", "no"), ("don't", "no"),
        ("never mind", "no"), ("stop", "no"),
        ("maybe", "unclear"), ("", "unclear"), ("what?", "unclear"),
        ("i guess so", "unclear"),
        # A comma is punctuation, not hesitation.
        ("yes, send it", "yes"), ("no, cancel that", "no"),
        ("yes, show me the result", "yes"), ("no, show me something else", "no"),
        # …but it must not manufacture a decision out of one.
        ("maybe, yes", "unclear"), ("not sure, ask me later", "unclear"),
    ],
)
def test_parse_confirmation(reply, expected):
    assert parse_confirmation(reply) == expected


def test_negation_is_not_read_as_approval():
    """'don't send it' contains 'send' and must never parse as affirmative."""
    assert parse_confirmation("don't send it") == "no"


def test_new_command_is_not_read_as_approval():
    """
    A fresh 'send mail to ...' must not confirm a previously pending draft.
    The old implementation used answer.startswith("send"), which did exactly
    that — it would deliver a stale draft to the wrong recipient.
    """
    assert parse_confirmation("send mail to someone@example.com") == "unclear"


# ── Enforcement: the flag cannot approve ─────────────────────────────────────
def test_tier2_not_executed_despite_user_approved_flag(planner):
    """The central regression: user_approved=True must NOT bypass the gate."""
    res = _exec(planner.process_command("kill notepad", user_approved=True))
    assert res.get("awaiting_tier2_approval") is True
    assert res.get("risk_tier") == 2
    assert res.get("executed") is not True
    assert planner.pending_clarification is not None


def test_tier2_prompt_carries_eta_from_component_2_2(planner):
    """The confirmation prompt must quote an ETA — 2.2's production role."""
    res = _exec(planner.process_command("kill notepad"))
    assert isinstance(res.get("predicted_eta_seconds"), (int, float))
    assert res["predicted_eta_seconds"] > 0
    # The prompt was shortened for speech; what must survive is that the
    # ETA from component 2.2 is still shown to the user (PRD §9).
    assert "est." in res["message"].lower()


def test_email_send_still_gated_despite_flag(planner):
    """Email was already correct; keep it that way."""
    res = _exec(
        planner.process_command(
            'send mail to test@example.com subject: "Hi" body: "Hello"',
            user_approved=True,
        )
    )
    assert res.get("awaiting_send_confirmation") is True
    assert res.get("delivered") is not True


# ── Enforcement: the three replies ───────────────────────────────────────────
def test_ambiguous_reply_reasks_and_stays_armed(planner):
    planner.process_command("kill notepad")
    res = _exec(planner.process_command("maybe"))
    assert res.get("awaiting_tier2_approval") is True
    assert res.get("executed") is not True
    # Still armed, so the user can still answer properly.
    assert planner.pending_clarification is not None


def test_negative_reply_cancels_and_clears(planner):
    planner.process_command("kill notepad")
    res = _exec(planner.process_command("no"))
    assert res.get("cancelled") is True
    assert res.get("executed") is False
    assert planner.pending_clarification is None


def test_affirmative_reply_executes(planner):
    """Approval reaches the executor. The target does not exist, so the action
    reports 'not found' — the point is that it ran at all."""
    planner.process_command("kill definitely_not_a_real_process_xyz")
    res = _exec(planner.process_command("yes"))
    assert res.get("approved_by_user") is True
    assert res.get("awaiting_tier2_approval") is not True
    assert res.get("message")  # never silent after an approval
    assert planner.pending_clarification is None


# ── Abandoning the gate for a new command ────────────────────────────────────
# `process_command` clears a pending clarification when the next turn looks like
# a new topic. That heuristic used to run *before* the confirmation was parsed
# and said nothing when it fired, so an armed gate could vanish in silence.
def test_new_topic_cancels_the_gate_but_says_so(planner):
    """Walking away from an approval is allowed. Doing it silently is not."""
    planner.process_command("kill notepad")
    assert planner.pending_clarification is not None

    res = _exec(planner.process_command("what time is it"))

    assert planner.pending_clarification is None          # gate released
    assert res.get("cancelled_pending_approval") is True  # and announced
    assert "cancelled the pending approval" in res.get("message", "").lower()
    assert res.get("executed") is not True                # nothing ran


def test_confirmation_wins_over_the_new_topic_heuristic(planner):
    """
    'show'/'what'/'how' are new-topic markers, but a reply that parses as a
    clear yes or no is an answer to the question on the table. Before the fix,
    "no, show me something else" was read as a new command and the gate was
    dropped rather than declined.
    """
    planner.process_command("kill notepad")
    res = _exec(planner.process_command("no, show me something else"))

    assert res.get("cancelled") is True                   # declined, not dropped
    assert res.get("cancelled_pending_approval") is not True
    assert planner.pending_clarification is None


def test_low_stakes_clarification_still_clears_quietly(planner):
    """
    The announcement is reserved for approval gates. A "which contact did you
    mean?" prompt carries no authorisation, so abandoning it needs no notice —
    and test_100_ruthless.py asserts that clearing behaviour.
    """
    planner.pending_clarification = {"type": "select_email"}
    res = _exec(planner.process_command("what time is it"))

    assert planner.pending_clarification is None
    assert res.get("cancelled_pending_approval") is not True


# ── The executor registry ────────────────────────────────────────────────────
def test_unregistered_executor_is_refused(planner):
    """Only registered actions can be parked for approval."""
    res = planner.require_tier2_approval(
        action_name="rm_rf_everything",
        target="/",
        executor="not_registered",
        executor_kwargs={},
        original_command="destroy everything",
    )
    assert res["success"] is False
    assert res["error"] == "UNKNOWN_TIER2_EXECUTOR"
    assert planner.pending_clarification is None


def test_pending_state_is_plain_data(planner):
    """
    The parked state must stay serialisable — no callables. It is written to the
    audit log and returned across the API boundary.
    """
    import json

    planner.process_command("kill notepad")
    json.dumps(planner.pending_clarification)  # raises if a callable sneaked in


# ── Policy list honesty ──────────────────────────────────────────────────────
def test_implemented_subset_is_actually_a_subset():
    assert TIER_2_IMPLEMENTED <= TIER_2_ACTIONS
