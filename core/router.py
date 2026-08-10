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

#: Below this, the classifier is guessing and stage 2 declines to act on it.
#: `predict_intent`'s own fallback threshold is 0.65; this is the routing floor,
#: kept separate because they answer different questions — "should we ask an LLM"
#: versus "may this dispatch to a handler".
MIN_INTENT_CONFIDENCE = 0.50


@dataclass(frozen=True)
class RoutingDecision:
    """How a command was routed, and by what."""

    stage: str                      # "pattern" | "classifier" | "fallback"
    skill: Optional[Skill] = None
    slots: Dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    confidence: float = 0.0
    reason: str = ""

    @property
    def routed(self) -> bool:
        return self.skill is not None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "skill": self.skill.name if self.skill else None,
            "slots": self.slots,
            "intent": self.intent,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
        }


class Router:
    """Chooses a skill for a command. Chooses only — running it is the caller's."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def route(
        self,
        command: str,
        intent: str = "",
        confidence: float = 0.0,
    ) -> RoutingDecision:
        """Returns the routing decision without executing anything.

        Separating the choice from the execution is deliberate: it makes routing
        testable over the whole `datagen/` corpus without running a single
        handler, which is what turns component 2.1's offline F1 into an
        end-to-end routing-accuracy figure.
        """
        # ── Stage 1: patterns ────────────────────────────────────────────────
        match = self.registry.match_pattern(command)
        if match is not None:
            skill = self.registry.get(match.intent)
            if skill is not None:
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

        # ── Stage 3: hand back to the legacy handler ─────────────────────────
        if intent and confidence < MIN_INTENT_CONFIDENCE:
            reason = f"intent '{intent}' at {confidence:.2f} is below the {MIN_INTENT_CONFIDENCE} floor"
        elif intent:
            reason = f"no skill serves intent '{intent}'"
        else:
            reason = "no pattern matched and no intent supplied"

        return RoutingDecision(
            stage="fallback", intent=intent, confidence=confidence, reason=reason
        )
