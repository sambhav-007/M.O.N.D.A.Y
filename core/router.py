"""
M.O.N.D.A.Y. — the three-stage router.

Replaces the substring chain in `MasterPlanner._dispatch_to_agent` with an
explicit cascade, borrowed from the pipeline shape OpenVoiceOS/Mycroft settled
on for the same reason: every assistant grows a 500-line `if/elif` and then has
to escape it.

    command
      │
      ├─ Stage 1  PATTERN      declarative patterns → skill + typed slots
      │                        deterministic, offline, ~0.01 ms
      │
      ├─ Stage 2  CLASSIFIER   component 2.1 picks the skill *family*
      │                        ← this is where the 0.929 macro-F1 finally does work
      │
      └─ Stage 3  FALLBACK     the legacy handler, shrinking as skills migrate

Why the order matters
---------------------
Stage 1 first means the demo-critical commands never depend on a model or a
network. Stage 2 second means the classifier is consulted *before* dispatch
rather than after it, which is the whole point of the phase: it used to be
computed on every command and then ignored for the first ~350 lines of routing.

Stage 3 exists so the migration can be incremental. Every skill moved out of the
legacy handler is one the classifier now genuinely routes; the count is reported
by `RoutingDecision.stage` so progress is measurable rather than asserted.

The confidence floor
--------------------
Stage 2 only accepts a classification at or above `MIN_INTENT_CONFIDENCE`.
Without a floor, "search current AI news" classified as `desktop_automation` at
**0.33** and was dispatched to `CoderAgent`, which wrote a Python script and ran
it in a subprocess. A guess that weak should not reach code execution, and now
it does not — it falls through to stage 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.skills import Skill, SkillRegistry
from core.slot_sanity import implausible
import re

#: Below this, the classifier is guessing and stage 2 declines to act on it.
#: `predict_intent`'s own fallback threshold is 0.65; this is the routing floor,
#: kept separate because they answer different questions — "should we ask an LLM"
#: versus "may this dispatch to a handler".
MIN_INTENT_CONFIDENCE = 0.50
_DIRECT_ANSWER_RE = re.compile(
    r"^(?:(?:is|are|should|would|could|can|do you think|what do you think)\b.*"
    r"\b(?:death|die|dying|suffer|suffering|life|meaning|morality|moral|ethical|ethics|better)\b|"
    r"(?:teach|teach me|help me learn|learn)\b.*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RoutingDecision:
    """How a command was routed, and by what."""

    # "pattern" | "classifier" | "llm" | "llm_answer" | "fallback"
    stage: str
    skill: Optional[Skill] = None
    slots: Dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    confidence: float = 0.0
    reason: str = ""
    #: Set only for stage "llm_answer": the model answered instead of choosing a
    #: skill. Text, never something that gets executed.
    answer: str = ""
    #: Which model produced `answer`, so the reply can say so.
    model: str = ""

    @property
    def routed(self) -> bool:
        return self.skill is not None

    def as_dict(self) -> Dict[str, Any]:
        out = {
            "stage": self.stage,
            "skill": self.skill.name if self.skill else None,
            "slots": self.slots,
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
        }
        if self.answer:
            out["model"] = self.model
        return out


class Router:
    """Chooses a skill for a command. Chooses only — running it is the caller's."""

    def __init__(
        self,
        registry: SkillRegistry,
        llm: Optional[Any] = None,
        remote: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        #: Stage 4 (ROADMAP Phase 13). A hosted model that **answers only** — it
        #: is never offered the tool schema and its reply is never read as a
        #: skill, so there is no path from here to an action to guard. Off
        #: without a key, and then the cascade ends exactly where it did before.
        self.remote = remote
        #: Stage 3. Optional by construction: `None` means the cascade ends at
        #: stage 2 exactly as it did before, which is also what happens when no
        #: Ollama server is running.
        self.llm = llm

    def route(
        self,
        command: str,
        intent: str = "",
        confidence: float = 0.0,
        emit: Optional[Any] = None,
        history: Optional[Any] = None,
        memories: Optional[Any] = None,
    ) -> RoutingDecision:
        """Returns the routing decision without executing anything.

        Separating the choice from the execution is deliberate: it makes routing
        testable over the whole `datagen/` corpus without running a single
        handler, which is what turns component 2.1's offline F1 into an
        end-to-end routing-accuracy figure.
        """
        # ── Stage 1: patterns ────────────────────────────────────────────────
        rejected_parse = ""
        match = self.registry.match_pattern(command)
        if match is not None:
            skill = self.registry.get(match.intent)
            if skill is not None:
                # Matching is not the same as being right. `book me a flight to
                # delhi on tuesday` matched the calendar pattern and captured
                # title='me a flight to delhi', and `schedule_event` acts — so a
                # junk entry went into a real calendar with no question asked. A
                # parse that fails its plausibility check is declined here and
                # the cascade continues, because "stage 1 has no confident
                # reading" is exactly what stages 2 and 3 are for.
                rejected_parse = implausible(skill, match.slots, command) or ""
                if not rejected_parse:
                    return RoutingDecision(
                        stage="pattern",
                        skill=skill,
                        slots=match.slots,
                        intent=intent,
                        confidence=confidence,
                        reason=f"matched pattern '{match.pattern}'",
                    )

        # ── Stage 2: the classifier ──────────────────────────────────────────
        if intent and confidence >= MIN_INTENT_CONFIDENCE:
            candidates = self.registry.by_intent(intent)
            if len(candidates) == 1:
                return RoutingDecision(
                    stage="classifier",
                    skill=candidates[0],
                    slots={},
                    intent=intent,
                    confidence=confidence,
                    reason=f"intent '{intent}' at {confidence:.2f}",
                )
            if len(candidates) > 1:
                # Ambiguity is not a decision. Two skills claiming one intent
                # class means the patterns need sharpening, not that one of them
                # should be picked arbitrarily — which is exactly what "whichever
                # branch came first" used to do.
                return RoutingDecision(
                    stage="fallback",
                    intent=intent,
                    confidence=confidence,
                    reason=(
                        f"intent '{intent}' matches {len(candidates)} skills "
                        f"({', '.join(s.name for s in candidates)}) — ambiguous"
                    ),
                )

        # ── Why the deterministic stages declined ────────────────────────────
        if rejected_parse:
            reason = f"pattern parse rejected — {rejected_parse}"
        elif intent and confidence < MIN_INTENT_CONFIDENCE:
            reason = f"intent '{intent}' at {confidence:.2f} is below the {MIN_INTENT_CONFIDENCE} floor"
        elif intent:
            reason = f"no skill serves intent '{intent}'"
        else:
            reason = "no pattern matched and no intent supplied"

        # ── Stage 3: the language model ──────────────────────────────────────
        # Last, and only when both stages above have declined — so nothing here
        # can change what a pattern already decided, and the offline guarantees
        # of stage 1 are untouched by whether a model happens to be running.
        if self.llm is not None:
            # The only slow step in the cascade, and the only one worth
            # announcing: stages 1 and 2 answer in under a millisecond, while a
            # cold model can take a minute or more to load. A caller that says
            # nothing here looks hung.
            if emit is not None:
                emit("consulting_model", {"model": getattr(self.llm, "model", "")})
            choice = self.llm.choose(
                command,
                # Fragments of a written answer, as they are produced. With a
                # large tool schema most commands produce none — the model
                # selects a tool instead, which is one chunk, not a stream.
                on_token=(lambda f: emit("token", {"text": f})) if emit else None,
                # Only stage 3 gets conversation context. Stages 1 and 2 are
                # stateless on purpose: a pattern that matched yesterday must
                # match today, and a classifier whose answer depended on the
                # previous command would make the published routing figure
                # unreproducible.
                history=history,
                # Stored facts, for the same reason and with the same limit:
                # stage 3 alone. A pattern whose meaning depended on what the
                # user once asked to be remembered would match differently on
                # two machines.
                memories=memories,
                direct_answer=bool(_DIRECT_ANSWER_RE.match(command.strip())),
            )
            if choice is not None and choice.skill:
                skill = self.registry.get(choice.skill)
                if skill is not None:
                    note = ""
                    if choice.dropped:
                        note = f", dropped {', '.join(sorted(choice.dropped))}"
                    return RoutingDecision(
                        stage="llm",
                        skill=skill,
                        slots=choice.arguments,
                        intent=intent,
                        confidence=confidence,
                        reason=f"{reason}; {choice.model} chose '{skill.name}'{note}",
                    )
            if choice is not None and choice.text:
                # No skill fits and the model answered instead. Carried on the
                # decision rather than executed: the planner decides how to
                # present generated text, and it is the only path that produces
                # `ModelAnswered` evidence.
                return RoutingDecision(
                    stage="llm_answer",
                    intent=intent,
                    confidence=confidence,
                    reason=f"{reason}; {choice.model} answered directly",
                    answer=choice.text,
                    model=choice.model,
                )
            if choice is None:
                detail = getattr(self.llm, "unavailable_reason", "")
                reason = f"{reason}; stage 3 declined" + (f" ({detail})" if detail else "")

        # ── Stage 4: a hosted model, if the user configured one ──────────────
        # Last of all, and only for a *question* — every stage above has
        # declined, so nothing it says can displace a pattern, a classification
        # or a local model. It cannot name a skill because it is never asked
        # for one.
        if self.remote is not None and self.remote.available():
            if emit is not None:
                emit("consulting_remote", {"model": getattr(self.remote, "model", "")})
            text = self.remote.answer(command, memories=memories, history=history)
            if text:
                return RoutingDecision(
                    stage="remote_answer",
                    intent=intent,
                    confidence=confidence,
                    reason=f"{reason}; hosted {self.remote.model} answered",
                    answer=text,
                    model=self.remote.model,
                )
            reason = f"{reason}; stage 4 declined"

        return RoutingDecision(
            stage="fallback", intent=intent, confidence=confidence, reason=reason
        )
