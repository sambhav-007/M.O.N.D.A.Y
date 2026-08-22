"""
M.O.N.D.A.Y. — ROADMAP Phase 12, second slice. Conversation notes.

The gap this closes
-------------------
Every turn is already written to `memories.db` with topic
`conversation_history`, one row per exchange, truncated to 200 characters a
side. That is a transcript, not a memory: after a week it is hundreds of rows of
"User: what time is it | Assistant: ✓ Current time is 11:52 AM", and asking
"what did we decide about the report" searches all of them equally.

It is also why `core/llm.py` excludes `conversation_history` from what stage 3
is shown — a transcript handed to a model as though it were a remembered fact is
the error the contacts lookup made before it got its own table.

A **note** is the durable half: a condensed record of what a stretch of
conversation was about, written once, stored under its own topic, and worth
retrieving a week later.

Extractive, not generated
-------------------------
The condensing is TF-IDF sentence scoring — the same approach
`DocumentAgent.summarize_document` uses — and it selects sentences the
conversation actually contained. It does **not** write new prose about what was
decided.

That is a deliberate limit rather than a stopgap. A generated summary of a
conversation is a claim about what was agreed, produced by a model that was not
part of the agreement, and this repository has spent every commit removing
claims of that shape. An extracted line is quotable: it was said. When a hosted
or local model is configured, the honest upgrade is to mark the result as
generated — not to quietly start inventing.

What it will not do
-------------------
Nothing here fires on its own. An assistant that silently distils your
conversations into stored notes is doing something you did not ask for with
words you did not know were being kept; the transcript rows are already a lot.
Notes are written when asked for, and the confirmation says where they went.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

#: Topic for the durable notes, distinct from `conversation_history` so recall,
#: stage 3's memory context, and this module can each treat them differently.
NOTE_TOPIC = "conversation_note"

#: Where the turns live.
TURN_TOPIC = "conversation_history"

#: How many sentences a note keeps. Long enough to hold a decision and its
#: reason; short enough that reading five notes is faster than reading the log.
NOTE_SENTENCES = 4

#: `auto_store_conversation_turn` writes rows shaped
#: "Agent: X | User: … | Assistant: …" — parsed rather than re-derived, so the
#: two stay in step by failing loudly here if that format ever changes.
_TURN = re.compile(
    r"^Agent:\s*(?P<agent>[^|]*)\|\s*User:\s*(?P<user>.*?)\s*\|\s*Assistant:\s*(?P<assistant>.*)$",
    re.DOTALL,
)

#: Keys are `turn_YYYYmmdd_HHMMSS`.
_TURN_KEY = re.compile(r"^turn_(?P<stamp>\d{8}_\d{6})$")

#: Windows a person names out loud, in the order they are tried.
_WINDOWS: List[Tuple[str, Optional[timedelta]]] = [
    ("today", timedelta(days=1)),
    ("yesterday", timedelta(days=2)),
    ("this week", timedelta(days=7)),
    ("last week", timedelta(days=14)),
    ("this month", timedelta(days=31)),
    ("ever", None),
]


def parse_turn(value: str) -> Optional[Dict[str, str]]:
    """Splits a stored turn back into its parts, or None if it is not one."""
    match = _TURN.match((value or "").strip())
    if not match:
        return None
    return {
        "agent": match.group("agent").strip(),
        "user": match.group("user").strip(),
        "assistant": match.group("assistant").strip(),
    }


def turn_time(key: str) -> Optional[datetime]:
    """The moment a turn row was written, from its key."""
    match = _TURN_KEY.match((key or "").strip())
    if not match:
        return None
    try:
        return datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def window_for(text: str, now: Optional[datetime] = None) -> Tuple[str, Optional[datetime]]:
    """"what did we discuss last week" → the phrase and the cutoff it names."""
    lowered = (text or "").lower()
    now = now or datetime.now()
    for phrase, span in _WINDOWS:
        if phrase in lowered:
            return phrase, (now - span if span else None)
    return "recently", now - timedelta(days=7)


def condense(turns: List[Dict[str, str]], limit: int = NOTE_SENTENCES) -> List[str]:
    """The most representative lines of a conversation, in the order said.

    TF-IDF against the conversation's own vocabulary, which is what
    `DocumentAgent.summarize_document` does to a document — a line sharing many
    distinctive words with the rest of the exchange is what the exchange was
    about.

    Falls back to the first `limit` lines when scoring is not possible (one
    turn, or a vectoriser failure), because an ordered excerpt is still a true
    excerpt. What it never does is invent a line.
    """
    lines: List[str] = []
    for turn in turns:
        user = turn.get("user", "").strip()
        if user:
            lines.append(user)

    if len(lines) <= limit:
        return lines

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(lines)
        scores = matrix.sum(axis=1).A1
        chosen = sorted(scores.argsort()[::-1][:limit])
        return [lines[index] for index in chosen]
    except Exception:  # noqa: BLE001 — an excerpt beats no note
        return lines[:limit]


def note_key(now: Optional[datetime] = None) -> str:
    return f"note_{(now or datetime.now()):%Y%m%d_%H%M%S}"


def build_note(turns: List[Dict[str, str]], window: str) -> str:
    """The stored text of a note. Plain, quotable, and clearly an extract."""
    highlights = condense(turns)
    body = "; ".join(highlights)
    return f"[{window}] {len(turns)} exchanges. Topics raised: {body}"
