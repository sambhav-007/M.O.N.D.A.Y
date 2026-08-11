"""
M.O.N.D.A.Y. — the skill registry.

A skill is one thing MONDAY can do, declared in one place: the patterns that
select it, the intent classes it belongs to, its risk tier, and the handler that
runs it.

The point of collecting these is what it replaces. Routing used to live in
`MasterPlanner._dispatch_to_agent` as ~350 lines of substring tests
(`if "volume" in cmd_lower`, `elif "eth" in cmd_lower`) evaluated *before*
`intent` — the output of component 2.1 — was consulted at all. Three
consequences, all of which this registry is meant to end:

* **The classifier decided almost nothing.** Its published 0.929 macro-F1
  described a model that was consulted after most commands had already been
  routed by a substring.
* **Substrings collide.** `"eth" in cmd_lower` matches "som**eth**ing",
  "wh**eth**er" and "m**eth**od"; a command containing any of them was answered
  with the price of Ethereum. Patterns match whole commands, so they cannot.
* **Order was load-bearing and invisible.** Whichever branch appeared first won,
  which is why `"gmail"` matching inside a Gmail *address* silently shadowed the
  branch that could actually parse an email command.

Skills are registered here and matched by `core/router.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.intent_patterns import IntentContainer, Match

# A handler takes the captured slots and the original command, and returns the
# usual result dict (built via core.contracts.AgentResult).
Handler = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class Skill:
    """One capability, and everything needed to route to it."""

    name: str
    patterns: List[str]
    handler: Handler
    #: Intent classes from component 2.1 that this skill can serve. Used by
    #: stage 2, when no pattern matched and the classifier picks a family.
    #:
    #: **Stage 2 supplies no slots.** It knows only that the command belongs to a
    #: family, so a skill listed here has to do something sensible when called
    #: with nothing. `remember_fact` does not — it needs a key and a value — and
    #: declaring it here sent "what is on my desktop" (classified `memory_query`
    #: at 0.52) into the memory *writer*, which replied "What should I remember?".
    #: A question reaching a write path is exactly the kind of thing this router
    #: was built to stop, so the rule is enforced below rather than remembered.
    intents: List[str] = field(default_factory=list)
    #: PRD §9 risk tier. Tier 2 never runs without a separate confirming turn.
    tier: int = 1
    #: True when the skill needs no network — the demo-safe set.
    offline: bool = True
    description: str = ""

    #: Set only when the handler runs sensibly with **no slots at all**, which is
    #: the condition for being reachable from stage 2.
    runs_without_slots: bool = False

    def __post_init__(self) -> None:
        if self.tier not in (1, 2):
            raise ValueError(f"{self.name}: tier must be 1 or 2, got {self.tier}")
        if not self.patterns and not self.intents:
            raise ValueError(
                f"{self.name}: a skill unreachable by pattern and by intent can "
                f"never be selected"
            )
        if self.intents and not self.runs_without_slots:
            raise ValueError(
                f"{self.name}: declares intents {self.intents} but not "
                f"`runs_without_slots`. Stage 2 routes on a classifier family and "
                f"passes no slots, so a skill reached that way must do something "
                f"useful with none. If it needs a key, a path or a target, leave "
                f"`intents` empty and let patterns select it."
            )
        if self.tier == 2 and self.intents:
            raise ValueError(
                f"{self.name}: a Tier-2 skill must not be reachable from the "
                f"classifier. Irreversible actions need the exactness of a "
                f"pattern, not a family guess."
            )


class SkillRegistry:
    """Holds the skills and answers "which one does this command want?"."""

    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}
        self._patterns = IntentContainer()

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name}")
        self._skills[skill.name] = skill
        if skill.patterns:
            self._patterns.add_intent(skill.name, skill.patterns)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def match_pattern(self, command: str) -> Optional[Match]:
        """Stage 1: exact, deterministic, no model involved."""
        return self._patterns.calc_intent(command)

    def by_intent(self, intent: str) -> List[Skill]:
        """Stage 2: every skill that serves a classifier intent class."""
        return [s for s in self._skills.values() if intent in s.intents]

    @property
    def skills(self) -> List[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name)

    @property
    def names(self) -> List[str]:
        return sorted(self._skills)

    def pattern_count(self) -> int:
        return self._patterns.pattern_count()

    def tier2_names(self) -> List[str]:
        return sorted(s.name for s in self._skills.values() if s.tier == 2)
