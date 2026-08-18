"""
M.O.N.D.A.Y. — the migrated skills.

Tranches 1–3 live here: the offline utility commands, memory and identity, and
the browser surface. They moved first because they are what the demo leans on
and have the least to go wrong; the riskiest paths (email, WhatsApp) migrated
last, behind their existing tests, and are in `core/skills_comms.py`.

Each entry replaces a branch of the substring chain that used to be
`MasterPlanner._dispatch_to_agent`, and the comment on it records what that
branch got wrong, so the same mistake is not reintroduced by someone widening a
pattern later.

`build_builtin_registry` is the single entry point and assembles all six
tranches. The chain it replaced is gone — see `core/planner.py`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict

from agents.memory_agent import is_machine_written
from core.contracts import AgentResult, RecordStored, SystemQuery
from core.skills import Skill, SkillRegistry
from core.skills_comms import register_comms_skills
from core.skills_live import register_live_skills
from core.skills_system import register_system_skills


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
        read_only=True,
        description="The current clock time — not the date and not a calendar event",
        patterns=[
            "[(what|whats|what's)] [is] [the] time [is it]",
            "time",
            "current time",
            "tell me [the] time",
            "what time is it",
            # 51 of the `datetime_query` misses begin "what time is …".
            "[(what|whats|what's)] [is] [the] [(current|right)] time (now|right now|here|today)",
            "(tell|give|show) me [the] [(current|exact)] time",
            "(tell|give|show) me [(what|the)] time [(it is|is it)]",
            "[(do|would)] you (know|have) [the] time",
            "got the time",
            "the time",
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
        read_only=True,
        description="Today's date and the day of the week — the calendar day, not the clock time",
        patterns=[
            "[(what|whats|what's)] [is] [the] date [today]",
            "date",
            "todays date",
            "today's date",
            "what day is it",
            # 22 of the misses are "what day of the week is it" and its variants.
            "[(what|whats|what's)] [is] [the] day of the week [(it is|is it|today)]",
            "[(what|whats|what's)] [is] [the] [(current|today's|todays)] date [(right now|now)]",
            "what day (is it|is it today|of the week is it today)",
            "(tell|give|show) me [(the|today's|todays)] date",
            "(tell|give|show) me (what|the) day [(it is|is it|of the week)]",
            "what is the day today",
            "which day is [it] today",
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
        read_only=True,
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
            "[(set|change|put|turn|adjust)] [the] volume [to] {level:int}",
            "[(set|change|put|turn|adjust)] [the] volume [to] {level:int} percent",
            "[(set|change|put|turn|adjust)] [the] volume [to] {level:int}%",
            "volume {level:int}",
            # "Set the system volume to 50%" — the reported miss. The corpus
            # also has "speaker volume", "sound volume" and "audio volume", so
            # the qualifier is a slot-free alternation rather than one literal.
            "(set|change|put|turn|adjust) [the] (system|speaker|speakers|sound|audio|master|device) volume [to] {level:int}",
            "(set|change|put|turn|adjust) [the] (system|speaker|speakers|sound|audio|master|device) volume [to] {level:int} percent",
            "(set|change|put|turn|adjust) [the] (system|speaker|speakers|sound|audio|master|device) volume [to] {level:int}%",
            "(set|change|put|turn|adjust) [the] (sound|audio) [to] {level:int}",
            "(set|change|put|turn|adjust) [the] (sound|audio) [to] {level:int} percent",
            "(set|change|put|turn|adjust) [the] (sound|audio) [to] {level:int}%",
            "volume [to] {level:int} percent",
            "volume [to] {level:int}%",
        ],
        handler=set_volume,
        tier=1,
        offline=True,
    ))

    def mute(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.set_system_volume(0)

    registry.register(Skill(
        name="mute_volume",
        description="Silence the system volume completely — mute, quiet, no sound",
        patterns=[
            "mute",
            "mute [the] (volume|sound|audio|speakers|system|everything)",
            "silence [the] (volume|sound|audio|speakers|system|everything)",
            "(volume|sound|audio|speakers) off",
            "turn off [the] (volume|sound|audio|speakers)",
            "(be|stay) (quiet|silent)",
            "quiet",
            "silent",
            "silence",
            "shut up",
            "no sound",
        ],
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
            # Nobody says "turn the volume up" as often as "turn up the volume":
            # the corpus has the particle before the object almost every time.
            "(turn|put|bring|crank|pump) up [the] [(system|speaker|speakers|sound|audio|master)] (volume|sound|audio)",
            "(turn|put|bring|crank|pump) up [the] volume",
            "(turn|put) [the] [(system|speaker|speakers|master)] (volume|sound|audio) up",
            "(increase|raise|boost|up) [the] [(system|speaker|speakers|sound|audio|master)] (volume|sound|audio)",
            "(volume|sound|audio) up",
            "(volume|sound) louder",
            "(speak|talk) (up|louder)",
            "make it louder",
            "make [the] (volume|sound|audio) louder",
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
            "(turn|put|bring) down [the] [(system|speaker|speakers|sound|audio|master)] (volume|sound|audio)",
            "(turn|put|bring) down [the] volume",
            "(turn|put) [the] [(system|speaker|speakers|master)] (volume|sound|audio) down",
            "(decrease|lower|reduce|soften) [the] [(system|speaker|speakers|sound|audio|master)] (volume|sound|audio)",
            "(volume|sound|audio) down",
            "softer",
            "too loud",
            "(it is|its|it's|you are|youre|you're) too loud",
            "make it (quieter|softer)",
            "make [the] (volume|sound|audio) (quieter|softer|lower)",
        ],
        handler=volume_down,
        tier=1,
        offline=True,
    ))

    def read_volume(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.get_system_volume()

    registry.register(Skill(
        name="read_volume",
        read_only=True,
        description="Report the current volume",
        patterns=[
            "[(what is|whats|what's)] [the] [current] volume",
            "[(what is|whats|what's)] [the] [current] volume level",
            "how loud is it",
            "volume level",
            "check [the] volume",
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
        read_only=True,
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
            "{name} (phone|mobile|cell|whatsapp|contact) number is {phone}",
            # People say it without the "is": "save didi contact number
            # 9812345678". The typed `{phone:phone}` slot is what makes these
            # safe without one — without a type, "add rahul number two" would
            # match and try to save "two" as a phone number.
            "(save|remember|store|add|set) {name} number {phone:phone}",
            "(save|remember|store|add|set) {name} (phone|mobile|cell|whatsapp|contact) number {phone:phone}",
            "(save|remember|store|add|set) {name} number (as|is|=) {phone:phone}",
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
        read_only=True,
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
        read_only=True,
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
        description="Save a fact, a note, or an item on a list, to read back later",
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

    def recall(query: str = "", _command: str = "", **_: Any) -> Dict[str, Any]:
        # Falls back to the whole command because this skill is reachable from
        # stage 2, which supplies no slots — a `memory_query` the patterns did
        # not recognise is still best served by searching memory for what the
        # user typed, rather than by a web search for their own notes.
        return planner.memory_agent.recall(query.strip() or _command.strip())

    registry.register(Skill(
        name="recall_memory",
        read_only=True,
        description="Read back something saved earlier — a fact, a note, or what is on a saved list",
        patterns=[
            "recall {query}",
            "what did i say about {query}",
            "what do you (know|remember) about {query}",
            "(look up|lookup) {query} in [my] memory",
        ],
        handler=recall,
        # Stage 2. `memory_query` is one of the three families where a
        # classification alone is enough to pick a handler: reading memory is
        # reversible, needs no target, and has exactly one skill that serves it.
        intents=["memory_query"],
        runs_without_slots=True,
        tier=1,
        offline=True,
    ))

    # ── Documents ────────────────────────────────────────────────────────────
    # `"summarize" in cmd_lower or "pdf" in cmd_lower` then a regex for the path,
    # falling back to **README.md** when it found nothing — so "summarize this"
    # confidently summarised the project's own readme.
    # Words that are a gesture, not a filename. "summarize this" captured
    # "this" as a path; `summarize_document` treats an unreadable path as a raw
    # text snippet, so it summarised the four-letter string "this" and reported
    # "✓ Summarised text snippet (1 words → 5 key points)". A demonstrative is
    # the user pointing at something MONDAY cannot see, and the honest answer is
    # to ask which file — not to summarise the word.
    _DEICTIC = {"this", "that", "it", "these", "those", "the file", "the document"}

    def summarize(path: str = "", **_: Any) -> Dict[str, Any]:
        target = path.strip().strip("\"'")
        if not target or target.lower() in _DEICTIC:
            return AgentResult.failed(
                "Which file should I summarise? Give me a path, e.g. "
                "summarize notes.pdf",
                error="NO_DOCUMENT",
            ).as_dict()
        return planner.document_agent.summarize_document(target)

    registry.register(Skill(
        name="summarize_document",
        read_only=True,
        description="Summarise a document",
        patterns=[
            "(summarize|summarise) {path}",
            "(summarize|summarise) [the] (file|document|pdf) {path}",
            "give me a summary of {path}",
        ],
        handler=summarize,
        # Stage 2 with no slots asks which file, which is the right answer to a
        # `document_intel` command that named none. The legacy branch defaulted
        # the path to **README.md**, so "summarize this" confidently summarised
        # the project's own readme and reported success.
        intents=["document_intel"],
        runs_without_slots=True,
        tier=1,
        offline=True,
    ))

    # ── A confirmation with nothing to confirm ───────────────────────────────
    # "yes" answers a pending question. With nothing pending it reached the
    # coder agent, which replied 'I'm not sure how to do that yet: "yes". I can
    # currently open apps, search the web, …' — four lines of capability menu in
    # answer to one word. It happens constantly: the user says "yes" a second
    # time, or confirms something that already completed.
    #
    # `process_command` handles a genuine pending gate long before dispatch, so
    # anything reaching here has nothing to answer, by construction.
    def stray_confirmation(**_: Any) -> Dict[str, Any]:
        return AgentResult.ok(
            "Nothing's waiting on a yes or no — what would you like me to do?",
            evidence=SystemQuery(source="planner", detail="no pending clarification"),
            data={"intent": "stray_confirmation", "speech": "Nothing's pending."},
        ).as_dict()

    registry.register(Skill(
        name="stray_confirmation",
        read_only=True,
        description="A yes/no with no question outstanding",
        patterns=[
            "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead",
            "confirm", "do it", "no", "nope", "cancel", "nevermind", "never mind",
        ],
        handler=stray_confirmation,
        tier=1,
        offline=True,
    ))

    # ── Greetings ────────────────────────────────────────────────────────────
    # The only skill reached from the classifier as well as from patterns, and
    # the only family where that is safe without slots: a greeting has no
    # target, no side effect and nothing to get wrong.
    #
    # The legacy branch was `if intent == "chitchat" or cmd_lower in [...]`, and
    # it sat *above* the memory, document and communication branches — so any
    # command the classifier called chitchat was answered with a greeting no
    # matter what it said. "how do i summarise a pdf" scored chitchat at 0.31
    # and got "Hello! I am M.O.N.D.A.Y. …". Stage 1 now runs first, so a command
    # only reaches this if no pattern in the entire registry recognised it.
    def chitchat(**_: Any) -> Dict[str, Any]:
        return AgentResult.ok(
            "Hello! I am M.O.N.D.A.Y., your Modular Operational Neural Desktop "
            "Assistant. How can I help you today?",
            evidence=SystemQuery(source="planner", detail="chitchat"),
            data={"intent": "chitchat", "speech": "Hello! How can I help?"},
        ).as_dict()

    registry.register(Skill(
        name="chitchat",
        read_only=True,
        description="Greetings and small talk",
        patterns=[
            "hello", "hi", "hey", "yo", "hello monday", "hi monday", "hey monday",
            "good (morning|afternoon|evening|day)",
            "how are you", "how are you doing", "how's it going",
            "who are you", "what are you", "what is your name", "your name",
            "(thanks|thank you|cheers|ta)",
            "(bye|goodbye|see you|good night)",
        ],
        handler=chitchat,
        intents=["chitchat"],
        runs_without_slots=True,
        tier=1,
        offline=True,
    ))

    # ── Who the user is ──────────────────────────────────────────────────────
    # The worst-behaved path in the app, and the failure is worth writing down
    # in full because it was self-amplifying.
    #
    # The old branch fired on `"my name" in cmd_lower`, called
    # `memory_agent.recall("name")` and read `matches[0]["value"]` as the answer.
    # `recall` is a TF-IDF *similarity* search over every row, and
    # `auto_store_conversation_turn` writes one row per exchange whose value is
    # the whole turn serialised. So:
    #
    #   > whats my name
    #   ✓ Your name is Agent: MasterPlanner | User: is my name | Assistant:
    #     ✓ Your name is Agent: MasterPlanner | User: name is sambhag |
    #     Assistant: Hello! I am M.O.N.D.A.Y. … (OS User: sambh). (OS User: sambh).
    #
    # Every answer was stored as the next turn, so each retelling nested the
    # previous one and the reply grew without bound. Three things fix it:
    #
    # 1. Reading and writing are separate skills. `my name is X` is a statement
    #    and used to reach the *reader* (or, missing the branch entirely, the
    #    chitchat greeting — "name is sambhag" was answered with "Hello!").
    # 2. The name lives under one canonical key, so the reader never has to
    #    guess which row is the answer.
    # 3. Machine-written rows are refused outright (`is_machine_written`), the
    #    same guard the WhatsApp contact lookup already used.
    USER_NAME_KEY = "user_name"

    # A name is a name — not a sentence, not a transcript. This is what stops a
    # bad write becoming a permanent bad read.
    _NAME_OK = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,48}$")
    # Trailing verbs the parser used to swallow: "remember my name is sambhav
    # save" stored the name as "Sambhav save".
    _NAME_TAIL = re.compile(
        r"\s+(save|saved|please|now|ok|okay|thanks|thank you|for me|got it)$",
        re.IGNORECASE,
    )

    def _clean_name(raw: str) -> str:
        name = (raw or "").strip().strip("\"'").strip(" .,!?")
        previous = None
        while previous != name:
            previous = name
            name = _NAME_TAIL.sub("", name).strip()
        return name

    def set_user_name(name: str = "", **_: Any) -> Dict[str, Any]:
        cleaned = _clean_name(name)
        if not cleaned or not _NAME_OK.match(cleaned):
            return AgentResult.failed(
                "That doesn't look like a name — try \"my name is Sambhav\".",
                error="BAD_NAME",
            ).as_dict()
        res = planner.memory_agent.remember(
            USER_NAME_KEY, cleaned, topic="user_identity"
        )
        if not res.get("success"):
            return res
        return AgentResult.ok(
            f"✓ Got it — I'll call you {cleaned}.",
            evidence=RecordStored(store="memories.db", key=USER_NAME_KEY),
            data={"name": cleaned, "speech": f"Got it, I'll call you {cleaned}."},
        ).as_dict()

    registry.register(Skill(
        name="set_user_name",
        description="Tell MONDAY your name",
        patterns=[
            "[remember [that]] my name is {name}",
            "[remember [that]] my name's {name}",
            "remember [that] i am {name}",
            "call me {name}",
            "name is {name}",
            "i'm called {name}",
        ],
        handler=set_user_name,
        tier=1,
        offline=True,
    ))

    def get_user_name(**_: Any) -> Dict[str, Any]:
        os_user = str(planner.boot_context.get("username", "") or "").strip()

        stored = ""
        try:
            recalled = planner.memory_agent.recall(USER_NAME_KEY, limit=5)
        except Exception:
            recalled = {"matches": []}

        for match in recalled.get("matches", []):
            key = str(match.get("key", ""))
            value = str(match.get("value", "")).strip()
            # Only the canonical key, and only when it still holds a name. A
            # transcript would satisfy neither, which is the whole point.
            if is_machine_written(key) or key.lower() != USER_NAME_KEY:
                continue
            if _NAME_OK.match(value):
                stored = value
            break

        if stored:
            msg = f"✓ Your name is {stored}."
            if os_user and os_user.lower() != stored.lower():
                msg += f" (Signed in as {os_user}.)"
            return AgentResult.ok(
                msg,
                evidence=SystemQuery(source="memories.db", detail=USER_NAME_KEY),
                data={"name": stored, "os_user": os_user,
                      "speech": f"Your name is {stored}."},
            ).as_dict()

        if os_user:
            return AgentResult.ok(
                f"I don't have your name saved — you're signed in as {os_user}. "
                f"Tell me with \"my name is …\".",
                evidence=SystemQuery(source="boot_context", detail="os username"),
                data={"name": "", "os_user": os_user,
                      "speech": f"I don't have your name saved. You're signed in as {os_user}."},
            ).as_dict()

        return AgentResult.failed(
            "I don't know your name yet. Tell me with \"my name is …\".",
            error="NAME_UNKNOWN",
        ).as_dict()

    registry.register(Skill(
        name="get_user_name",
        read_only=True,
        description="What MONDAY has saved as your name",
        patterns=[
            "[(what is|whats|what's)] my name",
            "who am i",
            "tell me my name",
            "do you (know|remember) my name",
            "my username",
        ],
        handler=get_user_name,
        tier=1,
        offline=True,
    ))

    # ── Apps and websites ────────────────────────────────────────────────────
    # Third tranche: the browser surface. Every one of these was mis-served, and
    # the three failures are worth recording because they are three different
    # ways for a substring chain to be wrong.
    #
    # **"open gmail" opened an email composer.** The email branch fired on
    # `"gmail" in cmd_lower` and sat ~70 lines above the launcher, so the reply
    # was "✓ Recipient set to 'recipient@example.com'! What is the subject of the
    # email?" — a command to open a website silently became a half-built message
    # to a placeholder address. This is the exact collision `core/skills.py`
    # names in its header; it survived because the launcher could never be
    # reached to disagree.
    #
    # **"open youtube.com on my browser" was not understood at all.** The
    # launcher stripped the verb and gave up if more than three words were left,
    # so a URL plus a destination failed the count, fell through to `CoderAgent`
    # and came back "I'm not sure how to do that yet". Saying *where* to open
    # something was never a thing the system could hear.
    #
    # The word count was still doing real work — it is what stopped "open
    # whatsapp and message papa saying hi" being read as an application named
    # "whatsapp and message papa saying hi". It is kept, as the `:app` slot type
    # (`core/intent_patterns.py`), so it now bounds the target rather than the
    # whole command, and the browser suffix is matched instead of counted.
    #
    # "start" is deliberately not a verb here: `start {target:app}` would match
    # "start meeting recording", which belongs to the audio agent. The legacy
    # chain still serves "start <app>", and it runs after that intercept.
    _POLITENESS = re.compile(r"\s+(please|for me|now|thanks)$", re.IGNORECASE)

    def open_target(target: str = "", **_: Any) -> Dict[str, Any]:
        name = _POLITENESS.sub("", target.strip().strip("\"'")).strip()
        if not name:
            return AgentResult.failed(
                "What should I open?", error="NO_TARGET"
            ).as_dict()
        # WhatsApp keeps its own entry point: it opens the app *and* says how to
        # dictate a message from here. Launching it directly would work and would
        # drop that, so the more useful handler keeps the command.
        if name.lower().replace(" ", "") in {"whatsapp", "whatsappweb"}:
            return planner._handle_whatsapp(f"open {name}", f"open {name}".lower())
        return planner.browser_agent.open_app_or_website(name)

    registry.register(Skill(
        name="open_app_or_website",
        description="Open an application or a website",
        patterns=[
            "(open|launch|visit|go to|pull up|bring up) [(the|my)] {target:app}",
            # Naming the browser is the whole point of the second pattern: it
            # carries more literal text, so it wins the specificity ranking and
            # the suffix lands in the pattern instead of in the app name.
            "(open|launch|visit|go to|pull up|bring up) [(the|my)] {target:app} "
            "(on|in) [my] (browser|chrome|edge|firefox|web browser)",
            "open [(the|my)] (website|site|page|url|link) {target:app}",
        ],
        handler=open_target,
        tier=1,
        # Launching an app needs no network; the web fallback does.
        offline=True,
    ))

    # ── Web search ───────────────────────────────────────────────────────────
    # **"search web for YouTube" searched for "web for YouTube".** The legacy
    # branch stripped the verb with `^(search for|search|find|look up|google)\s+`
    # and passed whatever was left straight to DuckDuckGo, so every word the user
    # spent saying *where* to search became part of what was searched for. It
    # reported five results and looked like a success, which is why it went
    # unnoticed: the failure is in the query, not in the status.
    #
    # A slot cannot make that mistake — "search the web for {query}" carries more
    # literal text than "search {query}", so it wins the ranking and captures
    # only the query.
    #
    # One deliberate move: "search api for X" used to reach the public-API
    # directory (`"search api" in cmd_lower`) and now reaches the web search. The
    # directory is still served by its own phrasing ("public api for X"), and a
    # command that says "search" should search.
    def search_web(query: str = "", **_: Any) -> Dict[str, Any]:
        q = query.strip().strip("\"'").rstrip("?").strip()
        if not q:
            return AgentResult.failed(
                "What should I search for?", error="NO_QUERY"
            ).as_dict()
        return planner.browser_agent.web_search(q)

    registry.register(Skill(
        name="web_search",
        description="Search the web and cite the sources",
        patterns=[
            "search [the] (web|internet|net|online) for {query}",
            "search [the] (web|internet|net|online) {query}",
            "web search for {query}",
            "search for {query}",
            "search {query}",
            "(google|bing) {query}",
            "find {query} (online|on the web|on the internet)",
        ],
        handler=search_web,
        tier=1,
        offline=False,
    ))

    # `research quantum computing` reached `research_topic("research quantum
    # computing")` — the verb-stripping regex above listed every search verb
    # except this one, so the topic searched for included the word "research".
    def research(topic: str = "", **_: Any) -> Dict[str, Any]:
        t = topic.strip().strip("\"'").rstrip("?").strip()
        if not t:
            return AgentResult.failed(
                "What should I research?", error="NO_TOPIC"
            ).as_dict()
        return planner.browser_agent.research_topic(t)

    registry.register(Skill(
        name="research_topic",
        description="Multi-source research summary on a topic",
        patterns=[
            "research {topic}",
            "research (on|about|into) {topic}",
            "[(do|run|give me)] [a] deep research (on|about) {topic}",
        ],
        handler=research,
        tier=1,
        offline=False,
    ))

    # ── The remaining tranches ───────────────────────────────────────────────
    # Split by file rather than piled in here, in the order they were migrated,
    # because each tranche's header records what its branches got wrong.
    register_live_skills(registry, planner)      # tranche 4 — live data
    register_system_skills(registry, planner)    # tranche 5 — desktop, tools
    register_comms_skills(registry, planner)     # tranche 6 — email, WhatsApp

    return registry
