"""
M.O.N.D.A.Y. — ROADMAP Phase 13. Stage 4: a hosted model, for the hard questions.

The honest way to reach frontier-level *answers* is to let the user plug in a
frontier model, not to pretend a 3B is one. This is that slot.

It answers. It does not act.
-----------------------------
Stage 3 selects skills; stage 4 does **not**, and that is the whole design
rather than a limitation to be lifted later. It cannot name a skill, cannot fill
a slot, cannot reach Tier 2 and cannot reach generated-code execution, because
it is never asked for a tool call and its reply is never parsed as one. The
containment argument is therefore not a list of guards that must all hold — it
is the absence of a code path.

That matters here more than usual. Implementing hosted function-calling would
mean a second tool-schema translation, validated against a provider this machine
cannot exercise (no key is configured), and "this code never runs here" is a
claim about the environment rather than about the code — the lesson `pyttsx3`
taught when installing it woke a dormant path that started Outlook.

When it runs
------------
Only when **every** stage before it has declined: no pattern, no confident
classification, and stage 3 either absent or unable to answer. On a machine with
no key it never runs at all, and `Router` behaves exactly as it did before this
file existed.

Nothing leaves the machine unless the user configured a key — ROADMAP §7.4. The
key is `GEMINI_API_KEY`, the same one `agents/vision_agent.py` already looks
for, and the request goes through `TriModelCognitiveEngine` rather than a second
HTTP client: one place talks to a hosted model, and it is the place that already
had the credential handling, the header-not-query-string fix, and the falsy
`CognitiveResponseDict` when nothing answered.

What the answer is worth
------------------------
`ModelAnswered(host="remote")`. A model replied — not a lookup, not a check, not
an action. The `host` field is what lets a reader tell a local answer from one
that left the machine, which is a thing a user is entitled to know without
reading the configuration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

#: The reply is a sentence or two for a person at their computer, not an essay.
#: Same instruction stage 3 gets, for the same reason: this text is spoken aloud
#: by `voice/tts.py` on the way past.
SYSTEM_PREAMBLE = (
    "You are M.O.N.D.A.Y., a desktop assistant. Answer in one or two short "
    "sentences, as if speaking to someone at their computer. If you do not "
    "know, say so plainly. Never claim to have performed an action — you are "
    "answering a question, not operating the machine."
)


def remote_key_configured() -> bool:
    """Whether a hosted model is reachable at all.

    Checked without importing the agent, so `available()` costs nothing on the
    overwhelmingly common path where no key exists.
    """
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "")
        if value and len(value.strip()) > 10:
            return True
    try:
        from agents.vision_agent import load_gemini_api_key

        return bool(load_gemini_api_key())
    except Exception:  # noqa: BLE001
        return False


class RemoteAnswerStage:
    """Stage 4. Optional, off without a key, and incapable of acting.

    Deliberately *not* shaped like `LlmStage`: it has no `choose`, because
    choosing is what it must not do. A reviewer comparing the two files should
    find no route from here to a skill, and there is none to find.
    """

    #: Named in the evidence, so "which model said this" is answerable.
    model = "gemini-1.5-flash"

    def __init__(self, enabled: Optional[bool] = None) -> None:
        #: `MONDAY_REMOTE_LLM=off` switches it off even with a key present — the
        #: same escape hatch `MONDAY_LLM=off` gives stage 3, so a demo can
        #: guarantee nothing leaves the machine.
        self._forced = enabled
        self._reason = ""

    def available(self) -> bool:
        if self._forced is not None:
            self._reason = "" if self._forced else "disabled explicitly"
            return self._forced
        if os.environ.get("MONDAY_REMOTE_LLM", "").strip().lower() in {
            "off", "0", "false", "no"
        }:
            self._reason = "disabled by MONDAY_REMOTE_LLM"
            return False
        if not remote_key_configured():
            self._reason = "no hosted model configured (set GEMINI_API_KEY)"
            return False
        self._reason = ""
        return True

    @property
    def unavailable_reason(self) -> str:
        if not self._reason:
            self.available()
        return self._reason

    def answer(
        self,
        command: str,
        memories: Optional[List[Dict[str, Any]]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[str]:
        """Asks the hosted model. None when it declines, fails, or is off.

        `None` rather than an exception or a placeholder: stage 4 is the last
        stage, and its failure must degrade to the honest refusal that existed
        before it — never to a traceback, and never to a cheerful string that
        reads like an answer.
        """
        if not self.available():
            return None

        from core.cognitive import TriModelCognitiveEngine

        prompt = SYSTEM_PREAMBLE
        if history:
            recent = "\n".join(
                f"{turn.get('role', 'user')}: {turn.get('content', '')}"
                for turn in history[-4:]
            )
            prompt += f"\n\nRecent conversation:\n{recent}"
        prompt += f"\n\nQuestion: {command}"

        try:
            reply = TriModelCognitiveEngine().generate_cognitive_response(
                prompt, retrieved_memories=memories or []
            )
        except Exception:  # noqa: BLE001
            return None

        # `CognitiveResponseDict` is falsy unless a model actually answered —
        # the fix that this repository had to make twice. Trusting it here is
        # the point of routing through that class rather than around it.
        if not reply:
            return None

        text = str(reply.get("response", "")).strip()
        return text or None
