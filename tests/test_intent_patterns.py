"""
Stage 1 of the router — deterministic pattern matching with typed slots.

These are the commands the demo depends on. They must resolve identically every
time, with no model and no network involved.
"""

from __future__ import annotations

import pytest

from core.intent_patterns import IntentContainer, expand_pattern, specificity


# ── Pattern expansion ────────────────────────────────────────────────────────
def test_alternation_expands_to_each_option():
    assert set(expand_pattern("send (mail|email) to {r}")) == {
        "send mail to {r}",
        "send email to {r}",
    }


def test_optional_expands_to_present_and_absent():
    assert set(expand_pattern("[please] kill {p}")) == {"please kill {p}", "kill {p}"}


def test_dropping_an_optional_does_not_leave_a_double_space():
    for pattern in expand_pattern("turn [the] volume up"):
        assert "  " not in pattern


def test_combinations_multiply():
    # 2 alternatives × 2 optional states
    assert len(expand_pattern("[hey] (monday|assistant) status")) == 4


def test_slots_are_never_treated_as_syntax():
    """Slots use braces precisely so they cannot collide with () or []."""
    assert expand_pattern("set volume to {level:int}") == ["set volume to {level:int}"]


def test_specificity_counts_literal_text_only():
    assert specificity("send mail to {r}") > specificity("{a} {b}")


# ── Matching ─────────────────────────────────────────────────────────────────
@pytest.fixture
def container():
    c = IntentContainer()
    c.add_intent("send_email", [
        "send (mail|email) to {recipient} subject {subject} body {body}",
        "send (mail|email) to {recipient}",
    ])
    c.add_intent("send_whatsapp", ["message {target} saying {text}"])
    c.add_intent("kill_process", ["kill {process}", "terminate {process}"])
    c.add_intent("set_volume", ["set volume to {level:int}"])
    c.add_intent("battery", ["battery", "battery status", "[what is my] battery level"])
    return c


def test_slots_are_captured(container):
    m = container.calc_intent("kill notepad")
    assert m.intent == "kill_process"
    assert m.slots == {"process": "notepad"}


def test_typed_slots_are_converted(container):
    m = container.calc_intent("set volume to 40")
    assert m.slots["level"] == 40
    assert isinstance(m.slots["level"], int)


def test_the_most_specific_pattern_wins(container):
    """
    Both email patterns match the long form. The one that reads subject and body
    has to win, or a full command silently loses two thirds of itself — which is
    how a real email once went out with no subject and no body.
    """
    m = container.calc_intent('send mail to a@b.com subject "Greetings" body "hello"')
    assert m.intent == "send_email"
    assert m.slots["recipient"] == "a@b.com"
    assert m.slots["subject"] == "Greetings"   # quotes stripped
    assert m.slots["body"] == "hello"


def test_matching_ignores_case_but_captures_do_not(container):
    """
    Matching must be case-insensitive; captured values must keep the case the
    user typed. Lowercasing the whole command before matching does both, and the
    second one is wrong — it would send an email whose subject reads "greetings"
    when the user wrote "Greetings", and flatten every proper noun and file path
    that passes through a slot.
    """
    assert container.calc_intent("KILL Notepad").slots["process"] == "Notepad"

    m = container.calc_intent('SEND MAIL TO a@b.com subject "Quarterly Review" body "Hi Priya"')
    assert m.slots["subject"] == "Quarterly Review"
    assert m.slots["body"] == "Hi Priya"


def test_trailing_punctuation_is_ignored(container):
    assert container.calc_intent("battery?").intent == "battery"


def test_unrelated_text_matches_nothing(container):
    """
    All-or-nothing matching is the point. Substring routing is what sent
    "what did I say about the method" to a crypto price lookup, because "eth"
    appears inside "method".
    """
    for text in [
        "what is the capital of france",
        "help me summarize x.pdf",
        "tell me about the method we discussed",
        "",
        "   ",
    ]:
        assert container.calc_intent(text) is None, text


def test_partial_commands_do_not_match(container):
    """A pattern describes a whole command or does not apply."""
    assert container.calc_intent("kill") is None
    assert container.calc_intent("send mail") is None


def test_substring_of_a_keyword_does_not_trigger(container):
    """'terminate' is an intent verb; 'determination' must not be."""
    assert container.calc_intent("determination is important") is None


# ── Performance, because this runs on every command ──────────────────────────
def test_matching_is_fast_enough_to_run_on_every_command(container):
    """
    The reason this is not the padacioso package: its calc_intent dispatches
    through a ProcessPoolExecutor, measured at ~200ms per command here. Anything
    on the hot path of every user input needs to be far below that.
    """
    import time

    start = time.perf_counter()
    for _ in range(200):
        container.calc_intent("send mail to a@b.com subject x body y")
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"200 matches took {elapsed:.2f}s — too slow for the hot path"
