"""What MONDAY says out loud, as opposed to what it prints.

A reply on screen can be a table, a list of five search results, or a
three-line caveat about WhatsApp delivery. Read aloud, all of that is
unbearable — and it was being read aloud verbatim, because the UI passed
`execution_result.message` straight to `speechSynthesis`. Live examples:

    what's the distance from Los Angeles to France
      → 45 seconds of scraped SEO copy, read to the end
    Shivansh number is 73409 00212
      → the saved number, then the whole Tier-2 prompt including
        "can't be undone · est. 1s", then the question

Speaking is not printing. Screen text can be skimmed and re-read; speech is
linear and cannot be skipped, so it has to be shorter and it has to lead with
the answer.

The rule here, in order:

1. If the handler set ``data["speech"]``, use it. A handler knows what the
   spoken form of its own result is — `desktop_contents` already did this
   ("3 files and 2 folders on your Desktop") long before this module existed,
   and that convention is what this generalises.
2. Otherwise derive one from the message: drop the decoration, keep the first
   sentence or two, and stop.

`to_speech` is deliberately the only place that decides. `cli.py`, the API and
the UI all read the same `speech` field, so what is spoken cannot drift between
surfaces the way `/help` once did.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

#: Longest spoken reply, in characters. Roughly 12 seconds at a normal rate.
#: Past that a listener has stopped following and is waiting for it to end.
MAX_SPEECH_CHARS = 240

#: Status glyphs, box drawing and markdown that mean nothing aloud. `✓` read as
#: "check mark" and `⚠️` as "warning sign" at the start of every single reply.
_DECORATION = re.compile(
    r"[✓✗❌⚠️🔒🤖🗣️🎙️🖥️📧📁🌐🧠📊💰⚡💡🔍►•·—–\[\]*`_#|]+"
)
_WHITESPACE = re.compile(r"\s+")
#: A sentence end followed by a space and a capital, or the end of the string.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
#: "Source: Title — https://…" and bare URLs. Reading a URL aloud is noise.
_SOURCE_TAIL = re.compile(r"\s*(source|sources?\s+consulted)\s*:.*$", re.IGNORECASE | re.DOTALL)
_URL = re.compile(r"https?://\S+|www\.\S+")


def clean_for_speech(text: str) -> str:
    """Strips decoration, URLs and source citations from a message."""
    out = _SOURCE_TAIL.sub("", str(text or ""))
    out = _URL.sub("", out)
    out = _DECORATION.sub(" ", out)
    return _WHITESPACE.sub(" ", out).strip(" .,:;-").strip()


def to_speech(message: str, data: Optional[Dict[str, Any]] = None) -> str:
    """The spoken form of a result. Never longer than `MAX_SPEECH_CHARS`.

    `data` is the result dict; an explicit `speech` key wins outright, because
    a handler describing its own result will always beat a generic truncation.
    """
    if data:
        explicit = data.get("speech")
        if isinstance(explicit, str) and explicit.strip():
            return _WHITESPACE.sub(" ", explicit).strip()

    cleaned = clean_for_speech(message)
    if not cleaned:
        return ""
    if len(cleaned) <= MAX_SPEECH_CHARS:
        return cleaned

    # Whole sentences up to the budget, so it never stops mid-word.
    spoken = ""
    for sentence in _SENTENCE.split(cleaned):
        candidate = f"{spoken} {sentence}".strip()
        if spoken and len(candidate) > MAX_SPEECH_CHARS:
            break
        spoken = candidate

    if not spoken:
        # One sentence longer than the whole budget — cut at a word boundary.
        spoken = cleaned[:MAX_SPEECH_CHARS].rsplit(" ", 1)[0]

    spoken = spoken.rstrip(" ,;:-")
    if len(spoken) < len(cleaned) and not spoken.endswith((".", "!", "?")):
        spoken += "."
    return spoken
