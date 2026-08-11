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

import re
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

    # ── Screenshot ───────────────────────────────────────────────────────────
    def screenshot(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.take_screenshot()

    registry.register(Skill(
        name="take_screenshot",
        description="Capture the screen",
        patterns=[
            "screenshot",
            "[(take|grab|capture)] [a] screenshot",
            "capture [the] screen",
        ],
        handler=screenshot,
        tier=1,
        offline=True,
    ))

    # ── Terminate a process — the first Tier-2 skill ─────────────────────────
    # Killing a process loses unsaved work, so it stops and asks in its own turn
    # (PRD §9). "close" alone is deliberately not a trigger: it is far too easy
    # to say by accident. The pattern also declines a bare "kill" with no target,
    # where the old regex produced an empty process name and a separate error.
    def terminate_process(process: str = "", **_: Any) -> Dict[str, Any]:
        name = re.sub(
            r"\s+(process|app|application|task)$", "", process.strip(), flags=re.IGNORECASE
        ).strip()
        if not name:
            return AgentResult.failed(
                "Which process should I terminate?", error="NO_PROCESS"
            ).as_dict()
        return planner.require_tier2_approval(
            action_name="terminate_process",
            target=name,
            executor="terminate_process",
            executor_kwargs={"process": name},
            original_command=f"kill {name}",
            task_type="desktop_automation",
            agent="computer",
            detail_lines=["Unsaved work in this process will be lost."],
        )

    registry.register(Skill(
        name="terminate_process",
        description="Force-close a running process (Tier 2 — asks first)",
        patterns=[
            "(kill|terminate|force close|end) {process}",
        ],
        handler=terminate_process,
        tier=2,
        offline=True,
    ))

    # ── Memory ───────────────────────────────────────────────────────────────
    # The old branch fired on `"remember" in cmd_lower or "recall" in cmd_lower
    # or "what did i" in cmd_lower`, then re-split the command with a second
    # regex to find the key and value. Patterns capture both in one step, and
    # "what did i" no longer swallows every sentence starting that way.
    def remember(key: str = "", value: str = "", fact: str = "", **_: Any) -> Dict[str, Any]:
        if key and value:
            return planner.memory_agent.remember(key.strip(), value.strip(), topic="user_notes")
        # "remember to call mum" — no key/value split, so store it whole rather
        # than inventing a key from the first word.
        text = fact.strip()
        if not text:
            return AgentResult.failed(
                "What should I remember?", error="NOTHING_TO_REMEMBER"
            ).as_dict()
        return planner.memory_agent.remember(text, text, topic="user_notes")

    # Contact numbers are a *more specific* reading of "remember X is Y", and they
    # must reach `_handle_save_contact_number`, not the generic memory store. Its
    # four validation guards exist because `normalise_phone` once stripped digits
    # out of arbitrary text and `recall` is a similarity search — together they
    # addressed a WhatsApp message to a number lifted from an unrelated saved
    # transcript (handoff.md §9.2). None of that is reimplemented here.
    #
    # Specificity ranking is what makes this work: "remember {name} number is
    # {phone}" carries more literal text than "remember {key} is {value}", so it
    # wins regardless of registration order.
    def save_contact_number(_command: str = "", **_: Any) -> Dict[str, Any]:
        saved = planner._handle_save_contact_number(_command)
        if saved is not None:
            return saved
        # The command looked like a contact but did not survive validation as
        # one — store it as an ordinary note rather than dropping it.
        return planner.memory_agent.remember(_command, _command, topic="user_notes")

    registry.register(Skill(
        name="save_contact_number",
        description="Save someone's phone number",
        patterns=[
            "remember [that] {name} number is {phone}",
            "[remember [that]] {name}'s number is {phone}",
            "{name} number is {phone}",
            "save {name} number as {phone}",
        ],
        handler=save_contact_number,
        tier=1,
        offline=True,
    ))

    # Asking *what* a number is, is not asking to send anything. "what is papa's
    # whatsapp number?" used to fall into the WhatsApp send flow, which parsed
    # the sentence for a recipient, took "what" as the name, and replied "I don't
    # have a phone number for 'what'. What's their number?" — offering to save a
    # contact called "what". Reading a contact is its own skill.
    def lookup_contact_number(name: str = "", **_: Any) -> Dict[str, Any]:
        who = planner._clean_contact_name(name)
        if not who:
            return AgentResult.failed(
                "Whose number are you after?", error="NO_CONTACT_NAME"
            ).as_dict()

        resolved = planner._resolve_phone_number(who)
        phone = resolved.get("phone")
        if not phone:
            return AgentResult.failed(
                f"I don't have a number saved for {who}. Tell me with "
                f"\"{who}'s number is 9876543210\".",
                error="CONTACT_NOT_FOUND",
            ).as_dict()

        return AgentResult.ok(
            f"{who}: {phone}",
            evidence=SystemQuery(source="memories.db", detail=f"contact '{who}'"),
            data={"name": who, "phone": phone, "source": resolved.get("source", "")},
        ).as_dict()

    registry.register(Skill(
        name="lookup_contact_number",
        description="Look up a saved phone number",
        patterns=[
            "[(what is|whats|what's)] {name}'s (whatsapp|phone|mobile|contact) number",
            "[(what is|whats|what's)] {name}'s number",
            "[(what is|whats|what's)] the number for {name}",
            "(do you have|find|get) {name}'s number",
        ],
        handler=lookup_contact_number,
        tier=1,
        offline=True,
    ))

    # "how many files are on my desktop" was classified `chitchat` at 0.25 and
    # fell through to a web search, which returned an SEO article titled "How to
    # Know How Many Files I Have on My PC". The machine can simply be asked.
    def desktop_contents(**_: Any) -> Dict[str, Any]:
        from pathlib import Path

        desktop = Path.home() / "Desktop"
        if not desktop.exists():
            return AgentResult.failed(
                f"I can't find a Desktop folder at {desktop}.",
                error="NO_DESKTOP",
            ).as_dict()

        entries = sorted(p for p in desktop.iterdir() if not p.name.startswith("."))
        files = [p for p in entries if p.is_file()]
        folders = [p for p in entries if p.is_dir()]

        names = ", ".join(p.name for p in entries[:8])
        if len(entries) > 8:
            names += f", +{len(entries) - 8} more"
        summary = f"{len(files)} files and {len(folders)} folders on your Desktop"
        return AgentResult.ok(
            f"{summary}." + (f" {names}" if names else ""),
            evidence=SystemQuery(source=str(desktop), detail=f"{len(entries)} entries"),
            data={
                "file_count": len(files),
                "folder_count": len(folders),
                "names": [p.name for p in entries],
                "speech": summary,
            },
        ).as_dict()

    registry.register(Skill(
        name="desktop_contents",
        description="What is on the desktop, and how much",
        patterns=[
            "how many (files|items|things) [are] [there] on [my] desktop",
            "[(what is|whats|what's)] on [my] desktop",
            "list [my] desktop",
            "(count|show) [my] desktop (files|items)",
        ],
        handler=desktop_contents,
        tier=1,
        offline=True,
    ))

    registry.register(Skill(
        name="remember_fact",
        description="Save something to memory",
        patterns=[
            # Every one of these keeps a mandatory verb. Making the verb optional
            # expands to a bare `{key} is {value}`, which matches any sentence
            # containing " is " — `IntentContainer.add_intent` now refuses it.
            "remember [that] {key} is {value}",
            "remember [that] {key} = {value}",
            "(save|store|note) [that] {key} is {value}",
            "remember [that] {fact}",
        ],
        handler=remember,
        # No `intents`: stage 2 passes no slots, and this needs a key and a
        # value. Declaring memory_query here routed "what is on my desktop" into
        # the memory writer.
        tier=1,
        offline=True,
    ))

    def recall(query: str = "", **_: Any) -> Dict[str, Any]:
        return planner.memory_agent.recall(query.strip() or "")

    registry.register(Skill(
        name="recall_memory",
        description="Look something up in memory",
        patterns=[
            "recall {query}",
            "what did i say about {query}",
            "what do you (know|remember) about {query}",
            "(look up|lookup) {query} in [my] memory",
        ],
        handler=recall,
        tier=1,
        offline=True,
    ))

    # ── Documents ────────────────────────────────────────────────────────────
    # `"summarize" in cmd_lower or "pdf" in cmd_lower` then a regex for the path,
    # falling back to **README.md** when it found nothing — so "summarize this"
    # confidently summarised the project's own readme.
    def summarize(path: str = "", **_: Any) -> Dict[str, Any]:
        target = path.strip().strip("\"'")
        if not target:
            return AgentResult.failed(
                "Which file should I summarise?", error="NO_DOCUMENT"
            ).as_dict()
        return planner.document_agent.summarize_document(target)

    registry.register(Skill(
        name="summarize_document",
        description="Summarise a document",
        patterns=[
            "(summarize|summarise) {path}",
            "(summarize|summarise) [the] (file|document|pdf) {path}",
            "give me a summary of {path}",
        ],
        handler=summarize,
        # No `intents`, same reason: without a path there is nothing to summarise.
        tier=1,
        offline=True,
    ))

    return registry
