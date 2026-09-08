"""
ROADMAP Phase 13 — stage 4, a hosted model for the hard questions.

**Everything here runs with a stubbed key**, because this machine has none. That
is the entire reason the file is thorough: the last hosted path in this
repository was inert for want of a key, went unexercised for weeks, and was
found on 2026-08-18 to be reporting generated text as work done, discarding
evidenced results, and swallowing the stage-3 proposal gate. "It never runs
here" is a claim about the environment, not about the code.

The containment argument for stage 4 is different from stage 3's, and stronger:
it **answers, it does not act**. It is never offered the tool schema, its reply
is never parsed as a skill name, and so there is no path from it to an action
that guards could fail to close. The tests below assert the absence of that
path rather than the correctness of a filter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from core.llm_remote import RemoteAnswerStage, remote_key_configured
from core.planner import MasterPlanner
from core.router import Router
from ml.intent_classifier import predict_intent


class _StubRemote:
    """A configured hosted model, without a key or a network."""

    model = "stub-hosted"

    def __init__(self, reply: Optional[str] = "Because the earth is tilted.") -> None:
        self.reply = reply
        self.asked: List[str] = []
        self.memories: List[Any] = []
        self.history: List[Any] = []

    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def answer(self, command, memories=None, history=None):
        self.asked.append(command)
        self.memories = list(memories or [])
        self.history = list(history or [])
        return self.reply


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture
def local_stages_only(planner):
    """Stage 3 off, so stage 4 is reached — its only trigger."""
    original_llm, original_remote = planner.router.llm, planner.router.remote
    planner.router.llm = None
    yield planner
    planner.router.llm, planner.router.remote = original_llm, original_remote


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


# ── Off by default ───────────────────────────────────────────────────────────
def test_no_key_means_no_hosted_model(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    stage = RemoteAnswerStage()

    if remote_key_configured():
        pytest.skip("a hosted key is configured on this machine")
    assert stage.available() is False
    assert "GEMINI_API_KEY" in stage.unavailable_reason


def test_a_key_can_still_be_switched_off(monkeypatch):
    """`MONDAY_REMOTE_LLM=off` is the escape hatch `MONDAY_LLM=off` gives stage
    3: a demo must be able to guarantee that nothing leaves the machine."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key-0123456789")
    monkeypatch.setenv("MONDAY_REMOTE_LLM", "off")

    stage = RemoteAnswerStage()
    assert stage.available() is False
    assert "MONDAY_REMOTE_LLM" in stage.unavailable_reason


def test_an_unavailable_stage_answers_nothing(monkeypatch):
    monkeypatch.setenv("MONDAY_REMOTE_LLM", "off")
    assert RemoteAnswerStage().answer("anything") is None


def test_the_cascade_is_unchanged_without_a_key(planner, local_stages_only):
    """The property that matters most: a machine with no key behaves exactly as
    it did before this file existed."""
    local_stages_only.router.remote = RemoteAnswerStage(enabled=False)
    decision = _route(local_stages_only, "xyzzy plugh nothing matches this")

    assert decision.routed is False
    assert decision.stage == "fallback"


# ── It answers, and only answers ─────────────────────────────────────────────
def test_a_hosted_answer_is_returned_when_everything_else_declined(planner, local_stages_only):
    stub = _StubRemote()
    local_stages_only.router.remote = stub
    decision = _route(local_stages_only, "xyzzy plugh why are there seasons")

    assert decision.stage == "remote_answer"
    assert decision.answer == "Because the earth is tilted."
    assert decision.skill is None, "stage 4 must never select a skill"
    assert stub.asked, "the hosted model was not consulted"


def test_it_is_never_offered_a_skill_to_choose(planner, local_stages_only):
    """The containment argument is the absence of a code path, not a filter.

    `RemoteAnswerStage` has no `choose`; the router never passes it the tool
    schema; nothing parses its reply as a skill name. A reviewer looking for a
    route from stage 4 to an action should find none, and this asserts it.
    """
    stage = RemoteAnswerStage()
    assert not hasattr(stage, "choose")

    import inspect

    import core.llm_remote as remote_module

    source = inspect.getsource(remote_module)
    # Code-shaped tokens only. "tier" was in this list and matched the module's
    # own docstring explaining that stage 4 cannot reach Tier 2 — a scan of
    # prose is a scan of the wrong thing.
    for forbidden in ("llm_reachable_skills", "build_tool_schema", "tool_calls",
                      "registry.get", "decision.skill"):
        assert forbidden not in source, (
            f"core/llm_remote.py mentions {forbidden!r} — stage 4 answers, it "
            f"does not act"
        )


