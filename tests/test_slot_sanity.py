"""
ROADMAP Phase 9 — a pattern may match and still be wrong.

The failure this file exists to prevent, found by running real phrasings through
the router on 2026-08-18:

    'book me a flight to delhi on tuesday'
        -> schedule_event {'title': 'me a flight to delhi', 'when': 'tuesday'}

`(schedule|add|create|book) {title} (at|on|for) {when}` did what it was told, and
nothing asked whether "me a flight to delhi" is a plausible event title.
`schedule_event` **acts**, so that wrote a junk entry into a real calendar with
no question asked. MONDAY cannot book flights; the honest answer was "I'm not
sure how to do that yet", and the user would have lost one retry instead of
gaining a wrong calendar they may never look at.

Two halves, and the second matters more:

* **The negative set** — commands that must reach nothing. Coverage can always
  be raised by matching more, so a coverage number without this is a number that
  can be gamed. `reports/massive_coverage.md` is the coverage half.
* **The positive control** — commands that must keep working. Every rule in
  `core/slot_sanity.py` can only *reject*, so a rule that fires wrongly silently
  takes a working command away. These are the ones that would notice.
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner
from core.slot_sanity import implausible
from ml.intent_classifier import predict_intent


class _Skill:
    """Stands in for a skill that ACTS.

    Rule 2 reads `read_only`: a clumsy search query is worth keeping, a clumsy
    action is not. `_ReadOnlySkill` below is the other half of that pair.
    """
    name = "test_skill"
    read_only = False


class _ReadOnlySkill:
    name = "test_reader"
    read_only = True


# ── The rules, one at a time ─────────────────────────────────────────────────
@pytest.mark.parametrize("slots,command,fragment", [
    # 1. the verb's object, captured as content
    ({"title": "me a flight to delhi"}, "book me a flight to delhi on tuesday", "verb's object"),
    ({"title": "us a table for four"}, "book us a table for four at 8", "verb's object"),
    # 2. a question split rather than understood
    # Rule 2 fires only for a skill that acts — see `_Skill.read_only` below.
    ({"title": "i meet reveca today"}, "when do i meet reveca today", "question was split"),
    ({"fact": "you spell necessary"}, "how do you spell necessary", "question was split"),
    # 3. a sentence where a filename belongs
    ({"path": "my last email and reply to it"}, "summarise my last email and reply to it", "names no file"),
    # 4. a ticker that is a sentence
    ({"symbol": "the stock market today please"}, "price of the stock market today please", "at most 3"),
    # 5. an article where a person's name belongs. `call me {name}` is a fair
    # pattern and "call me an uber" is a fair sentence; they mean different
    # things by "call", and the skill ACTS — it writes the user's name.
    # Found by the first run of reports/scoreboard.py.
    ({"name": "an uber to the airport"}, "call me an uber to the airport", "not somebody's name"),
    ({"name": "a taxi"}, "call me a taxi", "not somebody's name"),
])
def test_a_broken_parse_is_named_as_broken(slots, command, fragment):
    reason = implausible(_Skill, slots, command)
    assert reason is not None, f"{slots} should have been rejected"
    assert fragment in reason


@pytest.mark.parametrize("slots,command", [
    # A real title, a real time.
    ({"title": "standup", "when": "9"}, "schedule standup at 9"),
    ({"title": "dentist appointment", "when": "tuesday"}, "book dentist appointment on tuesday"),
    # A real filename, with and without a directory.
    ({"path": "report.pdf"}, "summarize report.pdf"),
    ({"path": "C:/docs/notes.txt"}, "summarize C:/docs/notes.txt"),
    ({"path": "notes"}, "summarize notes"),
    # "i" opens a remembered fact legitimately — the rule is guarded on the
    # command opening with a question word, and this one does not.
    ({"fact": "i park in bay 4"}, "remember i park in bay 4"),
    ({"value": "i prefer tea"}, "remember my drink is i prefer tea"),
    # A question whose topic is a noun phrase, which is the normal case.
    ({"topic": "the capital of france"}, "what is the capital of france"),
    ({"topic": "ada lovelace"}, "who is ada lovelace"),
    # Tickers and short company names.
    ({"symbol": "ifci"}, "ifci share price"),
    ({"symbol": "tata motors"}, "tata motors share price"),
    # A single word that happens to be a pronoun is not evidence of anything.
    ({"title": "me"}, "schedule me at 9"),
    # A real name, and a value that legitimately opens with an article — rule 5
    # is scoped to person slots for exactly this reason.
    ({"name": "Sam"}, "call me Sam"),
    ({"name": "Sambhav"}, "my name is Sambhav"),
    ({"key": "my drink", "value": "a coffee"}, "remember my drink is a coffee"),
])
def test_a_good_parse_is_left_alone(slots, command):
    assert implausible(_Skill, slots, command) is None, f"{slots} was rejected wrongly"


def test_a_clumsy_query_survives_for_a_skill_that_only_reads():
    """The measurement that scoped rule 2: every rejection it made over the
    whole corpus went to `answer_question`, and refusing to search for a
    slightly mangled phrase gives the user nothing instead of something
    imperfect."""
    slots = {"topic": "we continue to have daylight savings time"}
    command = "why do we continue to have daylight savings time"
    assert implausible(_ReadOnlySkill, slots, command) is None
    assert implausible(_Skill, slots, command) is not None


def test_a_broken_path_is_rejected_even_for_a_reader():
    """Rules 3 and 4 stay universal: they predict a guaranteed failure rather
    than a worse result. A file that does not exist cannot be summarised."""
    assert implausible(
        _ReadOnlySkill, {"path": "my last email and reply to it"}, "summarise it"
    ) is not None


def test_non_string_slots_are_ignored():
    """`{level:int}` arrives as an int, and none of these rules apply to it."""
    assert implausible(_Skill, {"level": 50}, "set volume to 50") is None


def test_an_impossible_path_does_not_raise():
    """A slot holds whatever the user typed, including strings the OS rejects.

    `_exists()` calls `Path(...).exists()` on it, which raises OSError on Windows
    for characters that cannot appear in a filename. Two words, so rule 3's
    length guard does not fire and the value comes back clean; three words and
    it is rejected for naming no file. Either way it must not raise.
    """
    assert implausible(_Skill, {"path": 'a"b<c>d|e'}, "summarize it") is None
    assert implausible(_Skill, {"path": 'a"b<c>d|e junk file'}, "summarize it") is not None


# ── End to end: the negative set ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None      # stage 1 and 2 only — a model is not a capability
    return p


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


@pytest.mark.parametrize("command", [
    # MONDAY books nothing. Reaching the calendar with a mangled title is worse
    # than reaching nothing, because it acts.
    "book me a flight to delhi on tuesday",
    "book me a table for two tonight",
    # There is no email-summarising path, and `summarize_document` would have
    # gone looking for a file called "my last email and reply to it".
    "summarise my last email and reply to it",
])
def test_a_command_with_no_honest_answer_reaches_nothing(planner, command):
    decision = _route(planner, command)
    assert not decision.routed, (
        f"{command!r} reached {decision.skill.name if decision.skill else '?'} "
        f"— a confident wrong action is worse than an honest refusal"
    )


def test_the_refusal_says_which_pattern_was_not_believed(planner):
    """"Nothing matched" and "something matched and was not believed" are
    different diagnoses, and the second names a pattern worth fixing."""
    decision = _route(planner, "book me a flight to delhi on tuesday")
    assert "parse rejected" in decision.reason
    assert "title=" in decision.reason


# ── End to end: the positive control ─────────────────────────────────────────
@pytest.mark.parametrize("command,skill", [
    ("schedule standup at 9", "schedule_event"),
    ("what is the capital of france", "answer_question"),
    ("who is ada lovelace", "answer_question"),
    ("remember i park in bay 4", "remember_fact"),
    ("ifci share price", "stock_price"),
    ("what time is it", "tell_time"),
    ("latest news", "latest_news"),
    ("set volume to 40", "set_volume"),
    ("turn up the volume", "volume_up"),
])
def test_the_commands_that_must_keep_working_keep_working(planner, command, skill):
    """Every rule can only reject, so over-rejection is the failure mode with no
    other symptom — nothing errors, a command just quietly stops working."""
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} stopped routing"
    assert decision.skill.name == skill
