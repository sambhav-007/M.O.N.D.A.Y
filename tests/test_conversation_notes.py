"""
ROADMAP Phase 12, second slice — conversation notes.

Every turn was already going into `memories.db` as one row per exchange,
truncated to 200 characters a side. That is a transcript, not a memory: after a
week it is hundreds of rows of "User: what time is it | Assistant: ✓ Current
time is 11:52 AM", and "what did we decide about the report" searches all of
them equally. It is also why `core/llm.py` excludes that topic from what stage 3
is shown.

The thing being protected here is the line between **quoting and generating**.
`condense` selects sentences the conversation actually contained; it never
writes new prose about what was decided. A generated summary is a claim about an
agreement, produced by something that was not party to it, and this repository
has spent every commit removing claims of that shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from core.conversation_notes import (
    NOTE_TOPIC,
    TURN_TOPIC,
    build_note,
    condense,
    note_key,
    parse_turn,
    turn_time,
    window_for,
)
from core.planner import MasterPlanner
from ml.intent_classifier import predict_intent


# ── Reading what was stored ──────────────────────────────────────────────────
def test_a_stored_turn_is_read_back_in_its_parts():
    """The format is written by `auto_store_conversation_turn`. Parsing it here
    rather than re-deriving it means a change to that format fails loudly."""
    parsed = parse_turn(
        "Agent: MasterPlanner | User: what time is it | Assistant: it is 11:52"
    )
    assert parsed == {
        "agent": "MasterPlanner",
        "user": "what time is it",
        "assistant": "it is 11:52",
    }


@pytest.mark.parametrize("value", [
    "", "not a turn at all", "User: missing the agent prefix",
])
def test_anything_that_is_not_a_turn_is_skipped(value):
    assert parse_turn(value) is None


def test_a_turn_key_carries_its_time():
    assert turn_time("turn_20260818_143000") == datetime(2026, 8, 18, 14, 30, 0)
    assert turn_time("note_20260818_143000") is None
    assert turn_time("nonsense") is None


# ── The window a person names ────────────────────────────────────────────────
@pytest.mark.parametrize("text,phrase", [
    ("what did we talk about today", "today"),
    ("what did we discuss yesterday", "yesterday"),
    ("what did we decide this week", "this week"),
    ("what did we decide last week", "last week"),
    ("what have we talked about ever", "ever"),
    ("what did we discuss", "recently"),
])
def test_the_named_window_is_understood(text, phrase):
    named, _ = window_for(text, now=datetime(2026, 8, 18, 12, 0))
    assert named == phrase


def test_ever_has_no_cutoff():
    _, since = window_for("everything we have ever discussed",
                          now=datetime(2026, 8, 18, 12, 0))
    assert since is None


def test_a_window_cutoff_is_in_the_past():
    _, since = window_for("what did we discuss yesterday",
                          now=datetime(2026, 8, 18, 12, 0))
    assert since < datetime(2026, 8, 18, 12, 0)


# ── Condensing quotes, it does not write ─────────────────────────────────────
def _turns(*lines: str) -> List[Dict[str, str]]:
    return [{"user": line, "assistant": "ok"} for line in lines]


def test_a_short_conversation_is_kept_whole():
    turns = _turns("book the venue", "check the budget")
    assert condense(turns) == ["book the venue", "check the budget"]


def test_every_line_kept_was_actually_said():
    """The property that matters. An extracted line is quotable; a written one
    is a claim about what was agreed, by something that was not there."""
    said = [
        "we should move the deadline to november",
        "the budget review is the week before",
        "marketing wants screenshots by the twentieth",
        "anna owns the migration",
        "ben owns the changelog",
        "the release candidate is cut on the twenty fifth",
    ]
    kept = condense(_turns(*said), limit=3)

    assert len(kept) == 3
    for line in kept:
        assert line in said, f"{line!r} was never said"


def test_the_order_of_the_conversation_is_preserved():
    said = [f"point number {n} about the project plan" for n in range(8)]
    kept = condense(_turns(*said), limit=4)
    assert kept == sorted(kept, key=said.index)


def test_an_empty_conversation_condenses_to_nothing():
    assert condense([]) == []


def test_a_note_says_how_much_it_covers():
    text = build_note(_turns("book the venue", "check the budget"), "today")
    assert "[today]" in text
    assert "2 exchanges" in text


def test_note_keys_are_distinct_from_turn_keys():
    """They share a table; `_stored_turns` must never read a note as a turn."""
    assert note_key(datetime(2026, 8, 18, 14, 30)).startswith("note_")
    assert turn_time(note_key(datetime(2026, 8, 18, 14, 30))) is None


# ── End to end ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


def _run(planner, command) -> Dict[str, Any]:
    return planner.process_command(command)["execution_result"]


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


@pytest.mark.parametrize("command,skill", [
    ("what did we talk about today", "recall_conversation"),
    ("what did we discuss", "recall_conversation"),
    ("what did we decide last week", "recall_conversation"),
    ("what did i ask you about yesterday", "recall_conversation"),
    ("make a note of this conversation", "note_conversation"),
    ("summarise our conversation", "note_conversation"),
    ("note this chat", "note_conversation"),
])
def test_conversation_commands_reach_their_skills(planner, command, skill):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} routes nowhere"
    assert decision.skill.name == skill


def test_the_time_phrase_is_captured_not_dropped(planner):
    """`[rest]` in this DSL is an optional *literal*, so the first version of
    these patterns matched the word "rest" and every command carrying a time
    phrase fell through. `[{rest}]` is the optional slot."""
    assert _route(planner, "what did we talk about today").slots == {"rest": "today"}
    assert _route(planner, "what did we decide last week").slots == {"rest": "last week"}


def test_recalling_quotes_and_says_it_is_quoting(planner):
    _run(planner, "what time is it")
    result = _run(planner, "what did we discuss")

    assert result["success"] is True
    assert result["evidence"]["kind"] == "system_query"
    assert "not a summary of what it meant" in result["message"]


def test_a_note_is_written_and_named(planner):
    _run(planner, "what time is it")
    result = _run(planner, "make a note of this conversation")

    assert result["success"] is True
    assert result["evidence"]["kind"] == "record_stored"
    assert result["note_key"].startswith("note_")

    # And it is findable afterwards, which is the entire point of a durable note.
    found = planner.memory_agent.recall(result["note_key"])
    assert found["matches"], "the note was reported saved and cannot be recalled"
    assert found["matches"][0]["topic"] == NOTE_TOPIC


def test_a_window_with_nothing_in_it_says_so(planner, monkeypatch):
    """Not an empty success. "I have nothing from then" is the honest answer."""
    import core.skills_notes as notes

    monkeypatch.setattr(notes, "_stored_turns", lambda planner, since=None: [])
    result = _run(planner, "what did we talk about last week")

    assert result["success"] is False
    assert result["error"] == "NO_CONVERSATION_FOUND"


def test_a_failed_write_is_not_reported_as_a_note(planner, monkeypatch):
    """The write is the whole point of the skill."""
    monkeypatch.setattr(
        planner.memory_agent, "remember",
        lambda key, value, topic="general": {"success": False, "error": "DISK_FULL",
                                             "message": "could not write"},
    )
    _run(planner, "what time is it")
    result = _run(planner, "make a note of this conversation")

    assert result["success"] is False
    assert result.get("note_key") is None


def test_notes_are_not_read_back_as_turns(planner):
    """Notes and turns share one table. A note read as a turn would be
    condensed into the next note, which compounds into nonsense."""
    import core.skills_notes as notes

    _run(planner, "what time is it")
    _run(planner, "make a note of this conversation")

    for turn in notes._stored_turns(planner):
        assert not str(turn.get("user", "")).startswith("[")
