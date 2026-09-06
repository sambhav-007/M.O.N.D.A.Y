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
``{name:int}``     typed capture (simplematch's types: int, float, email, ...)
``{name:app}``     an app or domain name — at most ``MAX_APP_TOKENS`` tokens
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

#: The wake word, which the browser UI already listens for ("Hey Monday") and
#: which people then repeat in the typed box. A bare name is only treated as a
#: wake word when a greeting introduces it or a comma follows it — otherwise
#: "monday morning meeting" would lose its day. `olly` is MASSIVE's assistant
#: name and appears in front of ~1 in 20 utterances there.
#
#: The greeting can appear in the natural forms "hi monday", "hello monday",
#: and "hi to monday" / "hello to monday". Taking the `to` between the
#: greeting and the name is intentional: that variant shows up in real speech,
#: and it should not be mistaken for a command that starts with the word "to".
_WAKE_WORD = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay)[\s,]+(?:to[\s,]+)?(?:monday|olly)|(?:monday|olly)\s*,)[\s,]*",
    re.IGNORECASE,
)

#: Openers people put in front of a command. Taken from the real corpus rather
#: than invented: `audio_volume_up` alone has "can you", "could you please" and
#: "please" wrapped around commands MONDAY already serves.
_CIVILITY_OPENER = re.compile(
    r"^(?:(?:please|kindly|"
    r"can you|could you|would you|will you|can we|"
    r"i want you to|i need you to|i would like you to|i'd like you to|"
    r"i want to|i need to|i would like to|i'd like to|"
    r"let's|lets)[\s,]+)+",
    re.IGNORECASE,
)

#: Closers. `for me` is included because "turn the volume up for me" is common
#: and means nothing MONDAY can act on differently.
_CIVILITY_CLOSER = re.compile(
    r"[\s,]*(?:please|thanks|thank you|for me|if you (?:can|could)|"
    r"would you|will you|ok|okay)[\s,.!?]*$",
    re.IGNORECASE,
)


def strip_civilities(text: str) -> str:
    """Removes wake words and politeness from the edges of a command.

    Edges only. A "please" inside the command is content — it may be sitting in
    an email body or a WhatsApp message, and those go out to real people.

    Returns the text unchanged when there is nothing to strip, so the caller can
    tell whether a retry is worth attempting.
    """
    stripped = (text or "").strip()
    # Alternating, because each can reveal the other: "hey monday please mute"
    # and "please, monday, mute" both occur.
    while True:
        shorter = _CIVILITY_CLOSER.sub("", _CIVILITY_OPENER.sub("", _WAKE_WORD.sub("", stripped))).strip()
        if shorter == stripped:
            break
        stripped = shorter
    # Never hand back an empty command: "please" on its own is not a command,
    # and an empty string would match a pattern made only of optional segments.
    return stripped or (text or "").strip()

#: Most tokens a `{name:app}` slot will accept.
MAX_APP_TOKENS = 3

# `{target}` compiles to `.*`, which swallows the rest of the command: "open
# whatsapp and message papa saying hi" reads as a request to launch an
# application called "whatsapp and message papa saying hi".
#
# The substring chain guarded against that by counting words — it stripped the
# verb and gave up if more than three were left. That guard was doing real work
# and is kept, but as a property of the *slot* rather than of the whole command,
# which is what let "open youtube.com on my browser" (four words after the verb)
# be rejected as an app name instead of understood as a URL plus a destination.
# A program or domain name is one to three tokens; anything longer is a sentence
# and belongs to a handler that can parse it.
simplematch.register_type("app", r"\S+(?: \S+){0,%d}" % (MAX_APP_TOKENS - 1))

# An arithmetic expression, and nothing else. Digits and operators only, with at
# least one operator so a bare number is not mistaken for a sum — "what is 42"
# is a question about 42, not a calculation of it.
#
# This is what lets `what is {expression:math}` and `what is {topic}` coexist:
# they carry identical literal text, so the typed slot is what separates them
# (see `typed_slots`).
simplematch.register_type(
    "math", r"[\d.()\s]*\d[\d.()\s]*(?:[-+*/^%][\d.()\s]*\d[\d.()\s]*)+"
)

