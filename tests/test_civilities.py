"""
Stage 1 retries once with the politeness removed.

Measured on the 10,631 real utterances in `data/external/massive_en_us.csv`, the
largest single class of routing miss was not a missing capability. It was
"please", "can you", "could you please" and a trailing "please" wrapped around a
command MONDAY already served. 122 of 134 `audio_volume_up` utterances missed,
and a third of them missed for that reason alone.

The design constraint is the interesting part, and it is what most of this file
tests: **the retry may only add matches, never change one.** It runs solely when
the command as typed matched nothing, so a pattern that matched yesterday
matches today and captures the same slots. That matters because slots carry
email bodies and WhatsApp messages, and a message that lost its "please" on the
way out would be this feature doing harm to a real conversation.
"""

from __future__ import annotations

import pytest

from core.intent_patterns import IntentContainer, strip_civilities
from core.planner import MasterPlanner
from ml.intent_classifier import predict_intent


# ── The stripper itself ──────────────────────────────────────────────────────
@pytest.mark.parametrize("typed,bare", [
    ("please turn up the volume", "turn up the volume"),
    ("can you turn up the volume", "turn up the volume"),
    ("could you please mute", "mute"),
    ("i want you to mute the sound", "mute the sound"),
    ("turn the volume up please", "turn the volume up"),
    ("mute thanks", "mute"),
    ("turn the volume up for me", "turn the volume up"),
    ("please turn the volume up please", "turn the volume up"),
    ("hey monday what time is it", "what time is it"),
    ("monday, mute", "mute"),
])
def test_civilities_come_off_the_edges(typed, bare):
    assert strip_civilities(typed) == bare


@pytest.mark.parametrize("untouched", [
    # "monday" is a day before it is a wake word. Only a greeting or a comma
    # makes it one, or "monday morning meeting" would lose its day.
    "monday morning meeting",
    "remember monday is gym day",
    "schedule standup monday at 9",
    # Politeness in the middle is content, not grammar.
    "send mail to a@b.com body please call me back",
    "remember the wifi password is pleasant123",
])
def test_the_middle_of_a_command_is_never_touched(untouched):
    assert strip_civilities(untouched) == untouched


def test_a_command_is_never_stripped_to_nothing():
    """"please" alone is not a command, and an empty string would match a
    pattern made entirely of optional segments."""
    assert strip_civilities("please") == "please"
    assert strip_civilities("thanks") == "thanks"


@pytest.mark.parametrize("greeting", ["hi monday", "hello monday", "hey monday", "hi to monday", "hello to monday"])
def test_wake_word_greetings_survive_stripping(greeting):
    assert strip_civilities(greeting) == greeting


@pytest.mark.parametrize("typed,bare", [
    ("hi to monday what time is it", "what time is it"),
    ("hello to monday battery", "battery"),
])
def test_wake_word_with_to_is_stripped(typed, bare):
    assert strip_civilities(typed) == bare


# ── The retry, and its one guarantee ─────────────────────────────────────────
def test_the_retry_only_runs_when_the_first_pass_failed():
    """A pattern that matches the command as typed keeps its match and its
    slots. Proved on a pattern where the two passes would disagree."""
    container = IntentContainer()
    container.add_intent("literal", ["say please {word}"])
    container.add_intent("bare", ["say {word}"])

    match = container.calc_intent("say please now")
    # Both could match after stripping; only the first pass ran, so the more
    # specific literal wins and `word` is what the user actually said.
    assert match.intent == "literal"
    assert match.slots["word"] == "now"


def test_the_retry_adds_a_match_that_did_not_exist():
    container = IntentContainer()
    container.add_intent("mute", ["mute"])

    assert container.calc_intent("mute").intent == "mute"
    assert container.calc_intent("can you mute please").intent == "mute"


def test_a_slot_never_loses_its_content_to_the_retry():
    """The failure this guarantee exists to prevent: an email body arrives
    without the word the sender chose to put in it."""
    container = IntentContainer()
    container.add_intent("send", ["send {body} to {who}"])

    match = container.calc_intent("send please call me to bob")
    assert match.slots["body"] == "please call me"
    assert match.slots["who"] == "bob"


def test_an_unmatchable_command_is_still_unmatchable():
    container = IntentContainer()
    container.add_intent("mute", ["mute"])
    assert container.calc_intent("please xyzzy plugh") is None


# ── End to end, on the real skills ───────────────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


@pytest.mark.parametrize("command,skill", [
    ("please turn up the volume", "volume_up"),
    ("can you mute", "mute_volume"),
    ("could you please tell me the time", "tell_time"),
    ("hey monday what time is it", "tell_time"),
    ("please tell me the latest news", "latest_news"),
    ("can you tell me the weather", "weather"),
    ("what time is it please", "tell_time"),
])
def test_a_polite_command_reaches_the_same_skill_as_a_blunt_one(planner, command, skill):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} routes nowhere"
    assert decision.skill.name == skill


def test_politeness_does_not_reach_into_a_message_body(planner):
    """The end-to-end version of the slot guarantee, on the real WhatsApp
    patterns — the best-tested parser in the repository, and one whose output
    goes to another person."""
    decision = _route(planner, "message 9876543210 saying please call me back")
    assert decision.routed
    assert "please call me back" in str(decision.slots)
