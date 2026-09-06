"""
M.O.N.D.A.Y. — the capability menu, and the words that are refused outright.

One source of truth for what MONDAY says it can do. The app, `cli.py` and the
API all render `build_help_text()` rather than keeping a copy — the menu this
replaced advertised a `mondayvoice.mp3` voice clone that was abandoned and a
"Self-Evolution Plugin System" that does not exist, and it said so on only one
of the three surfaces.

Extracted from `core/planner.py` when the substring chain was removed: the
planner is a coordinator now, and a hundred lines of menu copy is not
coordination. `core.planner` re-exports every name here, so existing imports
keep working.
"""

from __future__ import annotations

# ── /help ────────────────────────────────────────────────────────────────────
# Matched exactly, never as a substring. The previous intercept tested
# `"help" in cmd_lower`, so "help me summarize sample.pdf" printed the menu
# instead of summarising the file.
#: Refused before anything else looks at the command. Substrings, deliberately:
#: a refusal should fire on a fragment, which is the opposite of what routing
#: needs. Kept at module level so `tests/` can assert the list rather than
#: rediscover it.
PROHIBITED_KEYWORDS = [
    "hack ", "exploit", "ddos", "malware", "format c:", "rm -rf /",
    "drop database", "wipe drive",
]


HELP_TRIGGERS = {
    "/help", "/?", "help", "help me", "?", "commands", "list commands",
    "capabilities", "features", "what can you do", "what can u do",
    "what can you perform", "what are your features", "show help", "menu",
}


def is_help_request(command: str) -> bool:
    """True only for a bare help request, not for a task that mentions help."""
    raw = (command or "").lower().strip()
    if raw in HELP_TRIGGERS:          # checked first so bare "?" and "/?" survive
        return True
    return raw.strip(".!?") in HELP_TRIGGERS


def build_help_text() -> str:
    """
    The capability list shown by /help.

    Deliberately describes only what the code actually does. Anything that needs
    setup is labelled rather than omitted or overstated — a help menu that
    promises features the system does not have is worse than no help menu.
    """
    from core.security import TIER_2_IMPLEMENTED

    # Lines are kept under 72 characters so the whole menu fits inside the CLI's
    # bordered panel on an 80-column terminal without re-wrapping, which would
    # break the two-column alignment.
    gated = ", ".join(sorted(TIER_2_IMPLEMENTED))
    return f"""🤖 M.O.N.D.A.Y. — what I can do

Type these in plain English. Every example below works as written.

Supported now
  • Read-only desktop and system tasks, file/document work, memory, live info,
    timers, clipboard/window queries, and the built-in help menu.
  • Irreversible tasks are blocked by the Tier-2 confirmation gate until you say
    yes in a separate turn.
  • The exact supported surface is the set of examples below; optional features
    are listed separately so a missing dependency is never mistaken for a working
    feature.

Optional / setup required
  • Email sending needs setup: SMTP_USER / SMTP_PASSWORD in .env.
  • Screen vision needs setup: a Gemini API key.
  • A less robotic voice needs setup: MONDAY_PIPER_VOICE set to a .onnx file.
  • MONDAY_TTS=off silences the backend entirely.

🖥️  APPS & SYSTEM
   open notepad             launch an app (web fallback)
   screenshot               capture the screen to data/staging
   health                   live CPU / RAM / disk
   battery                  charge level and power status
   set volume to 40         also: mute, volume
   my ip                    local network details
   what time is it          also: what is the date
   kill <process>           ⚠️ Tier 2 — I ask first

📁  FILES & DOCUMENTS
   organize <folder path>   sort a folder by file type
   summarize report.pdf     summarise a PDF or text file

🌐  WEB & KNOWLEDGE
   search <anything>        live web search, with sources
   research <topic>         multi-source synthesised report
   what is the capital of France     looked up, not guessed

🧠  MEMORY
   remember my prof is Dr. Gupta     store a fact
   recall prof              retrieve it later
   proactive                suggestions from 2.3 + 2.4

📧  COMMUNICATION
   send mail to a@b.com subject "Hi" body "Hello"
        ⚠️ Tier 2 — I draft it, show you, then ask. Reply 'send'
        to deliver or 'cancel' to keep it as a draft.
   message 9876543210 saying hi      opens the chat with it typed;
                                     you press Enter to send it.
                                     10 digits is fine, +91 assumed
   papa's number is 9876543210       saves a contact, then just say
                                     "message papa saying hi"
   schedule meeting tomorrow 3pm     add a calendar event
   notify me the build finished      desktop notification

📊  LIVE INFO
   latest news              top headlines, live
   technology news          or any topic you name
   ifci share price         a listed company, by name or ticker
   weather in Delhi · bitcoin price · where am i · iss location

🗣️  VOICE
   speak hello world        say it out loud, offline
   "Hey Monday, ..."        wake word — turn Live on first
   Live button / Ctrl+L     always-on listening
   Spacebar (in the app)    push-to-talk
   just talk over me        I stop speaking and listen

⏰  TIMERS & MEDIA
   set a timer for 10 minutes    also: remind me in 15 mins
   set an alarm for 7am          wake me up at 6:30
   what alarms do i have         cancel my timers
   next song · pause · previous  the media keys, for whatever
                                 app is already playing
   Timers ring only while I'm running — I'll tell you if one
   passed while I was closed.

🖱️  CLIPBOARD, WINDOWS & FILES
   what is on my clipboard       copy <text> to the clipboard
   what windows are open         switch to chrome
   find a file called notes      searches your folders, not C:
🗒️  DOCUMENTS & CONVERSATION
   what does report.pdf say about X   answers from inside a file
   search my documents for X          across a folder, with sources
   what did we talk about today       quotes past exchanges
   make a note of this conversation   saves a durable note

🔍  DIAGNOSTICS
   history                  the action audit log
   /help                    this menu

🔒  SAFETY — how approval works
   Reversible actions (Tier 1) run straight away and are logged.
   Irreversible ones (Tier 2) stop and ask first, with an ETA from
   the regression model: "Est. 12s — approve?". Nothing irreversible
   happens without your explicit yes.
   Currently gated: {gated}.

🎓  THE ML INSIDE (course components)
   2.1 intent classifier    routes your command
   2.2 ETA regression       supplies the "Est. 12s"
   2.3 memory clustering    groups what you save
   2.4 association rules    finds repeated habits
   2.5 RL router            learns which route works
   2.6 XAI                  explains 2.1 and 2.2

🧩  IF A LOCAL MODEL IS RUNNING (optional)
   Anything I don't recognise goes to a local LLM, which either
   picks one of the commands above or just answers. It runs on
   this machine — nothing you type is sent anywhere. Replies it
   writes are marked 💭, because a generated answer is not a
   checked one. Off entirely with MONDAY_LLM=off.

⚙️  OPTIONAL / SETUP REQUIRED
   Sending email needs SMTP_USER / SMTP_PASSWORD in .env
   (for Gmail, an App Password).
   Screen vision needs a Gemini API key.
   A less robotic voice needs Piper: point MONDAY_PIPER_VOICE
   at a .onnx voice file. Without it I speak through Windows
   SAPI5 — offline either way, just plainer. MONDAY_TTS=off
   silences the backend entirely."""
