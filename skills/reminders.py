"""CODEC Skill: Reminders (add + list, Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "reminders"
SKILL_DESCRIPTION = "Add or list reminders cross-platform (Apple Reminders on macOS, local JSON & Google Tasks store elsewhere)"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = [
    "add reminder", "set reminder", "remind me to", "add to reminders",
    "new reminder", "create reminder", "reminder to",
    "list reminders", "show reminders", "my reminders", "read reminders",
    "what reminders", "current reminders", "list current reminders",
    "outstanding reminders", "pending reminders",
]

import sys
import os
import json
import time
import subprocess
import re

_REMINDERS_FILE = os.path.expanduser("~/.codec/reminders.json")

def _load_local_reminders():
    if not os.path.exists(_REMINDERS_FILE):
        return []
    try:
        with open(_REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_local_reminders(rem_list):
    os.makedirs(os.path.dirname(_REMINDERS_FILE), exist_ok=True)
    with open(_REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(rem_list, f, indent=2)

def _is_read_intent(low: str) -> bool:
    READ_KEYS = ("list", "show", "my reminders", "read reminders", "what reminders",
                 "current reminders", "outstanding", "pending")
    WRITE_KEYS = ("add reminder", "set reminder", "remind me to", "add to reminders",
                  "new reminder", "create reminder", "reminder to")
    if any(w in low for w in WRITE_KEYS):
        return False
    return any(k in low for k in READ_KEYS)

def _list_reminders(limit: int = 20) -> str:
    if sys.platform == "darwin":
        script = '''
        tell application "Reminders"
            set output to ""
            set theLists to (name of lists)
            repeat with listName in theLists
                set theList to list listName
                set openRems to (name of reminders of theList whose completed is false)
                repeat with r in openRems
                    set output to output & listName & ": " & r & linefeed
                end repeat
            end repeat
            return output
        end tell
        '''
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                lines = [l for l in r.stdout.strip().splitlines() if l.strip()][:limit]
                return "Open reminders (macOS):\n" + "\n".join(f"  • {l}" for l in lines)
        except Exception:
            pass

    # Local JSON store fallback
    rems = _load_local_reminders()
    open_rems = [r for r in rems if not r.get("completed", False)]
    if not open_rems:
        return "No open reminders."
    return "Open reminders:\n" + "\n".join([f"  • {r.get('name', '')} (added {r.get('date', '')})" for r in open_rems[-limit:]])

def run(task, app="", ctx=""):
    low = (task or "").lower()

    if _is_read_intent(low):
        return _list_reminders()

    reminder = task
    for remove in ["add reminder", "set reminder", "remind me to", "add to reminders",
                   "new reminder", "create reminder", "reminder to", "please", "can you"]:
        reminder = re.sub(r'\b' + re.escape(remove) + r'\b', '', reminder, flags=re.IGNORECASE)
    reminder = reminder.strip().strip(":").strip()
    if not reminder or len(reminder) < 3:
        return None

    if sys.platform == "darwin":
        try:
            safe = reminder.replace('"', '\\"').replace("'", "")
            subprocess.run(["osascript", "-e", f'tell application "Reminders" to make new reminder in default list with properties {{name:"{safe}"}}'], capture_output=True, text=True, timeout=10)
        except Exception:
            pass

    rems = _load_local_reminders()
    rems.append({
        "name": reminder,
        "completed": False,
        "date": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    _save_local_reminders(rems)
    return f"Reminder added: {reminder}"