# A literal phone number. Loose on formatting (people type +91 98765 43210,
# (555) 123-4567 and 9876543210) and strict on content: digits and separators
# only, never letters. `CommunicationAgent.normalise_phone` is what decides
# whether it is a *valid* number; this only decides whether the user typed one.
#
# It exists so "message +919876543210 saying hi" and "message the team about
# friday" can be told apart by the pattern rather than by a handler that has
# already committed to messaging someone.
simplematch.register_type("phone", r"\+?\d[\d\-().]*(?:[ ][\d\-().]+)*\d")


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


_TYPED_SLOT = re.compile(r"\{[^{}]*:[^{}]*\}")
#: `{name}` or `{name:type}` — captures both halves.
_SLOT_PARTS = re.compile(r"\{([^{}:]+)(?::([^{}]+))?\}")


def slot_spec(patterns: Iterable[str]) -> Dict[str, str]:
    """The slots a set of patterns can capture, as ``name -> type``.

    Type is ``""`` for an untyped ``{slot}``. Where the same name appears both
    typed and untyped, the type wins — a name that is ever constrained is better
    described by the constraint.

    This exists so a skill's arguments can be **derived** rather than declared
    twice. `core/llm.py` builds the tool schema the language model is offered
    straight from here, so a pattern gaining a slot gains an argument, and a
    schema cannot drift away from the patterns it claims to describe. The
    alternative — a hand-written JSON schema beside the patterns — is the exact
    shape of the stale-artefact problem this repository keeps finding.
    """
    found: Dict[str, str] = {}
    for pattern in patterns:
        for name, slot_type in _SLOT_PARTS.findall(pattern):
            key = name.strip()
            if not key:
                continue
            existing = found.get(key, "")
            found[key] = (slot_type or "").strip() or existing
    return found


def typed_slots(pattern: str) -> int:
    """How many of a pattern's slots are constrained to a type.

    The tie-breaker under `specificity`, and it exists because literal text alone
    cannot separate two equally-worded readings of the same command.
    `what is {topic}` and `what is {expression:math}` carry identical literal
    text, so ranking on that alone left "what is 12 * 8" decided by which skill
    happened to be registered first — the invisible ordering dependency this
    module was written to remove.

    A typed slot matches strictly less than a free one, so preferring it is the
    same principle as preferring literal text: **the more constrained reading of
    a command is the more likely one to be meant.** `{expression:math}` only
    accepts arithmetic, so when it matches at all, arithmetic is what was typed.
    """
    return len(_TYPED_SLOT.findall(pattern))


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
    typed_slots: int = field(default=0)

    @property
    def rank(self) -> tuple:
        """Literal text first, then constraint. See `typed_slots`."""
        return (self.specificity, self.typed_slots)


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
                    typed_slots(concrete),
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

        best = self._best_match(cleaned)
        if best is not None:
            return best

        # Second pass, and only ever a second one. Measured on the 10,631 real
        # utterances in `data/external/massive_en_us.csv`, the largest single
        # class of miss is a command MONDAY already serves wrapped in "can you
        # …", "please …" or a wake word. Retrying after the wrapper is removed
        # cannot change a match that already succeeded — it never runs when one
        # did — so no pattern's meaning or captured slots move.
        polite = strip_civilities(cleaned)
        if polite != cleaned:
            return self._best_match(polite)
        return None

    def _best_match(self, cleaned: str) -> Optional[Match]:
        """The most specific pattern matching this exact text, or None."""
        best: Optional[Match] = None
        for intent, entries in self._intents.items():
            for matcher, pattern, score, typed in entries:
                captured = matcher.match(cleaned)
                if captured is None:
                    continue
                if best is None or (score, typed) > best.rank:
                    best = Match(
                        intent=intent,
                        slots={k: _tidy(v) for k, v in captured.items()},
                        pattern=pattern,
                        specificity=score,
                        typed_slots=typed,
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
