"""
ROADMAP Phase 10 — more than one step, honestly reported.

`core/task_dag_engine.py` was deleted for this. Measured on 2026-08-18, before
it went:

    > summarize nonexistent_file_xyzzy.pdf and then email it to nobody@example.invalid
      success: True   evidence: None
      "✓ Dynamic Task DAG Executed Successfully (2 Steps Completed)"

    > kill notepad and then tell me the time
      Step 1: ⚠️ terminate_process → notepad · Approve? Reply 'yes'…
      Step 2: ↩️ Cancelled the pending approval — you asked for something else
      success: True

The second is the one that mattered. It armed the Tier-2 gate, cancelled it with
the next step, killed nothing, and reported the whole thing as a success — a
fabricated success on the one path in this repository that touches an
irreversible action. Its own test asserted `success is True`, which is how it
survived.

The replacement executes each step by re-entering `MasterPlanner.process_command`,
so a step inherits the moral firewall, the classifier, slot sanity, the proposal
gate, the Tier-2 gate, the audit log and the spoken form rather than restating
any of them. Most of this file is about the two things a plan may not do:
**claim more than happened**, and **walk through a gate**.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from core.multi_step import MAX_STEPS, run_steps, split_compound
from core.planner import MasterPlanner


# ── Splitting ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("command,expected", [
    ("what time is it and then tell me the date", ["what time is it", "tell me the date"]),
    ("organize downloads, then tell me the time", ["organize downloads", "tell me the time"]),
    ("check the battery after that tell me the time", ["check the battery", "tell me the time"]),
    ("tell me the news and then the weather and then the time",
     ["tell me the news", "the weather", "the time"]),
])
def test_an_explicit_sequence_becomes_steps(command, expected):
    assert split_compound(command) == expected


@pytest.mark.parametrize("command", [
    # A conjunction inside one command. Splitting on a bare "and" would break
    # every one of these.
    "remember milk and eggs",
    "send mail to a@b.com subject hi body hello and thanks",
    "tell me the news and weather",
    "what is the difference between a list and a tuple",
    # A connective inside quotes belongs to the message, not to the plan.
    'message 9876543210 saying "call me and then text me"',
    # Too short a fragment means the split misread the sentence.
    "what then",
])
def test_a_single_command_stays_single(command):
    assert split_compound(command) == [command]


def test_an_empty_command_produces_no_steps():
    assert split_compound("") == []
    assert split_compound("   ") == []


# ── What a plan may claim ────────────────────────────────────────────────────
def _recorder(outcomes: Dict[str, bool]):
    """An `execute` that succeeds or fails per command, recording the order."""
    calls: List[str] = []

    def execute(command: str) -> Dict[str, Any]:
        calls.append(command)
        ok = outcomes.get(command, True)
        return {
            "success": ok,
            "message": f"ran {command}",
            "error": "" if ok else "STEP_FAILED",
            "evidence": {"kind": "system_query", "source": command} if ok else None,
        }

    return execute, calls


def test_every_step_succeeding_is_the_only_success():
    execute, calls = _recorder({})
    result = run_steps(["one thing", "two thing"], execute)

    assert result["success"] is True
    assert result["steps_completed"] == 2
    assert calls == ["one thing", "two thing"]


def test_a_failed_step_stops_the_plan():
    """Step 2 usually depends on step 1 having happened. Running it anyway is
    how the old engine summarised a search that had returned nothing."""
    execute, calls = _recorder({"two thing": False})
    result = run_steps(["one thing", "two thing", "three thing"], execute)

    assert result["success"] is False
    assert result["error"] == "STEP_FAILED"
    assert result["steps_completed"] == 1
    assert calls == ["one thing", "two thing"], "the plan continued past a failure"


def test_the_steps_that_did_run_are_still_reported():
    """A user whose plan stopped half-way needs to know what state the machine
    is in. Hiding the completed steps would leave them guessing."""
    execute, _ = _recorder({"two thing": False})
    message = run_steps(["one thing", "two thing"], execute)["message"]

    assert "one thing ✓" in message
    assert "two thing ✗" in message
    assert message.count("one thing") == 1, "a step was listed twice"


def test_a_plan_claims_no_evidence_of_its_own():
    """Each step carried its own; the aggregate is the sum and nothing more."""
    execute, _ = _recorder({})
    result = run_steps(["one thing", "two thing"], execute)

    assert "evidence" not in result
    assert len(result["step_evidence"]) == 2


def test_a_plan_longer_than_the_budget_is_refused_and_says_so():
    execute, calls = _recorder({})
    steps = [f"step {n} here" for n in range(MAX_STEPS + 3)]
    result = run_steps(steps, execute)

    assert result["success"] is False
    assert result["error"] == "MULTI_STEP_OVER_BUDGET"
    assert len(calls) == MAX_STEPS, "the budget was not a hard stop"


# ── The gate ─────────────────────────────────────────────────────────────────
def test_a_step_awaiting_approval_stops_the_plan():
    """The old engine armed the gate and then cancelled it with the next step.

    A Tier-2 prompt reports `success: True` — it succeeded at *asking* — so a
    plan that only checked success would walk straight through it, which is
    exactly what happened.
    """
    calls: List[str] = []

    def execute(command: str) -> Dict[str, Any]:
        calls.append(command)
        if command == "kill notepad":
            return {
                "success": True,            # the prompt was shown, not the kill
                "awaiting_approval": True,
                "pending_clarification": True,
                "message": "⚠️ terminate_process → notepad · Approve?",
            }
        return {"success": True, "message": f"ran {command}"}

    result = run_steps(["kill notepad", "tell me the time"], execute)

    assert result["success"] is False
    assert result["error"] == "MULTI_STEP_NEEDS_APPROVAL"
    assert calls == ["kill notepad"], "the plan ran a step after arming a gate"
    assert "Reply 'yes'" in result["message"]


def test_the_pending_step_is_not_counted_as_completed():
    def execute(command: str) -> Dict[str, Any]:
        return {"success": True, "awaiting_approval": True, "message": "Approve?"}

    result = run_steps(["kill notepad", "tell me the time"], execute)
    assert result["steps_completed"] == 0


# ── End to end, through the real planner ─────────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


def test_two_offline_steps_both_run(planner):
    planner.pending_clarification = None
    result = planner.process_command(
        "what time is it and then tell me the date"
    )["execution_result"]

    assert result["success"] is True
    assert result["steps_completed"] == 2
    assert result["multi_step"] is True


def test_a_tier_2_step_inside_a_plan_still_asks(planner):
    """The regression that deleted the old engine.

    It reported "✓ Dynamic Task DAG Executed Successfully" for this exact
    command, having armed the gate and cancelled it, with notepad still running.
    """
    planner.pending_clarification = None
    result = planner.process_command(
        "kill notepad and then tell me the time"
    )["execution_result"]

    assert result["success"] is False
    assert result["error"] == "MULTI_STEP_NEEDS_APPROVAL"
    assert planner.pending_clarification is not None, "the gate was dropped"
    assert "terminate_process" in result["message"]
    planner.pending_clarification = None


def test_a_plan_is_never_split_again_inside_itself(planner):
    """`_in_multi_step` guards the re-entry. Without it a step that still
    contained a connective would recurse without bound."""
    planner.pending_clarification = None
    assert planner._in_multi_step is False
    planner.process_command("what time is it and then tell me the date")
    assert planner._in_multi_step is False, "the guard was left set"


def test_a_single_command_is_untouched_by_any_of_this(planner):
    """The overwhelmingly common case must not pay for the rare one."""
    planner.pending_clarification = None
    result = planner.process_command("what time is it")["execution_result"]

    assert result["success"] is True
    assert "multi_step" not in result
