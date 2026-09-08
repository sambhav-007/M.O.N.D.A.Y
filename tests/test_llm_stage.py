"""
Stage 3 — the language model, and the things it is not allowed to do.

The router's third stage answers what stages 1 and 2 could not. That makes it
the only part of the routing cascade whose behaviour is not fully determined by
code in this repository, so the tests here are mostly about **containment**:
what the model is offered, what happens when it emits something it was not
offered, and what a generated answer is allowed to claim.

Nothing here needs a running model. The stage is driven with a stub, because
what is being tested is the validation around the model rather than the model
itself — and a suite that needed a 2 GB download to run would not be run.
`@pytest.mark.llm` marks the handful of cases that want a live one; they are
deselected by default, like `network`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from core.contracts import ModelAnswered
from core.intent_patterns import slot_spec
from core.llm import (
    CHOOSE_TIMEOUT,
    FIRST_CALL_TIMEOUT,
    PREFERRED_MODELS,
    SYSTEM_PROMPT,
    LlmChoice,
    LlmStage,
    _first_present,
    build_tool_schema,
    memory_context,
)
from core import planner as planner_module
from core.planner import MasterPlanner
from core.router import Router
from core.skills import Skill, SkillRegistry


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture
def registry(planner):
    return planner.router.registry


class StubLlm:
    """Stands in for `LlmStage`, recording whether it was consulted at all.

    The signature must track `LlmStage.choose`, including `on_token`. When
    streaming was added this double silently stopped matching the thing it
    doubles, and seven tests failed with `unexpected keyword argument` — which
    is the useful failure. A stub that swallowed `**kwargs` would have kept
    passing while testing a call the real router no longer makes.
    """

    def __init__(self, choice: Optional[LlmChoice] = None) -> None:
        self.choice = choice
        self.calls: List[str] = []
        self.history: List[Dict[str, str]] = []
        self.memories: List[Dict[str, Any]] = []
        self.model = "stub"
        self.unavailable_reason = "stub"

    def choose(
        self,
        command: str,
        on_token: Optional[Any] = None,
        history: Optional[List[Dict[str, str]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        direct_answer: bool = False,
    ) -> Optional[LlmChoice]:
        self.calls.append(command)
        self.history = list(history or [])
        self.memories = list(memories or [])
        if on_token is not None and self.choice is not None and self.choice.text:
            on_token(self.choice.text)
        return self.choice


def test_the_stub_still_matches_the_thing_it_stands_in_for(registry):
    """A double that has drifted from its subject tests nothing.

    Asserted mechanically because the drift is invisible otherwise: the stub
    keeps passing its own tests while the real router calls a signature it no
    longer has.
    """
    import inspect

    real = inspect.signature(LlmStage.choose).parameters
    stub = inspect.signature(StubLlm.choose).parameters
    assert set(real) == set(stub), (
        f"StubLlm.choose{tuple(stub)} no longer matches "
        f"LlmStage.choose{tuple(real)}"
    )


# ── Slots are derived, not declared twice ────────────────────────────────────
def test_slot_spec_reads_names_and_types_out_of_patterns():
    spec = slot_spec([
        "set volume to {level:int}",
        "open {target:app}",
        "remember {key} is {value}",
    ])
    assert spec == {"level": "int", "target": "app", "key": "", "value": ""}


def test_a_slot_typed_anywhere_is_reported_as_typed():
    """`{phone}` and `{phone:phone}` both appear in the WhatsApp patterns.

    The constrained reading is the more informative one, so it wins — otherwise
    the schema would describe a typed slot as a free string purely because of
    which pattern happened to be listed last.
    """
    assert slot_spec(["message {phone}", "message {phone:phone} {rest}"])["phone"] == "phone"


def test_skill_slots_come_from_its_own_patterns(registry):
    assert registry.get("set_volume").slots == {"level": "int"}
    assert "path" in registry.get("summarize_document").slots


# ── What the model is offered ────────────────────────────────────────────────
def test_the_schema_is_generated_from_the_registry(registry):
    tools = build_tool_schema(registry)
    assert len(tools) == len(registry.llm_reachable_skills())
    names = {t["function"]["name"] for t in tools}
    assert names == {s.name for s in registry.llm_reachable_skills()}
    for tool in tools:
        assert tool["function"]["description"], f"{tool['function']['name']} has no description"


def test_prompt_prefers_direct_answers_for_subjective_questions():
    assert "subjective, philosophical, ethical, or advice questions" in SYSTEM_PROMPT
    assert "instead of calling a web-search tool" in SYSTEM_PROMPT


def test_the_schema_arguments_match_the_patterns(registry):
    """A schema that drifts from the patterns is the stale-artefact bug again."""
    tools = {t["function"]["name"]: t for t in build_tool_schema(registry)}
    volume = tools["set_volume"]["function"]["parameters"]["properties"]
    assert set(volume) == {"level"}
    assert volume["level"]["type"] == "integer"


# ── What the model is NOT offered ────────────────────────────────────────────
def test_no_tier2_skill_is_ever_offered_to_the_model(registry):
    """The rule that irreversible actions need an exact pattern, extended.

    Stage 2 is already forbidden from reaching Tier 2 (`Skill.__post_init__`
    raises on it). A language model is a better guesser than a seven-class
    classifier, but it is still guessing, and `terminate_process` loses unsaved
    work either way.
    """
    offered = {s.name for s in registry.llm_reachable_skills()}
    for name in registry.tier2_names():
        assert name not in offered, f"Tier-2 skill {name} is reachable from the model"


def test_confirmation_recovery_skill_is_not_offered_to_the_model(registry):
    assert "stray_confirmation" not in {
        skill.name for skill in registry.llm_reachable_skills()
    }


def test_tier2_forces_llm_reachable_off_even_when_asked_for_it():
    skill = Skill(
        name="dangerous", patterns=["do the thing"], handler=lambda **_: {},
        tier=2, llm_reachable=True,
    )
    assert skill.llm_reachable is False


def test_generated_code_execution_is_not_reachable_from_the_model(registry):
    """`create_desktop_folder` runs Python under `subprocess`.

    Tier 1 is a statement about reversibility; this is a statement about what
    the implementation does. They are different questions, which is why the flag
    exists separately from the tier.
    """
    offered = {s.name for s in registry.llm_reachable_skills()}
    assert "create_desktop_folder" not in offered


# ── Validating what comes back ───────────────────────────────────────────────
def test_a_skill_name_we_never_offered_is_refused(registry):
    stage = LlmStage(registry)
    assert stage._validate("no_such_skill", {}) is None


def test_a_tier2_name_emitted_by_the_model_is_refused(registry):
    """Small models emit names they were not given. This is the backstop."""
    stage = LlmStage(registry)
    assert stage._validate("terminate_process", {"process": "explorer"}) is None


def test_the_code_execution_skill_is_refused_even_if_named(registry):
    stage = LlmStage(registry)
    assert stage._validate("create_desktop_folder", {}) is None


def test_unknown_arguments_are_dropped_and_recorded(registry):
    """Dropped rather than fatal, and never silent.

    Every handler takes `**_`, so an invented key is inert — the real risk is a
    wrong *value* in a known key, which rejecting unknown keys would not catch.
    Refusing the whole call would make a 3B model useless; dropping without
    saying so would hide what the model did.
    """
    stage = LlmStage(registry)
    choice = stage._validate("set_volume", {"level": 40, "colour": "blue"})
    assert choice is not None
    assert choice.arguments == {"level": 40}
    assert choice.dropped == ["colour"]


def test_typed_slots_are_coerced(registry):
    stage = LlmStage(registry)
    choice = stage._validate("set_volume", {"level": "40"})
    assert choice.arguments == {"level": 40}


def test_an_uncoercible_value_drops_the_argument_not_the_call(registry):
    """`set volume to "loud"` should reach the volume skill and be told what is
    wrong by the handler, rather than vanishing into a refusal."""
    stage = LlmStage(registry)
    choice = stage._validate("set_volume", {"level": "loud"})
    assert choice is not None and choice.skill == "set_volume"
    assert choice.arguments == {}
    assert choice.dropped == ["level"]


# ── The cascade order ────────────────────────────────────────────────────────
def test_a_pattern_match_never_consults_the_model(registry):
    """Stage 3 must not be able to change what stage 1 already decided.

    This is the property that keeps `DEMO.md` offline and the Tier-2 gate exact,
    and it is worth asserting on the *call*, not on the outcome: a stage 3 that
    ran and was ignored would still cost a user seconds and a socket.
    """
    stub = StubLlm(LlmChoice(skill="chitchat", model="stub"))
    router = Router(registry, llm=stub)
    decision = router.route("what time is it")
    assert decision.stage == "pattern"
    assert decision.skill.name == "tell_time"
    assert stub.calls == [], "stage 3 was consulted despite a pattern match"


def test_the_model_is_consulted_only_when_the_other_stages_decline(registry):
    stub = StubLlm(LlmChoice(skill="system_health", model="stub"))
    router = Router(registry, llm=stub)
    decision = router.route("give me a rundown of this machine")
    assert stub.calls == ["give me a rundown of this machine"]
    assert decision.stage == "llm"
    assert decision.skill.name == "system_health"


def test_the_routing_decision_records_what_the_model_did(registry):
    stub = StubLlm(LlmChoice(skill="system_health", model="llama3.2:3b", dropped=["mood"]))
    router = Router(registry, llm=stub)
    decision = router.route("xyzzy plugh")
    assert "llama3.2:3b" in decision.reason
    assert "dropped mood" in decision.reason


def test_a_refused_model_choice_falls_through_to_the_honest_refusal(registry):
    """The model named something it was not offered, so nothing routes."""
    stub = StubLlm(LlmChoice(skill=None, model="stub"))
    router = Router(registry, llm=stub)
    decision = router.route("xyzzy plugh")
    assert decision.stage == "fallback"
    assert decision.routed is False


def test_no_llm_leaves_the_cascade_exactly_as_it_was(registry):
    router = Router(registry, llm=None)
    assert router.route("xyzzy plugh").stage == "fallback"
    assert router.route("what time is it").stage == "pattern"


# ── A generated answer claims only what it is ────────────────────────────────
def test_a_model_answer_carries_model_answered_evidence_and_nothing_stronger(planner):
    stub = StubLlm(LlmChoice(text="Paris is the capital of France.", model="llama3.2:3b"))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        result = planner._dispatch_to_agent("tell me something", "unclear", False, 0.1)
    finally:
        planner.router.llm = original

    assert result["success"] is True
    assert result["generated"] is True
    assert result["evidence"]["kind"] == "model_answered"
    assert result["evidence"]["model"] == "llama3.2:3b"
    assert result["evidence"]["host"] == "local"


def test_a_model_answer_is_visibly_generated(planner):
    """A reader must be able to tell a generated answer from an observed one
    without inspecting the evidence dict."""
    stub = StubLlm(LlmChoice(text="I think so.", model="stub"))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        result = planner._dispatch_to_agent("do you reckon", "chitchat", False, 0.1)
    finally:
        planner.router.llm = original
    assert result["message"].startswith("💭")


def test_model_answered_evidence_refuses_to_claim_more_than_it_can():
    e = ModelAnswered(model="llama3.2:3b")
    assert "generated this text" in e.describe()
    assert e.host == "local"


# ── A guess may answer, but it may not act ───────────────────────────────────
# The measurement behind this section: asked to "shut down chrome for me right
# now", a live 3B selected `open_app_or_website` and MONDAY **launched Chrome**.
# The Tier-2 gate was not violated — nothing irreversible was reached — and that
# was not enough. "Reversible" and "wanted" are different properties.
def _route_via_llm(planner, skill_name, slots=None, command="some vague thing"):
    stub = StubLlm(LlmChoice(skill=skill_name, arguments=slots or {}, model="stub"))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        return planner._dispatch_to_agent(command, "unclear", False, 0.1)
    finally:
        planner.router.llm = original


def test_a_guessed_read_only_skill_runs_immediately(planner):
    """Reading changes nothing, so asking first is friction with no safety."""
    planner.pending_clarification = None
    result = _route_via_llm(planner, "battery_status")
    assert result.get("awaiting_llm_confirmation") is not True
    assert planner.pending_clarification is None


def test_a_guessed_acting_skill_is_proposed_not_performed(planner):
    planner.pending_clarification = None
    result = _route_via_llm(planner, "open_app_or_website", {"target": "chrome"})

    assert result["success"] is False
    assert result["error"] == "AWAITING_LLM_CONFIRMATION"
    assert result["proposed_skill"] == "open_app_or_website"
    assert planner.pending_clarification is not None
    # The reading it arrived at has to be visible, or the user cannot tell it
    # is about to do the opposite of what they asked.
    assert "chrome" in result["message"]


def test_declining_a_proposal_runs_nothing(planner):
    planner.pending_clarification = None
    _route_via_llm(planner, "open_app_or_website", {"target": "chrome"})
    result = planner.process_command("no")["execution_result"]

    assert result.get("cancelled") is True
    assert result.get("executed") is not True
    assert planner.pending_clarification is None


def test_an_unclear_reply_to_a_proposal_re_asks(planner):
    """Same rule as every other gate: never infer consent from ambiguity."""
    planner.pending_clarification = None
    _route_via_llm(planner, "open_app_or_website", {"target": "chrome"})
    result = planner.process_command("hmm maybe")["execution_result"]

    assert result.get("awaiting_llm_confirmation") is True
    assert planner.pending_clarification is not None
    planner.pending_clarification = None


def test_accepting_a_proposal_runs_the_skill_with_its_slots(planner, monkeypatch):
    planner.pending_clarification = None
    launched = []
    monkeypatch.setattr(
        planner.browser_agent, "open_app_or_website",
        lambda target: launched.append(target) or {
            "success": True, "message": f"opened {target}",
            "evidence": {"kind": "system_query", "source": "test"},
        },
    )
    _route_via_llm(planner, "open_app_or_website", {"target": "notepad"})
    result = planner.process_command("yes")["execution_result"]

    assert launched == ["notepad"]
    assert result.get("routed_by") == "llm_confirmed"


def test_a_proposal_is_revalidated_when_it_resumes(planner):
    """The pending state is plain data and a resume is a second entry point.

    A skill the model may not reach must not become reachable by parking its
    name in the clarification and answering yes.
    """
    planner.pending_clarification = {
        "type": "llm_proposal",
        "step": "confirm_llm_skill",
        "skill": "terminate_process",   # Tier 2 — never llm_reachable
        "slots": {"process": "explorer"},
        "original_command": "kill explorer",
    }
    result = planner.process_command("yes")["execution_result"]
    assert result["success"] is False
    assert result["error"] == "SKILL_NOT_RUNNABLE"
    planner.pending_clarification = None


def test_a_pattern_match_is_never_proposed(planner):
    """Patterns are exact. Only a guess is qualified by `read_only`."""
    planner.pending_clarification = None
    result = planner._dispatch_to_agent("open notepad", "browser", False, 0.9)
    assert result.get("awaiting_llm_confirmation") is not True


def test_every_skill_that_acts_is_marked_as_such(registry):
    """A skill added later defaults to needing confirmation, not to acting.

    `read_only` defaults to False so the unsafe direction requires a deliberate
    annotation — the same shape as `classify_action_risk` defaulting to Tier 2.
    """
    assert Skill(name="x", patterns=["do x"], handler=lambda **_: {}).read_only is False
    # And the ones that obviously only read are annotated, or the confirmation
    # prompt would appear in front of "what time is it".
    for name in ("tell_time", "battery_status", "system_health", "answer_question"):
        assert registry.get(name).read_only is True, f"{name} should be read-only"


# ── Availability, and the cost of not having it ──────────────────────────────
def test_the_stage_can_be_switched_off_outright(registry, monkeypatch):
    """`MONDAY_LLM=off` exists so a demo can guarantee the deterministic path."""
    monkeypatch.setenv("MONDAY_LLM", "off")
    stage = LlmStage(registry)
    assert stage.available() is False
    assert "disabled" in stage.unavailable_reason
    assert stage.choose("anything") is None


def test_the_model_listing_is_read_in_both_client_shapes(registry, monkeypatch):
    """`Client.list()` returns a pydantic object in ollama-python 0.6, a dict
    before it.

    Reading it as a dict against 0.6 raises `AttributeError`, which
    `available()` catches as "no server" — so the stage would have reported
    itself permanently unavailable on every machine, with a message blaming the
    server. Silent, total, and indistinguishable from Ollama not being
    installed. Both shapes are asserted because that is what makes the failure
    impossible to reintroduce.
    """
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Obj:
        def __init__(self, name: str) -> None:
            self.model = name

    class _Listing:
        def __init__(self, names: List[str]) -> None:
            self.models = [_Obj(n) for n in names]

    for listing in (_Listing(["llama3.2:3b"]), {"models": [{"model": "llama3.2:3b"}]}):
        class _Client:
            def __init__(self, *a: Any, **kw: Any) -> None:
                pass

            def list(self, _l: Any = listing) -> Any:
                return _l

        monkeypatch.setattr(ollama, "Client", _Client)
        stage = LlmStage(registry, model="llama3.2:3b")
        assert stage.available() is True, f"listing shape not understood: {type(listing)}"
        assert stage.unavailable_reason == ""


def test_a_tool_call_is_read_in_both_response_shapes(registry):
    """Same hazard as the listing: pydantic in 0.6, dicts before it."""
    stage = LlmStage(registry)

    class _Fn:
        name = "set_volume"
        arguments = {"level": 30}

    class _Call:
        function = _Fn()

    class _Msg:
        tool_calls = [_Call()]
        content = ""

    class _Resp:
        message = _Msg()

    as_dict = {"message": {"tool_calls": [
        {"function": {"name": "set_volume", "arguments": {"level": 30}}}
    ]}}

    for response in (_Resp(), as_dict):
        choice = stage._read(response)
        assert choice is not None, f"tool call not read from {type(response)}"
        assert choice.skill == "set_volume"
        assert choice.arguments == {"level": 30}


def test_a_plain_text_reply_is_read_in_both_response_shapes(registry):
    stage = LlmStage(registry)

    class _Msg:
        tool_calls = None
        content = "  Two and a half.  "

    class _Resp:
        message = _Msg()

    for response in (_Resp(), {"message": {"content": "  Two and a half.  "}}):
        choice = stage._read(response)
        assert choice is not None and choice.skill is None
        assert choice.text == "Two and a half."


def test_the_first_call_is_given_longer_than_the_rest(registry, monkeypatch):
    """The cold start loads ~2 GB of weights; the calls after it do not.

    Applying one timeout to both made the *first* command after startup the only
    one that failed, which is the worst shape a defect can have — it reads as
    flakiness rather than as a fixed cost in the wrong place. It is how the live
    tests failed, and only the test that happened to run first.
    """
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")
    timeouts: List[float] = []

    class _Client:
        def __init__(self, *a: Any, timeout: float = 0, **kw: Any) -> None:
            timeouts.append(timeout)

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "llama3.2:3b"}]}

        def chat(self, **kw: Any) -> Dict[str, Any]:
            return {"message": {"content": "hello"}}

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="llama3.2:3b")

    stage.choose("first")
    stage.choose("second")

    # [probe, first call, second call]
    assert timeouts[1] == FIRST_CALL_TIMEOUT
    assert timeouts[2] == CHOOSE_TIMEOUT
    assert FIRST_CALL_TIMEOUT > CHOOSE_TIMEOUT


def test_a_failed_cold_start_does_not_shorten_later_timeouts(registry, monkeypatch):
    """Warmth is proven by a call returning, not by one being attempted."""
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")
    timeouts: List[float] = []

    class _Client:
        def __init__(self, *a: Any, timeout: float = 0, **kw: Any) -> None:
            timeouts.append(timeout)

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "llama3.2:3b"}]}

        def chat(self, **kw: Any) -> Dict[str, Any]:
            raise TimeoutError("cold start took too long")

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="llama3.2:3b")

    assert stage.choose("first") is None
    assert stage.choose("second") is None
    assert timeouts[1] == FIRST_CALL_TIMEOUT
    assert timeouts[2] == FIRST_CALL_TIMEOUT, "a timed-out cold start marked the model warm"


def test_an_empty_reply_routes_nowhere(registry):
    """A model that returns neither a call nor text must not become a success."""
    stage = LlmStage(registry)
    assert stage._read({"message": {"content": "   "}}) is None


def test_a_model_that_is_not_pulled_is_reported_as_such(registry, monkeypatch):
    """A running server with the wrong model is a different problem from no
    server, and the message has to say which."""
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "qwen3:8b"}]}

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="llama3.2:3b")
    assert stage.available() is False
    assert "not pulled" in stage.unavailable_reason
    assert "qwen3:8b" in stage.unavailable_reason


def test_an_absent_server_is_a_reason_not_an_exception(registry, monkeypatch):
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    stage = LlmStage(registry, host="http://127.0.0.1:1")  # nothing listens here
    assert stage.available() is False
    assert stage.unavailable_reason
    assert stage.choose("anything") is None


# ── Against a real model ─────────────────────────────────────────────────────
# Deselected by default (`-m "not llm"` in pytest.ini), because they need an
# Ollama server and a ~2 GB model. Run them deliberately:
#
#     py -3.12 -m pytest -m llm
#
# They assert *containment and shape*, not wording. A 3B model is not
# deterministic enough to assert on a sentence, and a test that pins one would
# fail on the next model version for no useful reason.
@pytest.mark.llm
def test_a_live_model_selects_a_real_skill(registry):
    stage = LlmStage(registry)
    if not stage.available():
        pytest.skip(stage.unavailable_reason)

    choice = stage.choose("could you tell me how much battery is left")
    assert choice is not None
    assert choice.skill in {s.name for s in registry.llm_reachable_skills()}


@pytest.mark.llm
def test_a_live_model_cannot_reach_a_tier2_skill(registry):
    """The containment property, against the real thing.

    Asked directly to do the one gated thing, the model must not be able to
    select it — the skill is not in the schema it was given, and the validator
    refuses the name even if it invents it.
    """
    stage = LlmStage(registry)
    if not stage.available():
        pytest.skip(stage.unavailable_reason)

    for command in ["kill every chrome process right now",
                    "force quit notepad immediately"]:
        choice = stage.choose(command)
        if choice is not None and choice.skill:
            assert choice.skill not in registry.tier2_names(), (
                f"the model reached a Tier-2 skill via {command!r}"
            )
            assert choice.skill != "create_desktop_folder"


@pytest.mark.llm
def test_a_live_model_answers_when_no_skill_fits(registry):
    stage = LlmStage(registry)
    if not stage.available():
        pytest.skip(stage.unavailable_reason)

    choice = stage.choose("what is the difference between a list and a tuple")
    assert choice is not None
    # Either it answers, or it picks a skill — both are legitimate. What it may
    # not do is return something that is neither.
    assert choice.text or choice.skill


def test_availability_is_probed_once_not_per_command(registry, monkeypatch):
    """A socket connection in front of every answer would tax the offline path
    that stage 1 exists to protect, so the probe result is cached."""
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    probes: List[str] = []

    class _CountingClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            probes.append("constructed")

        def list(self) -> Dict[str, Any]:
            raise ConnectionError("nothing listening")

    monkeypatch.setattr(ollama, "Client", _CountingClient)

    stage = LlmStage(registry, host="http://127.0.0.1:1")
    for _ in range(6):
        assert stage.available() is False
    assert len(probes) == 1, f"probed {len(probes)} times; the result must be cached"


# ── One language model in the routing path ───────────────────────────────────
# There were two. Stage 3 is this one: local, last, evidenced, contained. The
# other sat in `process_command` directly below the dispatch — a hosted Gemini
# call that fired when the classifier had fallen back *or* the dispatch had
# failed for any reason short of a refusal, and replaced whatever came back with
# `{"success": True, "cognitive_llm": True}` wrapped around a generated string.
#
# It was inert on the development machine only because no API key was
# configured, which is a fact about the machine and not about the code. That is
# the same lesson the voice work learned when installing `pyttsx3` woke a
# dormant path that started Outlook to answer a contact lookup. These tests are
# the ones that would have failed had a key been present.
def _dispatch_returning(planner, monkeypatch, result):
    """Replaces the dispatch with a known result.

    The right seam: the deleted code ran *after* `_dispatch_to_agent` returned
    and rewrote its verdict, so what matters is what survives the trip back.
    """
    monkeypatch.setattr(planner, "_dispatch_to_agent", lambda *a, **kw: dict(result))


def _unsure_classifier(monkeypatch, intent="unclear", confidence=0.11):
    """Forces component 2.1 to report low confidence, which set `fallback`."""
    monkeypatch.setattr(
        planner_module, "predict_intent", lambda *_a, **_kw: (intent, confidence, True)
    )


def test_the_planner_holds_no_second_language_model(planner):
    """Structural, not a comment: there is no engine here to call by accident."""
    assert not hasattr(planner, "cognitive_engine")


def test_a_failed_dispatch_stays_failed(planner, monkeypatch):
    """A structured failure is evidence. Answering over the top of it is not.

    `WEB_SEARCH_HTTP_202` is the real case: DuckDuckGo rate-limits this machine,
    the agent reports that precisely, and the override turned it into a cheerful
    generated paragraph marked `success: True`.
    """
    _dispatch_returning(planner, monkeypatch, {
        "success": False,
        "error": "WEB_SEARCH_HTTP_202",
        "message": "DuckDuckGo refused the request (HTTP 202).",
    })
    result = planner.process_command("search for something")["execution_result"]

    assert result["success"] is False
    assert result["error"] == "WEB_SEARCH_HTTP_202"
    assert result.get("cognitive_llm") is not True
    assert "🤖" not in result["message"]


def test_an_unsure_classifier_does_not_discard_a_real_result(planner, monkeypatch):
    """The condition was `fallback or <dispatch failed>`, not `and`.

    So a command that matched a pattern and did real work had its result thrown
    away whenever 2.1 happened to be unsure — and 2.1 being unsure is precisely
    when the pattern, not the classifier, was carrying the routing.
    """
    _unsure_classifier(monkeypatch)
    _dispatch_returning(planner, monkeypatch, {
        "success": True,
        "message": "Battery at 74%.",
        "evidence": {"kind": "system_query", "source": "psutil"},
    })
    result = planner.process_command("battery")["execution_result"]

    assert result["message"].startswith("Battery at 74%")
    assert result["evidence"]["source"] == "psutil"
    assert result.get("cognitive_llm") is not True


def test_a_stage_3_proposal_reaches_the_user(planner, monkeypatch):
    """`_propose_llm_skill` returns success=False by design.

    The override read that as a failed dispatch, replaced the question with an
    unrelated answer, and left `pending_clarification` armed — so the user was
    never shown the question their next "yes" would answer.
    """
    planner.pending_clarification = None
    _unsure_classifier(monkeypatch)
    stub = StubLlm(LlmChoice(
        skill="open_app_or_website", arguments={"target": "chrome"}, model="stub"
    ))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        result = planner.process_command("xyzzy the chrome thing")["execution_result"]
    finally:
        planner.router.llm = original

    assert result.get("awaiting_llm_confirmation") is True
    assert "chrome" in result["message"]
    assert planner.pending_clarification is not None
    planner.pending_clarification = None


def test_a_generated_answer_arrives_generated_through_the_whole_pipeline(planner, monkeypatch):
    """`_dispatch_to_agent` labels it; nothing downstream may relabel it."""
    planner.pending_clarification = None
    _unsure_classifier(monkeypatch)
    stub = StubLlm(LlmChoice(text="A tuple cannot be changed.", model="llama3.2:3b"))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        result = planner.process_command("xyzzy tuples")["execution_result"]
    finally:
        planner.router.llm = original

    assert result["generated"] is True
    assert result["evidence"]["kind"] == "model_answered"
    assert result.get("cognitive_llm") is not True


# ── Stored facts, and the line between a fact and a transcript ───────────────
# The deleted path was handed `get_contextual_memories(cmd)`; stage 3 was not.
# Deleting one of two LLM paths must not quietly delete a capability with it, so
# the memories moved across — and stopped at the same containment line
# everything else does.
def _capturing_stage(registry, monkeypatch, seen):
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "llama3.2:3b"}]}

        def chat(self, **kw: Any) -> Dict[str, Any]:
            seen.append(kw["messages"])
            return {"message": {"content": "noted"}}

    monkeypatch.setattr(ollama, "Client", _Client)
    return LlmStage(registry, model="llama3.2:3b")


def test_stored_facts_reach_the_model_as_their_own_system_message(registry, monkeypatch):
    """Their own message, not appended to the prompt: the containment
    instructions and the user's data are never one editable string."""
    seen: List[Any] = []
    stage = _capturing_stage(registry, monkeypatch, seen)
    stage.choose(
        "what is my wifi password",
        memories=[{"key": "wifi password", "value": "hunter2", "topic": "general"}],
    )

    messages = seen[0]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["role"] == "system"
    assert "hunter2" in messages[1]["content"]


