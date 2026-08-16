"""
M.O.N.D.A.Y. — tranche 5: the desktop, the diagnostics, and the tool registry.

The branches replaced here are the ones whose keywords were widest, and the
widest of all was this pair, ~90 lines apart in `_dispatch_to_agent`:

    if any(v in cmd_lower for v in ["screen", "chart", "looking at", "visual", ...]):
        return self.vision_agent.analyze_screen_context(command)
    ...
    elif "light" in cmd_lower or "plug" in cmd_lower or "iot" in cmd_lower:
        return self.tool_registry.execute_tool("toggle_smart_light", ...)

`"screen"` matched "take a screenshot", "screen recording", and every sentence
containing *on-screen*; `"light"` matched "flight", "delight", "highlight" and
"lightweight", so "i need to book a flight" reached the smart-home tool. Both
answered with total confidence about something they had not been asked.

`speak` and `history` are here for the opposite reason — they were correct, but
one of them was written twice (`cli.py` had its own copy of `history` and
`proactive`, so they worked in the terminal and answered "I'm not sure how to do
that yet" in the app). A skill is reachable from every surface by construction.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from core.contracts import AgentResult, SystemQuery
from core.skills import Skill, SkillRegistry


def register_system_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers the desktop, diagnostic and tool-registry skills."""

    # ── The screen ───────────────────────────────────────────────────────────
    def analyze_screen(_command: str = "", **_: Any) -> Dict[str, Any]:
        return planner.vision_agent.analyze_screen_context(_command)

    registry.register(Skill(
        name="analyze_screen",
        description="Describe what is on screen (needs a Gemini key)",
        patterns=[
            "[(what is|whats|what's)] on my screen",
            "[(what is|whats|what's)] [(on|in)] [the] screen",
            "(read|describe|analyse|analyze|look at) my screen",
            "(read|describe|analyse|analyze) [the] screen",
            "what am i looking at",
            "[(what does|read)] the error on my screen [say]",
            "what is written on [my] screen",
        ],
        handler=analyze_screen,
        tier=1,
        offline=True,
    ))

    # ── Folders ──────────────────────────────────────────────────────────────
    # The old branch read the folder with `re.search(r'organize\\s+([^\\s,"]+)')`
    # and fell back to `"."` — the current working directory, which for the app
    # is the repository root. "organize my files" would have sorted the source
    # tree into Documents/Images/Other subfolders. A missing target is now a
    # question, not a default.
    def organize_folder(path: str = "", **_: Any) -> Dict[str, Any]:
        target = path.strip().strip("\"'")
        if not target:
            return AgentResult.failed(
                "Which folder should I organise? Give me a path, e.g. "
                "organize C:\\Users\\me\\Downloads",
                error="NO_FOLDER",
            ).as_dict()
        return planner.computer_agent.organize_directory(target)

    registry.register(Skill(
        name="organize_folder",
        description="Sort a folder's files by type",
        patterns=[
            "(organize|organise|sort|tidy) {path}",
            "(organize|organise|sort|tidy) [the] (folder|directory|dir) {path}",
            "(organize|organise|sort|tidy) {path} by (type|file type|extension)",
        ],
        handler=organize_folder,
        tier=1,
        offline=True,
    ))

    def create_desktop_folder(_command: str = "", **_: Any) -> Dict[str, Any]:
        """The one generated-code path that is still routed to.

        `CoderAgent` supports three domains: `system_volume`, `desktop_folder`
        and `web_scraper`. The volume is now served directly by
        `ComputerAgent.set_system_volume`, which reports the PowerShell exit
        status instead of a generated script's `print`. `web_scraper` is
        deliberately **not** routed to at all: its template printed `[SUCCESS]`
        and exited 0 when the fetch raised, so the parent read a zero exit code
        and reported a scrape that never happened — a fabricated success
        laundered through a subprocess, where the result contract cannot see it
        (UPGRADE_PLAN §2.2). `web_search` and `research_topic` do that job and
        report their own HTTP status.

        So this is what remains, and it reaches code generation only from an
        explicit, patterned request — never from a low-confidence guess.
        """
        return planner.coder_agent.generate_and_execute_script(_command)

    registry.register(Skill(
        name="create_desktop_folder",
        description="Create a folder on the desktop",
        patterns=[
            "(create|make|add) [a] [new] (folder|directory) on [my] desktop",
            "(create|make|add) [a] [new] desktop (folder|directory)",
            "(create|make|add) [a] [new] (folder|directory) called {name} on [my] desktop",
        ],
        handler=create_desktop_folder,
        tier=1,
        offline=True,
        # The only skill that opts out of stage 3, and the reason is the
        # docstring above: it reaches `CoderAgent`, which writes Python and runs
        # it under `subprocess`. "A guess must not reach code execution"
        # (UPGRADE_PLAN §1.2) was the finding that removed the substring chain's
        # final `else`; a language model is a better guesser than that chain
        # was, but it is still guessing. Tier 1 is about reversibility, and this
        # exclusion is about what the implementation *does* — two different
        # questions, so it needs its own flag rather than a tier bump.
        llm_reachable=False,
    ))

    # ── Processes ────────────────────────────────────────────────────────────
    def list_processes(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.list_running_processes()

    registry.register(Skill(
        name="list_processes",
        description="What is running right now",
        patterns=[
            "(list|show) [(the|my)] [running] (processes|programs|apps|tasks)",
            "[(what is|whats|what's)] running",
            "running (processes|programs|apps)",
            "task manager",
        ],
        handler=list_processes,
        tier=1,
        offline=True,
    ))

    # ── Voice ────────────────────────────────────────────────────────────────
    # Anchored to the start of the command, and it always was — a bare `"say "`
    # substring also matches "what did I say about X", which belongs to memory.
    # The pattern makes the anchoring structural rather than a regex someone has
    # to remember to keep.
    def speak_text(phrase: str = "", **_: Any) -> Dict[str, Any]:
        return planner.voice_agent.speak(phrase.strip().strip("\"'") or "M.O.N.D.A.Y. online.")

    registry.register(Skill(
        name="speak_text",
        description="Say something out loud",
        patterns=[
            "(say|speak) {phrase}",
            "say out loud {phrase}",
            "(read|say) {phrase} out loud",
        ],
        handler=speak_text,
        tier=1,
        offline=True,
    ))

    # ── The audit log ────────────────────────────────────────────────────────
    def audit_history(**_: Any) -> Dict[str, Any]:
        from core.security import get_action_history

        entries = get_action_history(limit=10)
        if not entries:
            return AgentResult.ok(
                "The action audit log is empty.",
                evidence=SystemQuery(source="data/action_history.jsonl", detail="0 entries"),
                data={"intent": "audit_log", "entries": [], "speech": "The audit log is empty."},
            ).as_dict()
        lines = [
            f"  {e.get('timestamp','')[:19].replace('T',' ')}  "
            f"T{e.get('tier','?')}  {e.get('action','')}  →  "
            f"{str(e.get('target',''))[:40]}  [{e.get('status','')}]"
            for e in entries
        ]
        return AgentResult.ok(
            "🔍 Recent actions (newest last):\n" + "\n".join(lines),
            evidence=SystemQuery(
                source="data/action_history.jsonl", detail=f"{len(entries)} entries"
            ),
            data={"intent": "audit_log", "entries": entries,
                  "speech": f"The last {len(entries)} actions are on screen."},
        ).as_dict()

    registry.register(Skill(
        name="audit_history",
        description="The action audit log",
        patterns=[
            "history", "log", "audit", "audit log", "action history",
            "(show|list) [(me|my)] [(recent|last)] (actions|history)",
            "what have you done",
        ],
        handler=audit_history,
        tier=1,
        offline=True,
    ))

    # ── Proactive suggestions (components 2.3 + 2.4) ─────────────────────────
    def proactive(**_: Any) -> Dict[str, Any]:
        sug_mem = planner.memory_agent.get_proactive_suggestions()
        sug_hab = planner.habit_agent.detect_habits_and_suggest()
        mem = [s.get("prompt") for s in sug_mem.get("suggestions", []) if s.get("prompt")]
        hab = [h.get("prompt") for h in sug_hab.get("suggestions", []) if h.get("prompt")]
        parts = ["🧠 Memory topics (Component 2.3 — clustering):"]
        parts += [f"  • {m}" for m in mem] or ["  (nothing yet — save a few memories first)"]
        parts.append("\n⚡ Workflow habits (Component 2.4 — association mining):")
        parts += [f"  • {h}" for h in hab] or ["  (no repeated patterns detected yet)"]
        return AgentResult.ok(
            "\n".join(parts),
            evidence=SystemQuery(
                source="components 2.3 + 2.4",
                detail=f"{len(mem)} memory topics, {len(hab)} habits",
            ),
            data={
                "intent": "proactive_suggestions",
                "memory_suggestions": mem,
                "habit_suggestions": hab,
                "speech": f"{len(mem)} memory topics and {len(hab)} habits.",
            },
        ).as_dict()

    registry.register(Skill(
        name="proactive_suggestions",
        description="Suggestions from the clustering and association models",
        patterns=[
            "proactive", "suggestions", "proactive suggestions",
            "what should i do next",
            "(show|give) me suggestions",
        ],
        handler=proactive,
        tier=1,
        offline=True,
    ))

    # ── Meetings ─────────────────────────────────────────────────────────────
    # Both of these answer `NOT_IMPLEMENTED`, and that is the whole point of
    # keeping them routable. `start_meeting_recording` used to print "🎙️
    # Capturing meeting audio streams…" while capturing nothing — there is no
    # audio capture anywhere in this repo — so a user could leave it running
    # through an hour-long meeting, take no notes, and find afterwards that
    # there had never been anything to summarise. An honest refusal is only
    # useful if the command reaches it.
    def start_recording(**_: Any) -> Dict[str, Any]:
        return planner.audio_summarizer_agent.start_meeting_recording()

    registry.register(Skill(
        name="start_meeting_recording",
        description="Record a meeting (not implemented — says so)",
        patterns=[
            "(start|begin) (meeting|the meeting) recording",
            "(start|begin) recording [(the|this)] meeting",
            "record (the|this) meeting",
            "record meeting",
        ],
        handler=start_recording,
        tier=1,
        offline=True,
    ))

    def stop_recording(**_: Any) -> Dict[str, Any]:
        return planner.audio_summarizer_agent.stop_meeting_recording_and_summarize()

    registry.register(Skill(
        name="stop_meeting_recording",
        description="Stop recording and summarise (not implemented — says so)",
        patterns=[
            "(stop|end|finish) (meeting|the meeting) recording",
            "(stop|end|finish) recording [(the|this)] meeting",
            "(summarize|summarise) (the|this|my) meeting",
            "meeting notes",
        ],
        handler=stop_recording,
        tier=1,
        offline=True,
    ))

    # ── The inbox ────────────────────────────────────────────────────────────
    def read_latest_email(**_: Any) -> Dict[str, Any]:
        return planner.tool_registry.execute_tool("read_latest_email")

    registry.register(Skill(
        name="read_latest_email",
        description="Read the most recent inbox message (needs Gmail OAuth)",
        patterns=[
            "read [(my|the)] [(latest|last|newest)] email",
            "read [(my|the)] [(latest|last|newest)] (mail|inbox)",
            "check [(my|the)] (inbox|email|mail)",
            "[(do|have)] i (have|got) [any] [new] (email|emails|mail)",
            "any new (email|emails|mail)",
        ],
        handler=read_latest_email,
        tier=1,
        offline=False,
    ))

    # ── Data conversion ──────────────────────────────────────────────────────
    # The old branch defaulted a missing path to `"data/sample.csv"`, so a
    # command naming no file converted a different file and reported success.
    def convert_csv(path: str = "", **_: Any) -> Dict[str, Any]:
        target = path.strip().strip("\"'")
        if not target:
            return AgentResult.failed(
                "Which CSV should I convert? Give me the path.", error="NO_CSV"
            ).as_dict()
        return planner.tool_registry.execute_tool("convert_csv_to_json", csv_path=target)

    registry.register(Skill(
        name="convert_csv_to_json",
        description="Convert a CSV file to JSON",
        patterns=[
            "convert {path} to json",
            "convert [the] (csv|file) {path} to json",
            "turn {path} into json",
        ],
        handler=convert_csv,
        tier=1,
        offline=True,
    ))

    # ── Smart home ───────────────────────────────────────────────────────────
    # Routed on purpose, and it answers that it cannot. Deleting the route would
    # send "turn on the living room light" to the generic fallback, which says
    # "I'm not sure how to do that yet" — true, but it does not say *why*, and
    # "Pillar 5: IoT & Smart Home Automation" is listed in the PRD. The honest
    # version names the missing piece: there is no hub to talk to.
    def smart_light(device: str = "", state: str = "", **_: Any) -> Dict[str, Any]:
        return planner.tool_registry.execute_tool(
            "toggle_smart_light",
            device_name=(device.strip() or "the light"),
            state=(state.strip().lower() or "on"),
        )

    registry.register(Skill(
        name="toggle_smart_light",
        description="Switch a smart light (not implemented — says why)",
        patterns=[
            "turn (on|off) [(the|my)] {device} (light|lights|lamp|plug)",
            "turn [(the|my)] {device} (light|lights|lamp|plug) (on|off)",
            "turn (on|off) [(the|my)] (light|lights|lamp|plug)",
            "turn [(the|my)] (light|lights|lamp|plug) (on|off)",
            "(switch|toggle) [(the|my)] (light|lights|lamp|plug) (on|off)",
        ],
        handler=smart_light,
        tier=1,
        offline=True,
    ))

    # ── Calendar and notifications ───────────────────────────────────────────
    # `/help` advertises both of these. Neither was reachable: no branch in the
    # chain mentioned `schedule` or `notify`, so both fell through to the coder
    # agent and were answered "I'm not sure how to do that yet" — a help menu
    # promising something the router had no way to deliver.
    def schedule_event(title: str = "", when: str = "", **_: Any) -> Dict[str, Any]:
        name = title.strip().strip("\"'")
        moment = when.strip().strip("\"'")
        if not name:
            return AgentResult.failed(
                "What should I put in the calendar?", error="NO_EVENT_TITLE"
            ).as_dict()
        if not moment:
            # Recording an event with no time is worse than declining: it looks
            # scheduled and will never come up.
            return AgentResult.failed(
                f"When is '{name}'? Try: schedule {name} at tomorrow 3pm",
                error="NO_EVENT_TIME",
            ).as_dict()
        return planner.comms_agent.schedule_calendar_event(name, moment)

    registry.register(Skill(
        name="schedule_event",
        description="Add an event to the local calendar",
        patterns=[
            "(schedule|add|create|book) [(a|an)] [(meeting|event|appointment)] {title} (at|on|for) {when}",
            "(schedule|add|create|book) {title} (at|on|for) {when}",
            "put {title} in [my] calendar (at|on|for) {when}",
            "remind me about {title} (at|on) {when}",
        ],
        handler=schedule_event,
        tier=1,
        offline=True,
    ))

    def upcoming_events(**_: Any) -> Dict[str, Any]:
        return planner.comms_agent.get_upcoming_events()

    registry.register(Skill(
        name="upcoming_events",
        description="What is coming up in the calendar",
        patterns=[
            "[(what is|whats|what's)] [(on|in)] my calendar",
            "[(what are|show|list)] [my] [(upcoming|next)] (events|meetings|appointments)",
            "calendar",
            "[(do|have)] i have (anything|any meetings) [(today|tomorrow|coming up)]",
        ],
        handler=upcoming_events,
        tier=1,
        offline=True,
    ))

    def notify(text: str = "", **_: Any) -> Dict[str, Any]:
        body = text.strip().strip("\"'")
        if not body:
            return AgentResult.failed(
                "What should the notification say?", error="NO_NOTIFICATION_TEXT"
            ).as_dict()
        return planner.comms_agent.send_desktop_notification("M.O.N.D.A.Y.", body)

    registry.register(Skill(
        name="desktop_notification",
        description="Show a desktop notification",
        patterns=[
            "notify me {text}",
            "(show|send|pop) [me] [a] notification {text}",
            "(show|send|pop) [me] [a] notification saying {text}",
        ],
        handler=notify,
        tier=1,
        offline=True,
    ))
