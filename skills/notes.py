"""CODEC Skill: Voice & System Notes (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "notes"
SKILL_DESCRIPTION = "Save and recall notes cross-platform (Apple Notes on macOS, local JSON & Google Keep store elsewhere)"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = ["take a note", "save a note", "note that", "remember that",
                   "my notes", "show notes", "read notes", "what did i note", "list notes",
                   "new note", "add a note", "make a note", "write a note", "jot down",
                   "note this", "make note"]

import sys
import os
import json
import time
import subprocess
import re

_NOTES_FILE = os.path.expanduser("~/.codec/notes.json")

def _load_local_notes():
    if not os.path.exists(_NOTES_FILE):
        return []
    try:
        with open(_NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_local_notes(notes_list):
    os.makedirs(os.path.dirname(_NOTES_FILE), exist_ok=True)
    with open(_NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes_list, f, indent=2)

def _is_remote_transport() -> bool:
    return os.environ.get("CODEC_MCP_TRANSPORT", "stdio").lower() == "http"

def run(task, app="", ctx=""):
    low = task.lower()
    WRITE_VERBS = ("take a note", "save a note", "new note", "add a note",
                   "make a note", "write a note", "note that", "remember that",
                   "jot down", "note this", "make note", "with content",
                   "saying", "that says")
    READ_VERBS = ("list", "show", "read", "my notes", "open notes", "view notes",
                  "what notes", "recent notes", "see notes", "what did i note")
    is_write = any(w in low for w in WRITE_VERBS)
    is_read = "notes" in low and any(v in low for v in READ_VERBS)

    if is_read and not is_write:
        if sys.platform == "darwin":
            try:
                script = '''
tell application "Notes"
    set out to ""
    set noteList to notes
    set i to 1
    repeat with n in noteList
        if i > 20 then exit repeat
        set t to name of n
        set out to out & "[" & (i as string) & "] " & t & linefeed
        set i to i + 1
    end repeat
    return out
end tell
'''
                r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and r.stdout.strip():
                    return f"CODEC NOTES (macOS):\n{r.stdout.strip()}"
            except Exception:
                pass
        
        # Local JSON notes read
        local_notes = _load_local_notes()
        if not local_notes:
            return "No notes found."
        formatted = "\n".join([f"• [{n.get('date', '')}] {n.get('content', '')}" for n in local_notes[-15:]])
        return f"CODEC NOTES:\n{formatted}"

    # Extract note text
    note = task
    for pat in [r'with\s+content\s+["\']?(.+?)["\']?$',
                r'saying\s+["\']?(.+?)["\']?$',
                r'that\s+says\s+["\']?(.+?)["\']?$',
                r':\s*["\']?(.+?)["\']?$',
                r'["\'](.+?)["\']']:
        m = re.search(pat, task, re.IGNORECASE)
        if m:
            note = m.group(1).strip()
            break
    else:
        for remove in ["take a note of","take a note","save a note","save a new note",
                       "new note","add a note","make a note","write a note",
                       "note that","remember that","jot down","note this","make note",
                       "please","can you"]:
            pat = r'\b' + re.escape(remove) + r'\b'
            low = re.sub(pat, '', low, count=1)
        note = low.strip(" :,-").strip()

    if not note or len(note) < 1:
        return None

    # Save to macOS Notes if on macOS
    if sys.platform == "darwin":
        try:
            safe = note.replace('"', '\\"').replace("'", "")
            subprocess.run(["osascript", "-e", f'tell application "Notes" to make new note at folder "Notes" with properties {{body:"{safe}"}}'], capture_output=True, timeout=5)
        except Exception:
            pass

    # Save to local JSON store
    local_notes = _load_local_notes()
    local_notes.append({
        "content": note,
        "date": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    _save_local_notes(local_notes)
    return f"Saved note: \"{note}\""
