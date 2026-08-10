"""
M.O.N.D.A.Y. — the migrated skills.

First tranche: the offline utility commands. They are the ones the demo leans on
and the ones with the least to go wrong, which is why they move first — the
riskiest paths (email, WhatsApp) migrate last, behind their existing tests.

Each entry replaces a branch of the substring chain in
`MasterPlanner._dispatch_to_agent`, and the comment on it records what that
branch got wrong, so the same mistake is not reintroduced by someone widening a
pattern later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from core.contracts import AgentResult, SystemQuery
from core.skills import Skill, SkillRegistry


def build_builtin_registry(planner: Any) -> SkillRegistry:
    """Builds the registry, binding handlers to a planner's agents."""
    registry = SkillRegistry()

    # ── Time and date ────────────────────────────────────────────────────────
    def tell_time(**_: Any) -> Dict[str, Any]:
        now = datetime.now()
        return AgentResult.ok(
            f"✓ Current time is {now.strftime('%I:%M %p')}.",
            evidence=SystemQuery(source="system clock", detail=now.isoformat(timespec="seconds")),
            data={"intent": "time"},
        ).as_dict()

    registry.register(Skill(
        name="tell_time",
        description="What time is it",
        patterns=[
            "[(what|whats|what's)] [is] [the] time [is it]",
            "time",
            "current time",
            "tell me [the] time",
            "what time is it",
        ],
        handler=tell_time,
        tier=1,
        offline=True,
    ))

    def tell_date(**_: Any) -> Dict[str, Any]:
        now = datetime.now()
        return AgentResult.ok(
            f"✓ Today's date is {now.strftime('%A, %B %d, %Y')}.",
            evidence=SystemQuery(source="system clock", detail=now.date().isoformat()),
            data={"intent": "date"},
        ).as_dict()

    registry.register(Skill(
        name="tell_date",
        description="What is today's date",
        patterns=[
            "[(what|whats|what's)] [is] [the] date [today]",
            "date",
            "todays date",
            "today's date",
            "what day is it",
        ],
        handler=tell_date,
        tier=1,
        offline=True,
    ))

    # ── Battery ──────────────────────────────────────────────────────────────
    # The old branch fired on `"charge" in cmd_lower`, so "how do I charge for
    # consulting" asked about the laptop battery. Patterns match whole commands.
    def battery(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.get_battery_status()

    registry.register(Skill(
        name="battery_status",
        description="Battery level and charging state",
        patterns=[
            "battery",
            "battery [(status|level|health|percentage)]",
            "[(what is|whats|what's)] [my] battery [(status|level|percentage)]",
            "[(am i|is it)] charging",
            "power status",
        ],
        handler=battery,
        tier=1,
        offline=True,
    ))

    # ── Volume ───────────────────────────────────────────────────────────────
    # `"volume" in cmd_lower` then `re.search(r'(\d+)', command)` took the first
    # number *anywhere* in the command, so "set volume to 50 on monitor 2" could
    # read the wrong one. A typed slot binds the number to its position.
    def set_volume(level: int = 50, **_: Any) -> Dict[str, Any]:
        return planner.computer_agent.set_system_volume(int(level))

    registry.register(Skill(
        name="set_volume",
        description="Set the system volume to a level",
        patterns=[
            "[(set|change|put|turn)] [the] volume [to] {level:int}",
            "[(set|change|put|turn)] [the] volume [to] {level:int} percent",
            "[(set|change|put|turn)] [the] volume [to] {level:int}%",
            "volume {level:int}",
        ],
        handler=set_volume,
        tier=1,
        offline=True,
    ))

    def mute(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.set_system_volume(0)

    registry.register(Skill(
        name="mute_volume",
        description="Mute the system volume",
        patterns=["mute", "mute [the] (volume|sound|audio)", "silence [the] (volume|sound|audio)"],
        handler=mute,
        tier=1,
        offline=True,
    ))

    def volume_up(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.set_system_volume(80)

    registry.register(Skill(
        name="volume_up",
        description="Turn the volume up",
        patterns=[
            "[(turn|put)] [the] volume up",
            "(increase|raise) [the] volume",
            "louder",
        ],
        handler=volume_up,
        tier=1,
        offline=True,
    ))

    def volume_down(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.set_system_volume(30)

    registry.register(Skill(
        name="volume_down",
        description="Turn the volume down",
        patterns=[
            "[(turn|put)] [the] volume down",
            "(decrease|lower|reduce) [the] volume",
            "quieter",
        ],
        handler=volume_down,
        tier=1,
        offline=True,
    ))

    def read_volume(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.get_system_volume()

    registry.register(Skill(
        name="read_volume",
        description="Report the current volume",
        patterns=[
            "[(what is|whats|what's)] [the] [current] volume",
            "how loud is it",
        ],
        handler=read_volume,
        tier=1,
        offline=True,
    ))

    # ── System health ────────────────────────────────────────────────────────
    def health(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.get_system_health()

    registry.register(Skill(
        name="system_health",
        description="CPU, memory and disk usage",
        patterns=[
            "health",
            "[(system|pc|computer|machine)] health",
            "[(system|pc|computer|machine)] (stats|status|usage)",
            "how is my (pc|computer|system|machine) doing",
        ],
        handler=health,
        tier=1,
        offline=True,
    ))

    return registry
