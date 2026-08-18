"""
M.O.N.D.A.Y. — ROADMAP Phase 9. A pattern may match and still be wrong.

Stage 1 is exact and deterministic, and that is not the same as correct:

    'book me a flight to delhi on tuesday'
        -> schedule_event {'title': 'me a flight to delhi', 'when': 'tuesday'}

`(schedule|add|create|book) {title} (at|on|for) {when}` did exactly what it was
told. Nobody asked whether "me a flight to delhi" is a plausible event title —
and `schedule_event` **acts**, so the result was a junk entry written into a real
calendar with no question asked.

That is worse than not matching. An honest "I'm not sure how to do that yet"
costs the user one retry; a confidently wrong action costs them a wrong calendar,
a wrong file, or a message to the wrong person, and they may not notice.

What this module is
-------------------
A plausibility check on the *captured slots*, not on the command. It answers one
question — **does this parse look like what the skill expects?** — and returns
the reason when it does not, so the router can carry it into `routing_reason`
and a defect can be diagnosed without re-running the command.

What happens to a failure
-------------------------
The pattern match is **declined**, and the cascade continues to the classifier
and then to the language model (`core/router.py`). It is not an error and not a
refusal: it means stage 1 has no confident reading, which is precisely what the
later stages are for. On a machine with no model that ends at the honest
refusal, which is the right answer for "book me a flight" — MONDAY cannot book
flights.

Deliberately conservative
-------------------------
Every rule here can only *reject*, so a rule that fires wrongly takes a working
command away. They are written to catch parses that are visibly broken — a
pronoun where a title belongs, a sentence where a filename belongs — and not to
judge whether a plausible-looking value is the one the user meant. Where a rule
was tempting but would have needed to guess, it was left out; `tests/
test_slot_sanity.py` carries the cases that must keep working.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

#: Objects of the verb the pattern was supposed to consume. "book **me** a
#: flight", "remind **us** about the thing" — when one of these opens a slot,
#: the pattern ate the verb and handed back its indirect object.
_LEADING_PRONOUNS = {"me", "us", "him", "her", "them", "myself", "ourselves"}

#: Question words that belong to the question, not to its subject. `how do i get
#: to the airport` captured `{topic}` = "i get to the airport" because the
#: pattern matched "how do" and left the rest.
_ORPHANED_SUBJECTS = {"i", "we", "you", "it", "they", "he", "she"}

#: A filename usually has one of these, or a separator. This is a shape test,
#: not a whitelist — an extension this does not know about still passes the
#: separator or the "does it exist" test below.
_FILE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_PATH_SEPARATOR = re.compile(r"[\\/]")

#: Slot names that name a file. Matched by name because that is how the patterns
#: declare them (`core/intent_patterns.py`), and a slot called `path` in a new
#: skill should inherit the check without anyone remembering to add it.
_PATH_SLOTS = {"path", "file", "filename", "folder", "directory"}

#: A ticker is one token; a company name people type is rarely more than three.
#: "tell me the price of the stock market today" is a topic, not a company.
_MAX_SYMBOL_WORDS = 3

#: Rule 2 only applies to commands that opened as a question, because "i"
#: legitimately opens a remembered fact ("remember i park in bay 4").
_QUESTION_OPENERS = {"how", "what", "why", "when", "where", "which", "who"}


def _words(value: str) -> list:
    return [w for w in re.split(r"\s+", value.strip()) if w]


def implausible(
    skill: Any,
    slots: Dict[str, Any],
    command: str = "",
) -> Optional[str]:
    """Why this parse should not be trusted, or None if it looks fine.

    `skill` is the matched `Skill` — rule 2 reads its `read_only` flag, because
    a clumsy search is worth keeping and a clumsy action is not. `command` is the
    original text, which two of the rules need because the same slot value is
    fine or broken depending on what preceded it.
    """
    for name, raw in (slots or {}).items():
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        words = _words(value)
        lowered = [w.lower().strip(".,!?'\"") for w in words]

        # ── 1. the verb's object, sitting in a content slot ──────────────────
        # Only when something follows it: a slot that is exactly "me" is a
        # different problem, and one this rule cannot tell from a real value.
        if len(words) > 1 and lowered[0] in _LEADING_PRONOUNS:
            return (
                f"{name}={value!r} starts with '{lowered[0]}', so the pattern "
                f"captured the verb's object rather than the {name}"
            )

        # ── 2. a question's subject, orphaned into a topic ───────────────────
        # `how do i get to the airport` -> topic='i get to the airport'. Guarded
        # twice over:
        #
        # * on the command opening with a question word, because "i"
        #   legitimately opens a remembered fact ("remember i park in bay 4");
        # * on the skill *acting*, because measured over the whole corpus every
        #   rejection this rule made went to `answer_question`, which searches.
        #   A clumsy query still answers the question, and refusing it gives the
        #   user nothing instead of something imperfect. This phase is about
        #   preventing a wrong action, and a search is not an action.
        opener = (command.strip().lower().split() or [""])[0]
        if (
            len(words) > 1
            and lowered[0] in _ORPHANED_SUBJECTS
            and opener in _QUESTION_OPENERS
            and not getattr(skill, "read_only", False)
        ):
            return (
                f"{name}={value!r} begins with '{lowered[0]}' after a question "
                f"word, so the question was split rather than understood"
            )

        # ── 3. a sentence where a filename belongs ──────────────────────────
        if name.lower() in _PATH_SLOTS:
            looks_like_a_file = (
                _FILE_EXTENSION.search(value)
                or _PATH_SEPARATOR.search(value)
                or _exists(value)
            )
            if not looks_like_a_file and len(words) >= 3:
                return (
                    f"{name}={value!r} names no file — no extension, no path, "
                    f"and nothing by that name exists"
                )

        # ── 4. a ticker that is a sentence ──────────────────────────────────
        if name.lower() == "symbol" and len(words) > _MAX_SYMBOL_WORDS:
            return (
                f"symbol={value!r} is {len(words)} words; a company or ticker "
                f"is at most {_MAX_SYMBOL_WORDS}"
            )

    return None


def _exists(value: str) -> bool:
    """Whether this names something on disk. Never raises — a slot can hold
    anything a user typed, including strings the OS rejects outright."""
    try:
        return Path(value).expanduser().exists()
    except (OSError, ValueError):
        return False
