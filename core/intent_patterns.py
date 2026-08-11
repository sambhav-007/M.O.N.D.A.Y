"""
M.O.N.D.A.Y. — deterministic intent patterns with typed slots.

Stage 1 of the router (see `core/router.py`). Declarative patterns replace the
hand-rolled parsing that grew up inside `core/planner.py` —
`_parse_email_command`, `_parse_whatsapp_command`, `_clean_wa_target`,
`_WA_NAME_VERB_RE` and the several hundred lines of `if "volume" in cmd_lower`
that decided routing before the intent classifier was ever consulted.

    container = IntentContainer()
    container.add_intent("send_email", [
        "send (mail|email) to {recipient} subject {subject} body {body}",
        "send (mail|email) to {recipient}",
    ])
    container.calc_intent('send mail to a@b.com subject "Hi" body "Hello"')
    # Match(intent='send_email', slots={'recipient': 'a@b.com', ...}, specificity=21)

Syntax
------
``{name}``         capture a slot
``{name:int}``     typed capture (simplematch's types: int, float, word, ...)
``(one|two)``      alternation
``[optional]``     optional segment

On the choice of engine
-----------------------
This follows the design of `padacioso <https://github.com/OpenVoiceOS/padacioso>`_
(Apache-2.0), the rule-based intent parser from OpenVoiceOS, and uses the same
underlying matcher, ``simplematch``.

It does not use the padacioso package itself, for two measured reasons:

1. ``padacioso.IntentContainer.calc_intent`` dispatches every match through a
   ``ProcessPoolExecutor``. Measured here: **~200 ms per command**, against
   **0.01 ms** for a direct ``simplematch`` call — the pool is re-created per
   call and each Windows spawn re-imports the parent module.
2. That pool makes it unusable in this process. Windows uses spawn rather than
   fork, so it requires an ``if __name__ == "__main__"`` guard in the entry
   module — which the planner cannot guarantee, since it is imported by uvicorn,
   by pytest and by ``cli.py``. Without the guard it raises outright, which is
   how this was found.

Alternation and optional syntax are padacioso's contribution on top of
simplematch, which escapes both as literals. `expand_pattern` reimplements that
expansion; it is the only part worth borrowing, and it is ~40 lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import simplematch

# Innermost group only, so nesting resolves from the inside out.
_ALTERNATION = re.compile(r"\(([^()]*)\)")
_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")
_WHITESPACE = re.compile(r"\s+")
_SLOT = re.compile(r"\{[^{}]*\}")


def expand_pattern(pattern: str) -> List[str]:
    """Expands ``(a|b)`` and ``[optional]`` into concrete simplematch patterns.

    ``"send [me] (mail|email)"`` becomes four patterns. Slots are left alone —
    they use ``{}``, so they can never be confused with either construct.
    """
    results = [pattern]
    changed = True
    while changed:
        changed = False
        expanded: List[str] = []
        for candidate in results:
            alt = _ALTERNATION.search(candidate)
            if alt:
                for option in alt.group(1).split("|"):
                    expanded.append(candidate[: alt.start()] + option + candidate[alt.end():])
                changed = True
                continue
            opt = _OPTIONAL.search(candidate)
            if opt:
                expanded.append(candidate[: opt.start()] + opt.group(1) + candidate[opt.end():])
                expanded.append(candidate[: opt.start()] + candidate[opt.end():])
                changed = True
                continue
            expanded.append(candidate)
        results = expanded

    # Dropping an optional leaves a double space behind.
    cleaned = [_WHITESPACE.sub(" ", r).strip() for r in results]
    return list(dict.fromkeys(p for p in cleaned if p))


def specificity(pattern: str) -> int:
    """How much of a pattern is literal text rather than a slot.

    Used to rank competing matches: `send mail to {r} subject {s} body {b}` is a
    more precise reading of an email command than `send mail to {r}`, so it must
    win regardless of the order intents were registered in.
    """
    return len(_SLOT.sub("", pattern).replace(" ", ""))


#: When a pattern does not begin with a literal word, this much literal text is
#: required elsewhere in it. Two letters of connective ("is", "to", "at") is not
#: an anchor; "number is" is.
MIN_FLOATING_LITERALS = 4


def is_anchored(pattern: str) -> bool:
    """Whether a pattern is specific enough to be safe to register.

    An unanchored pattern does not announce itself — it silently captures other
    skills' commands, which is precisely the failure mode of the substring chain
    this module replaces. `{key} is {value}` matches *any* sentence containing
    " is ", and `{a} {b}` matches nearly everything.

    This is not hypothetical. `[(save|store|note)] [that] {key} is {value}` was
    registered for the memory skill; every segment is optional, so its expansion
    included the bare `{key} is {value}`, and "what is the capital of france" was
    filed as a memory.

    Two ways to be anchored, either sufficing:

    * **Prefix-anchored** — begins with literal text. `end {process}` qualifies
      even though "end" is short, because it can only match commands that start
      with that word.
    * **Enough literal text** — `{name} number is {phone}` opens with a slot but
      carries "number is", which is specific enough to be meant.
    """
    stripped = pattern.strip()
    if not stripped:
        return False
    if not stripped.startswith("{"):
        return True
    return specificity(stripped) >= MIN_FLOATING_LITERALS


@dataclass(frozen=True)
class Match:
    """A pattern that matched, and what it captured."""

    intent: str
    slots: Dict[str, Any]
    pattern: str
    specificity: int = field(default=0)


class IntentContainer:
    """Matches text against registered patterns. Single process, no threads."""

    def __init__(self) -> None:
        # intent -> list of (compiled matcher, source pattern, specificity)
        self._intents: Dict[str, List[tuple]] = {}

    def add_intent(self, name: str, patterns: Iterable[str]) -> None:
        """Registers patterns for an intent. Matching is case-insensitive."""
        compiled = self._intents.setdefault(name, [])
        for raw in patterns:
            for concrete in expand_pattern(raw.lower()):
                if not is_anchored(concrete):
                    raise ValueError(
                        f"{name}: pattern {raw!r} expands to {concrete!r}, which is "
                        f"not anchored — it would match almost any input. Either "
                        f"start it with a literal word, or give it at least "
                        f"{MIN_FLOATING_LITERALS} characters of literal text. "
                        f"`(save|store) {{key}} is {{value}}` is fine; "
                        f"`[(save|store)] {{key}} is {{value}}` is not, because "
                        f"dropping every optional leaves a bare `{{key}} is {{value}}`."
                    )
                # `case_sensitive=False` rather than lowercasing the input:
                # matching must ignore case, but *captures* must not. Lowercasing
                # the command first would have sent an email with the subject
                # "greetings" when the user typed "Greetings", and would mangle
                # every proper noun, path and message body passing through a slot.
                compiled.append((
                    simplematch.Matcher(concrete, case_sensitive=False),
                    concrete,
                    specificity(concrete),
                ))

    def calc_intent(self, text: str) -> Optional[Match]:
        """Returns the most specific matching intent, or None.

        Deliberately all-or-nothing: a pattern either describes the whole command
        or it does not apply. Partial credit is what let `"eth" in cmd_lower`
        route "what did I say about the **meth**od" to a crypto price lookup.
        """
        cleaned = _WHITESPACE.sub(" ", (text or "").strip()).strip(" .!?")
        if not cleaned:
            return None

        best: Optional[Match] = None
        for intent, entries in self._intents.items():
            for matcher, pattern, score in entries:
                captured = matcher.match(cleaned)
                if captured is None:
                    continue
                if best is None or score > best.specificity:
                    best = Match(
                        intent=intent,
                        slots={k: _tidy(v) for k, v in captured.items()},
                        pattern=pattern,
                        specificity=score,
                    )
        return best

    @property
    def intents(self) -> List[str]:
        return sorted(self._intents)

    def pattern_count(self) -> int:
        return sum(len(v) for v in self._intents.values())


def _tidy(value: Any) -> Any:
    """Strips the quotes users type around slot values.

    `subject "Greetings"` should capture `Greetings`, not `"Greetings"` — the old
    hand-rolled email parser got this wrong in the other direction and sent a
    real message with an empty subject.
    """
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] and trimmed[0] in "\"'":
        return trimmed[1:-1].strip()
    return trimmed