def test_facts_are_placed_before_the_conversation(registry, monkeypatch):
    """A stored fact is background; the turns are what is being answered."""
    seen: List[Any] = []
    stage = _capturing_stage(registry, monkeypatch, seen)
    stage.choose(
        "and tell mum too",
        history=[{"role": "user", "content": "message dad"}],
        memories=[{"key": "mum", "value": "9876543210", "topic": "contacts"}],
    )

    assert [m["role"] for m in seen[0]] == ["system", "system", "user", "user"]


def test_a_conversation_transcript_is_not_offered_as_a_remembered_fact():
    """`recall` reads one table and that table holds both kinds of row.

    Handing a transcript to the model as something the user asked to be
    remembered is the error the contact lookup made when a question about an
    email address was answered out of a conversation row.
    """
    assert memory_context([
        {"key": "turn_12", "value": "user: hello", "topic": "conversation_history"},
    ]) == ""


def test_nothing_remembered_adds_nothing_to_the_prompt(registry, monkeypatch):
    assert memory_context(None) == ""
    assert memory_context([]) == ""
    assert memory_context([{"key": "", "value": "", "topic": "general"}]) == ""

    seen: List[Any] = []
    stage = _capturing_stage(registry, monkeypatch, seen)
    stage.choose("what time is it")
    assert [m["role"] for m in seen[0]] == ["system", "user"]


