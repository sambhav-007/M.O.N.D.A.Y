"""
Phase 3 — the three-stage router.

The behaviour under test is *which* handler a command reaches and *why*, which
is the thing the old substring chain made impossible to check: routing was a
side effect of the order 350 lines of `if "x" in cmd_lower` happened to be
written in, and `intent` — the output of component 2.1 — was not consulted until
line ~1811.
"""

from __future__ import annotations

import pytest

from core.contracts import AgentResult, SystemQuery
from core.router import MIN_INTENT_CONFIDENCE, Router
from core.skills import Skill, SkillRegistry


def _ok(name):
    def handler(**slots):
        return AgentResult.ok(
            f"ran {name}",
            evidence=SystemQuery(source="test"),
            data={"slots": slots},
        ).as_dict()

    return handler


@pytest.fixture
def router():
    reg = SkillRegistry()
    reg.register(Skill(
        name="tell_time", patterns=["what time is it", "time"],
        handler=_ok("tell_time"), intents=[], tier=1,
    ))
    reg.register(Skill(
        name="set_volume", patterns=["set volume to {level:int}"],
        handler=_ok("set_volume"), intents=[], tier=1,
    ))
    # `runs_without_slots` is mandatory alongside `intents`: stage 2 routes on a
    # classifier family and passes no slots, so anything reachable that way must
    # do something useful with none.
    reg.register(Skill(
        name="summarize", patterns=["summarize {path}"],
        handler=_ok("summarize"), intents=["document_intel"], tier=1,
        runs_without_slots=True,
    ))
    reg.register(Skill(
        name="remember", patterns=["remember {fact}"],
        handler=_ok("remember"), intents=["memory_query"], tier=1,
        runs_without_slots=True,
    ))
    return Router(reg)


# ── Stage 1: patterns ────────────────────────────────────────────────────────
def test_pattern_match_routes_without_the_classifier(router):
    """
    Stage 1 takes no intent and no confidence. The demo-critical commands must
    resolve with no model and no network in the path.
    """
    d = router.route("what time is it")
    assert d.stage == "pattern"
    assert d.skill.name == "tell_time"
    assert d.confidence == 0.0


def test_pattern_captures_typed_slots(router):
    d = router.route("set volume to 40")
    assert d.slots == {"level": 40}


def test_pattern_beats_a_confident_contradicting_classifier(router):
    """
    A pattern describes the whole command; a classifier describes a family.
    When the two disagree the exact reading wins, or `remember X` could be
    dispatched as a document command because a model felt strongly about it.
    """
    d = router.route("remember the wifi password is hunter2",
                     intent="document_intel", confidence=0.99)
    assert d.stage == "pattern"
    assert d.skill.name == "remember"


# ── Stage 2: the classifier ──────────────────────────────────────────────────
def test_classifier_routes_when_no_pattern_matches(router):
    """This is component 2.1 doing production work rather than reporting an F1."""
    d = router.route("give me the gist of that report", intent="document_intel", confidence=0.82)
    assert d.stage == "classifier"
    assert d.skill.name == "summarize"
    assert "document_intel" in d.reason


def test_low_confidence_does_not_reach_a_handler(router):
    """
    The concrete regression: "search current AI news" classified as
    `desktop_automation` at 0.33 and was dispatched to CoderAgent, which wrote a
    Python script and executed it in a subprocess. A guess that weak must not
    reach code execution.
    """
    d = router.route("something entirely unlike a document",
                     intent="document_intel", confidence=0.33)
    assert d.stage == "fallback"
    assert d.skill is None
    assert "below the" in d.reason


@pytest.mark.parametrize("command", [
    "delete all my photos",
    "please delete all my photos",
    "I want you to erase all my photos",
])
def test_unmatched_destructive_request_cannot_use_classifier_or_llm(router, command):
    class _MustNotRun:
        def choose(self, *args, **kwargs):
            raise AssertionError("model must not receive an unmatched destructive request")

    guarded = Router(router.registry, llm=_MustNotRun())
    d = guarded.route(command, intent="memory_query", confidence=0.99)
    assert d.stage == "fallback"
    assert d.skill is None
    assert "destructive request" in d.reason


def test_the_confidence_floor_is_where_it_says_it_is(router):
    just_under = router.route("vague", intent="document_intel", confidence=MIN_INTENT_CONFIDENCE - 0.01)
    just_over = router.route("vague", intent="document_intel", confidence=MIN_INTENT_CONFIDENCE)
    assert just_under.stage == "fallback"
    assert just_over.stage == "classifier"


