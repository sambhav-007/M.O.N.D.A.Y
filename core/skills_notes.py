"""
M.O.N.D.A.Y. — tranche 10: what we talked about (ROADMAP Phase 12, second slice).

Two skills over `core/conversation_notes.py`:

* **`recall_conversation`** — "what did we talk about yesterday". Reads the
  turns already in `memories.db`, scoped to the window the user named, and
  quotes what was said.
* **`note_conversation`** — "make a note of this conversation". Condenses a
  stretch of turns into one durable row under its own topic, so a week later it
  is findable without reading the whole log.

Both quote; neither generates. An extracted line was said; a written one is a
claim about what was agreed, produced by something that was not part of the
agreement. `core/conversation_notes.py` carries the rest of that reasoning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from core.contracts import AgentResult, RecordStored, SystemQuery
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
from core.skills import Skill, SkillRegistry

#: How many turns a note or a recall will read. A cap rather than the whole
#: history: this runs in front of a user waiting for an answer.
MAX_TURNS = 200


def _stored_turns(planner: Any, since: Any = None) -> List[Dict[str, str]]:
    """Every conversation turn on record, newest last, within the window."""
    rows = planner.memory_agent.list_memories() if hasattr(planner.memory_agent, "list_memories") else None
    if rows is None:
        # `list_memories` is the tidy path; `recall` with an empty query is the
        # one that exists. Read the table directly rather than inventing an
        # agent method this module would then be the only caller of.
        import sqlite3

        from agents.memory_agent import MEMORIES_DB_PATH

        try:
            with sqlite3.connect(MEMORIES_DB_PATH) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT key, value, topic FROM memories WHERE topic = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (TURN_TOPIC, MAX_TURNS),
                )
                rows = [{"key": k, "value": v, "topic": t} for k, v, t in cursor.fetchall()]
        except Exception:  # noqa: BLE001 — no table yet is "no conversation yet"
            rows = []

    turns: List[Dict[str, str]] = []
    for row in reversed(rows):
        if row.get("topic") != TURN_TOPIC:
            continue
        parsed = parse_turn(str(row.get("value", "")))
        if not parsed:
            continue
        when = turn_time(str(row.get("key", "")))
        if since is not None and when is not None and when < since:
            continue
        parsed["when"] = when.isoformat(timespec="seconds") if when else ""
        turns.append(parsed)
    return turns


def register_note_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers conversation recall and note-taking."""

    def recall_conversation(_command: str = "", **_: Any) -> Dict[str, Any]:
        window, since = window_for(_command)
        turns = _stored_turns(planner, since)

        if not turns:
            return AgentResult.failed(
                f"I have nothing on record from {window}.",
                error="NO_CONVERSATION_FOUND",
                data={"window": window},
            ).as_dict()

        highlights = condense(turns)
        lines = [f"  • {line[:110]}" for line in highlights]
        return AgentResult.ok(
            f"🗒️ {len(turns)} exchanges {window}. You asked about:\n"
            + "\n".join(lines)
            + "\n  Quoted from what was said — not a summary of what it meant.",
            evidence=SystemQuery(
                source="memories.db",
                detail=f"{len(turns)} turns with topic '{TURN_TOPIC}' {window}",
            ),
            data={
                "window": window,
                "turns": len(turns),
                "highlights": highlights,
                "speech": f"{len(turns)} exchanges {window}.",
            },
        ).as_dict()

    registry.register(Skill(
        name="recall_conversation",
        read_only=True,
        description="What we talked about earlier — quotes past exchanges, not stored facts",
        patterns=[
            "[(what|which)] did we (talk|speak) about [{rest}]",
            "[(what|which)] did we discuss [{rest}]",
            "[(what|which)] have we (talked|spoken) about [{rest}]",
            "[(what|which)] did i ask [(you)] [(about)] [{rest}]",
            "[(what|which)] did we decide [{rest}]",
            "[(what|which)] was i (asking|doing) [{rest}]",
            "(remind|tell) me what we (talked|spoke) about [{rest}]",
            "our (conversation|chat) [{rest}]",
            "conversation history",
        ],
        handler=recall_conversation,
        tier=1,
        offline=True,
    ))

    def note_conversation(_command: str = "", **_: Any) -> Dict[str, Any]:
        window, since = window_for(_command)
        turns = _stored_turns(planner, since)

        if not turns:
            return AgentResult.failed(
                f"There is nothing from {window} to make a note of.",
                error="NO_CONVERSATION_FOUND",
                data={"window": window},
            ).as_dict()

        key = note_key()
        text = build_note(turns, window)
        stored = planner.memory_agent.remember(key, text, topic=NOTE_TOPIC)
        if not stored.get("success"):
            # The write is the whole point; reporting a note that was not
            # written is the failure this repository keeps deleting.
            return stored

        return AgentResult.ok(
            f"✓ Noted: {text[:220]}\n"
            f"  Saved as '{key}' — ask 'recall {key}' or search your memories "
            f"for it later.",
            evidence=RecordStored(store="memories.db", key=key),
            data={
                "note_key": key,
                "window": window,
                "turns": len(turns),
                "speech": f"Noted {len(turns)} exchanges.",
            },
        ).as_dict()

    registry.register(Skill(
        name="note_conversation",
        read_only=False,
        description="Save a durable note of what we have been talking about",
        patterns=[
            "(make|take|save|write) [(a|an)] note (of|about) [(this|our)] (conversation|chat|discussion) [{rest}]",
            "note [(this|our)] (conversation|chat|discussion) [{rest}]",
            "(summarise|summarize) [(this|our)] (conversation|chat|discussion) [{rest}]",
            "(summarise|summarize) what we (talked|spoke) about [{rest}]",
            "remember [(this|our)] (conversation|chat|discussion) [{rest}]",
            "save [(this|our)] (conversation|chat) [{rest}]",
        ],
        handler=note_conversation,
        tier=1,
        offline=True,
    ))