def test_the_planner_hands_the_stage_what_the_memory_agent_found(planner, monkeypatch):
    """The wiring, end to end — the part a unit test of `memory_context` cannot
    see, and the part that would have been cut with the old path."""
    planner.pending_clarification = None
    _unsure_classifier(monkeypatch)
    monkeypatch.setattr(
        planner.memory_agent, "get_contextual_memories",
        lambda *_a, **_kw: [{"key": "wifi password", "value": "hunter2", "topic": "general"}],
    )
    stub = StubLlm(LlmChoice(text="It is hunter2.", model="stub"))
    original = planner.router.llm
    planner.router.llm = stub
    try:
        planner.process_command("xyzzy what did I tell you about the wifi")
    finally:
        planner.router.llm = original

    assert [m["value"] for m in stub.memories] == ["hunter2"]


# ── Which model, when nobody said ────────────────────────────────────────────
# One hard-coded default cannot serve both machines this runs on. The
# development machine puts all 29 layers of an 8B on a 6 GiB RTX 4050; a machine
# with no GPU cannot load one at all. Naming only the 8B would take stage 3 away
# from the second — `available()` would say "not pulled" and go quiet where it
# used to work.
def test_the_best_available_model_is_preferred():
    """"Best" is what the eval says, not what is largest.

    `reports/stage3_selection.py` on 339 commands: the 3B scores 66.1% at
    p50 0.7s, the 8B 64.3% at p50 1.8s. The 8B fits on this machine — Ollama
    puts all 29 layers on the 6 GiB card — and fitting is not helping.
    """
    assert _first_present(PREFERRED_MODELS, ["llama3.2:3b", "llama3.1:8b"]) == "llama3.2:3b"
    assert PREFERRED_MODELS[0] == "llama3.2:3b"