def test_an_ambiguous_intent_is_not_a_decision():
    """
    Two skills claiming one intent class means the patterns need sharpening. The
    old chain resolved this by running whichever branch was written first — which
    is how `"gmail"` matching inside a Gmail address shadowed the branch that
    could actually parse an email command.
    """
    reg = SkillRegistry()
    reg.register(Skill(name="a", patterns=["aaa"], handler=_ok("a"),
                       intents=["communication"], runs_without_slots=True))
    reg.register(Skill(name="b", patterns=["bbb"], handler=_ok("b"),
                       intents=["communication"], runs_without_slots=True))
    d = Router(reg).route("unmatched text", intent="communication", confidence=0.95)

    assert d.stage == "fallback"
    assert "ambiguous" in d.reason


# ── Stage 3: fallback ────────────────────────────────────────────────────────
def test_unknown_commands_fall_through_untouched(router):
    d = router.route("what is the capital of france")
    assert d.stage == "fallback"
    assert d.skill is None


def test_routing_never_executes_anything(router):
    """
    `route` chooses; the caller runs. Keeping them apart is what allows routing
    accuracy to be measured over a whole corpus without invoking a handler.
    """
    d = router.route("set volume to 90")
    assert d.routed
    assert d.slots == {"level": 90}  # decided, not performed


# ── The published routing figure ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "command,expected",
    __import__("reports.routing_evidence", fromlist=["ROUTING_SET"]).ROUTING_SET,
)
def test_published_routing_accuracy_holds(command, expected, real_router):
    """
    The routing set behind `reports/routing_evidence.md`, asserted per command so
    a regression names the command it broke rather than moving a number.

    The negatives are the half that matters. Each was mis-served by the substring
    chain: "how much do you charge" hit the battery branch via `"charge" in
    cmd_lower`; "what did i say about the method" hit the crypto branch, because
    `"eth" in cmd_lower` matches m-**eth**-od.
    """
    decision = real_router.route(command)
    actual = decision.skill.name if decision.skill else "(fallback)"
    assert actual == expected, f"{command!r} routed to {actual}, expected {expected}"


@pytest.fixture(scope="module")
def real_router():
    """The actual built-in registry, not the fixtures above.

    **Stage 3 is switched off here, deliberately.** The published figure is a
    claim about the *deterministic* stages: which handler a command reaches by
    pattern or by classifier. Leaving the language model in would make the
    number depend on whether an Ollama server happened to be running on the
    machine that produced it — so the same command could route two ways in two
    runs, and the negatives (commands that must **not** be captured) would stop
    meaning anything, because a model will happily find a plausible skill for
    "determination is important".

    What stage 3 adds is measured separately, and honestly, in
    `tests/test_llm_stage.py`.
    """
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    planner.router.llm = None
    return planner.router


# ── Stage 2 may only reach skills that work without slots ────────────────────
def test_intent_routing_requires_runs_without_slots():
    """
    Stage 2 passes no slots. A skill that needs a key, a path or a target and is
    still reachable by intent gets called with nothing — which is how
    "what is on my desktop", classified `memory_query` at 0.52, was routed into
    the memory *writer* and answered "What should I remember?". A question
    reaching a write path is the failure this router exists to prevent.
    """
    with pytest.raises(ValueError, match="runs_without_slots"):
        Skill(name="needs_slots", patterns=["remember {fact}"],
              handler=_ok("x"), intents=["memory_query"])


def test_tier2_skills_are_never_reachable_from_the_classifier():
    """An irreversible action needs the exactness of a pattern, not a family guess."""
    with pytest.raises(ValueError, match="must not be reachable from the classifier"):
        Skill(name="danger", patterns=["kill {p}"], handler=_ok("x"),
              intents=["desktop_automation"], tier=2, runs_without_slots=True)


# ── Registry invariants ──────────────────────────────────────────────────────
def test_a_skill_needs_some_way_to_be_reached():
    with pytest.raises(ValueError, match="unreachable"):
        Skill(name="orphan", patterns=[], handler=_ok("x"), intents=[])


def test_tiers_are_restricted_to_the_two_that_exist():
    with pytest.raises(ValueError, match="tier must be 1 or 2"):
        Skill(name="x", patterns=["x"], handler=_ok("x"), tier=3)


def test_duplicate_skill_names_are_refused():
    reg = SkillRegistry()
    reg.register(Skill(name="dup", patterns=["a"], handler=_ok("a")))
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(Skill(name="dup", patterns=["b"], handler=_ok("b")))
