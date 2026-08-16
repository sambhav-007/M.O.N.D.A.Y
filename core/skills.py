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

from core.intent_patterns import IntentContainer, Match, slot_spec

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

    #: Whether stage 3 — the language model — may select this skill.
    #:
    #: Defaults to True and is forced False for Tier 2 in `__post_init__`, so the
    #: rule that irreversible actions need an exact pattern covers the model
    #: without being restated. Set it False by hand for the narrower case: a
    #: Tier-1 skill whose *implementation* is dangerous to reach on a guess.
    #: `create_desktop_folder` is the only one — it runs generated Python under
    #: `subprocess`, and "a low-confidence guess must not reach code execution"
    #: (UPGRADE_PLAN §1.2) is not a claim about tiers.
    llm_reachable: bool = True

    #: Whether this skill only *reads* — no launching, no writing, no sending,
    #: nothing a user would want undone.
    #:
    #: It governs one thing: whether a **stage-3 selection runs immediately or
    #: is proposed first**. Defaults to False, so a skill that declares nothing
    #: gets confirmed rather than fired.
    #:
    #: The measurement that put it here: asked to "shut down chrome for me right
    #: now", a 3B model selected `open_app_or_website` and MONDAY **launched
    #: Chrome** — the opposite of the request, performed without asking. The
    #: Tier-2 gate did its job (nothing irreversible was reached) and that was
    #: not enough, because "reversible" and "wanted" are different properties.
    #: Closing a browser is reversible; opening one you asked to close is still
    #: wrong.
    #:
    #: Patterns are exact, so a pattern match runs regardless of this flag. It
    #: only ever qualifies a guess.
    read_only: bool = False

    @property
    def slots(self) -> Dict[str, str]:
        """The arguments this skill's patterns can capture, as ``name -> type``.

        Derived from the patterns, never declared separately — see
        `core.intent_patterns.slot_spec`. This is what makes the skill registry
        usable as a function-calling manifest without a second source of truth.
        """
        return slot_spec(self.patterns)

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
        if self.tier == 2 and self.llm_reachable:
            # Forced rather than raised: the default is True because most skills
            # are fine, and a Tier-2 skill declaring nothing should get the safe
            # answer rather than an error someone silences by setting the flag.
            # A frozen dataclass needs object.__setattr__ to do it.
            object.__setattr__(self, "llm_reachable", False)


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

    def llm_reachable_skills(self) -> List[Skill]:
        """The skills stage 3 is allowed to offer the model.

        Everything Tier 2 is excluded automatically, plus anything that opted
        out. This list is the model's entire world: a skill absent from it
        cannot be selected by the model no matter what the model emits, because
        `core/llm.py` validates the returned name against exactly this set.
        """
        return [s for s in self.skills if s.llm_reachable]