def test_another_model_is_used_when_the_preferred_one_is_absent():
    """The regression this avoids: stage 3 going silent on a machine where it
    worked, because the default moved to a model that machine never pulled.

    Both directions, because the preference order has now moved twice.
    """
    assert _first_present(PREFERRED_MODELS, ["llama3.2:3b"]) == "llama3.2:3b"
    assert _first_present(PREFERRED_MODELS, ["llama3.1:8b"]) == "llama3.1:8b"
    assert _first_present(PREFERRED_MODELS, ["llama3.2:1b"]) == "llama3.2:1b"


def test_a_deliberate_quantisation_still_counts():
    """Someone who pulled `llama3.1:8b-instruct-q4_0` chose that on purpose.
    Matching the whole tag would reject it and fall back to a worse model."""
    assert _first_present(PREFERRED_MODELS, ["llama3.1:8b-instruct-q4_0"]).startswith("llama3.1:8b")


def test_nothing_preferred_means_nothing_chosen():
    assert _first_present(PREFERRED_MODELS, ["mistral:7b"]) == ""
    assert _first_present(PREFERRED_MODELS, []) == ""


def test_an_explicit_model_is_never_second_guessed(registry, monkeypatch):
    """A named model that is absent must report exactly that.

    Quietly running a different one would make "which model answered this?"
    unanswerable, and stage 3's whole contract is that a generated answer says
    where it came from.
    """
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "llama3.2:3b"}]}

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="llama3.1:8b")

    assert stage.available() is False
    assert "not pulled" in stage.unavailable_reason
    assert stage.model == "llama3.1:8b", "an explicit choice was silently replaced"


def test_an_unnamed_model_resolves_against_the_server(registry, monkeypatch):
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "llama3.2:3b"}, {"model": "llama3.1:8b"}]}

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="")

    assert stage.available() is True
    assert stage.model == "llama3.2:3b"


def test_a_server_with_no_preferred_model_says_what_it_wanted(registry, monkeypatch):
    monkeypatch.delenv("MONDAY_LLM", raising=False)
    ollama = pytest.importorskip("ollama")

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def list(self) -> Dict[str, Any]:
            return {"models": [{"model": "mistral:7b"}]}

    monkeypatch.setattr(ollama, "Client", _Client)
    stage = LlmStage(registry, model="")

    assert stage.available() is False
    assert PREFERRED_MODELS[0] in stage.unavailable_reason
    assert "mistral:7b" in stage.unavailable_reason