def test_a_pattern_still_wins_over_the_hosted_model(planner, local_stages_only):
    """Stage 4 is last. Nothing it could say may displace an exact match."""
    stub = _StubRemote()
    local_stages_only.router.remote = stub
    decision = _route(local_stages_only, "what time is it")

    assert decision.stage == "pattern"
    assert decision.skill.name == "tell_time"
    assert stub.asked == [], "the hosted model was consulted for a matched command"


def test_stage_3_answering_stops_the_cascade(planner):
    """Nothing leaves the machine when a local model already answered."""
    from core.llm import LlmChoice

    class _LocalAnswers:
        model = "llama-stub"
        unavailable_reason = ""

        def choose(self, command, on_token=None, history=None, memories=None, direct_answer=False):
            return LlmChoice(text="A local answer.", model=self.model)

    stub = _StubRemote()
    original_llm, original_remote = planner.router.llm, planner.router.remote
    planner.router.llm, planner.router.remote = _LocalAnswers(), stub
    try:
        decision = _route(planner, "xyzzy plugh why are there seasons")
    finally:
        planner.router.llm, planner.router.remote = original_llm, original_remote

    assert decision.stage == "llm_answer"
    assert stub.asked == [], "stage 4 ran after a local model had answered"


def test_a_hosted_model_that_declines_leaves_the_honest_refusal(planner, local_stages_only):
    local_stages_only.router.remote = _StubRemote(reply=None)
    decision = _route(local_stages_only, "xyzzy plugh nothing matches this")

    assert decision.routed is False
    assert "stage 4 declined" in decision.reason


# ── What the answer claims ───────────────────────────────────────────────────
def test_a_hosted_answer_says_it_left_the_machine(planner, local_stages_only):
    """A user is entitled to know an answer was not local without reading the
    configuration, so `host` carries it in the evidence."""
    local_stages_only.router.remote = _StubRemote()
    result = local_stages_only.process_command(
        "xyzzy plugh why are there seasons"
    )["execution_result"]

    assert result["success"] is True
    assert result["evidence"]["kind"] == "model_answered"
    assert result["evidence"]["host"] == "remote"
    assert result["evidence"]["model"] == "stub-hosted"
    assert result["generated"] is True


def test_a_local_answer_still_says_local(planner):
    from core.llm import LlmChoice

    class _LocalAnswers:
        model = "llama-stub"
        unavailable_reason = ""

        def choose(self, command, on_token=None, history=None, memories=None, direct_answer=False):
            return LlmChoice(text="A local answer.", model=self.model)

    original = planner.router.llm
    planner.router.llm = _LocalAnswers()
    try:
        result = planner.process_command(
            "xyzzy plugh why are there seasons"
        )["execution_result"]
    finally:
        planner.router.llm = original

    assert result["evidence"]["host"] == "local"


def test_a_hosted_answer_is_marked_generated_in_the_prose_too(planner, local_stages_only):
    """A reader must be able to tell a generated answer from an observed one
    without inspecting the evidence dict."""
    local_stages_only.router.remote = _StubRemote()
    result = local_stages_only.process_command(
        "xyzzy plugh why are there seasons"
    )["execution_result"]
    assert result["message"].startswith("💭")


def test_the_hosted_model_sees_context_but_not_the_registry(planner, local_stages_only):
    """It gets what a question needs — prior turns and stored facts — and
    nothing that would let it pick an action."""
    stub = _StubRemote()
    local_stages_only.router.remote = stub
    # A command nothing matches: "why is that" alone reaches `answer_question`
    # by pattern, and stage 4 is never consulted for a command that routed.
    local_stages_only.router.route(
        "xyzzy plugh why is that",
        intent="unclear",
        confidence=0.1,
        history=[{"role": "user", "content": "tell me about tides"}],
        memories=[{"key": "city", "value": "Chandigarh", "topic": "general"}],
    )

    assert stub.history and stub.history[0]["content"] == "tell me about tides"
    assert stub.memories and stub.memories[0]["value"] == "Chandigarh"


# ── The router without one ───────────────────────────────────────────────────
def test_a_router_built_without_stage_4_is_unaffected(planner):
    registry = planner.router.registry
    router = Router(registry, llm=None, remote=None)

    assert router.route("what time is it").stage == "pattern"
    assert router.route("xyzzy plugh").routed is False
