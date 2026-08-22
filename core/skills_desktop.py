"""
M.O.N.D.A.Y. — tranche 8: the clipboard, windows, and finding a file.

ROADMAP Phase 11, tranche 2. None of these appear in MASSIVE — it is a *voice
assistant* corpus and nobody dictates "copy that to the clipboard" to a smart
speaker — so unlike the timers tranche there is no coverage number to move here.
The justification is different and is worth stating rather than assuming: this
is a **desktop** assistant, and a desktop assistant that cannot say what is on
the clipboard or which windows are open is missing the things its own surface
makes obvious.

Every one of these is real, offline, and dependency-light: `pyperclip` for the
clipboard (already a dependency), `ctypes` against `user32` for windows, and
`pathlib` for the file search. Nothing here shells out.

What each refuses to claim
--------------------------
* **Finding a file** searches a bounded set of the user's own folders, breadth
  first, and stops at a cap. It reports how many it looked at, because "no
  results" from a search that gave up early is a different answer from "no
  results" from a search that finished.
* **Focusing a window** reports `KeypressSent`-strength evidence at most: the
  API was called and returned. Whether the window came to the front is up to
  the shell, and Windows refuses foreground changes from a background process
  often enough that claiming it would be a lie some of the time.
* **The clipboard** is read and written exactly; there is nothing to hedge.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from core.contracts import AgentResult, SystemQuery
from core.skills import Skill, SkillRegistry

#: Where a file search looks. The user's own folders, not the whole disk: a
#: recursive walk of C:\ takes minutes, and an assistant that hangs for minutes
#: on "find my notes" is worse than one that says it looked in the obvious
#: places and did not find it.
def _search_roots() -> List[Path]:
    """The folders a search covers, nearest-first.

    The working directory comes first because it is where MONDAY was started
    from and therefore what "my notes" most often means — `find a file called
    handoff` returned "not found" without it, while handoff.md sat one folder
    away. Home comes last: it is the widest and the slowest.
    """
    home = Path.home()
    candidates = [
        Path.cwd(),
        home / "Desktop", home / "Documents", home / "Downloads",
        home / "Pictures", home / "Music", home / "Videos", home,
    ]
    seen: List[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in seen:
            seen.append(resolved)
    return seen

#: A hard cap on how many entries a search will look at. Reported when hit, so
#: "nothing found" never silently means "gave up".
MAX_SCANNED = 40000

#: Folders that are never the answer and are expensive to walk.
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "AppData",
    "site-packages", ".cache", "$RECYCLE.BIN", "System Volume Information",
}


def find_files(needle: str, limit: int = 10) -> Dict[str, Any]:
    """Breadth-first search of the user's folders for a name fragment."""
    needle = (needle or "").strip().strip("\"'").lower()
    if not needle:
        return {"matches": [], "scanned": 0, "capped": False}

    matches: List[Path] = []
    scanned = 0
    queue: List[Path] = _search_roots()

    while queue and len(matches) < limit and scanned < MAX_SCANNED:
        directory = queue.pop(0)
        try:
            entries = list(directory.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            scanned += 1
            if scanned >= MAX_SCANNED:
                break
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                if entry.name not in _SKIP_DIRS and not entry.name.startswith("."):
                    queue.append(entry)
                continue
            if needle in entry.name.lower():
                matches.append(entry)
                if len(matches) >= limit:
                    break

    return {
        "matches": matches,
        "scanned": scanned,
        "capped": scanned >= MAX_SCANNED,
    }


def list_windows() -> List[Dict[str, Any]]:
    """Visible top-level windows with a title. Empty off Windows."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # noqa: BLE001
        return []

    user32 = ctypes.windll.user32
    found: List[Dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _collect(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title:
            found.append({"handle": int(hwnd), "title": title})
        return True

    try:
        user32.EnumWindows(_collect, 0)
    except Exception:  # noqa: BLE001
        return []
    return found


def focus_window(handle: int) -> bool:
    """Asks the shell to bring a window forward. False if it refused."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, 9)          # SW_RESTORE
        return bool(user32.SetForegroundWindow(handle))
    except Exception:  # noqa: BLE001
        return False


def register_desktop_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers clipboard, window and file-finding skills."""

    # ── Clipboard ────────────────────────────────────────────────────────────
    def read_clipboard(**_: Any) -> Dict[str, Any]:
        try:
            import pyperclip

            text = pyperclip.paste()
        except Exception as exc:  # noqa: BLE001
            return AgentResult.failed(
                f"I couldn't read the clipboard: {exc}",
                error="CLIPBOARD_UNAVAILABLE",
            ).as_dict()

        if not (text or "").strip():
            return AgentResult.ok(
                "The clipboard is empty.",
                evidence=SystemQuery(source="clipboard", detail="0 characters"),
                data={"text": "", "speech": "The clipboard is empty."},
            ).as_dict()

        shown = text if len(text) <= 500 else text[:500] + f"… (+{len(text) - 500} more)"
        return AgentResult.ok(
            f"📋 Clipboard ({len(text)} characters):\n{shown}",
            evidence=SystemQuery(source="clipboard", detail=f"{len(text)} characters"),
            # Not spoken in full: a clipboard can hold a page of text, and
            # `core/speech.py` would read every word of it out loud.
            data={"text": text, "speech": f"{len(text)} characters on the clipboard."},
        ).as_dict()

    registry.register(Skill(
        name="read_clipboard",
        read_only=True,
        description="Read what is currently on the clipboard",
        patterns=[
            "[(what is|whats|what's)] [(on|in)] [(the|my)] clipboard",
            "read [(the|my)] clipboard",
            "(show|tell) me [(the|my)] clipboard",
            "clipboard",
            "paste",
            "what did i copy",
        ],
        handler=read_clipboard,
        tier=1,
        offline=True,
    ))

    def copy_to_clipboard(text: str = "", **_: Any) -> Dict[str, Any]:
        text = (text or "").strip().strip("\"'")
        if not text:
            return AgentResult.failed(
                "What should I copy? Try 'copy hello world to the clipboard'.",
                error="CLIPBOARD_NOTHING_TO_COPY",
            ).as_dict()
        try:
            import pyperclip

            pyperclip.copy(text)
            # Read it back: `copy` on Windows can fail silently when another
            # process holds the clipboard open, and "I copied it" is checkable.
            confirmed = pyperclip.paste() == text
        except Exception as exc:  # noqa: BLE001
            return AgentResult.failed(
                f"I couldn't write to the clipboard: {exc}",
                error="CLIPBOARD_UNAVAILABLE",
            ).as_dict()

        if not confirmed:
            return AgentResult.failed(
                "I wrote to the clipboard but it did not read back — something "
                "else may be holding it open.",
                error="CLIPBOARD_NOT_CONFIRMED",
            ).as_dict()

        return AgentResult.ok(
            f"✓ Copied {len(text)} characters to the clipboard.",
            evidence=SystemQuery(source="clipboard", detail=f"wrote and verified {len(text)} characters"),
            data={"text": text, "speech": "Copied."},
        ).as_dict()

    registry.register(Skill(
        name="copy_to_clipboard",
        read_only=False,
        description="Put a given piece of text on the clipboard",
        patterns=[
            "copy {text} to [(the|my)] clipboard",
            "copy to [(the|my)] clipboard {text}",
            "put {text} (on|in) [(the|my)] clipboard",
        ],
        handler=copy_to_clipboard,
        tier=1,
        offline=True,
    ))

    # ── Windows ──────────────────────────────────────────────────────────────
    def show_windows(**_: Any) -> Dict[str, Any]:
        windows = list_windows()
        if not windows:
            return AgentResult.failed(
                "I couldn't read the window list on this platform.",
                error="WINDOWS_UNAVAILABLE",
                data={"platform": sys.platform},
            ).as_dict()
        shown = windows[:15]
        lines = [f"  • {w['title'][:70]}" for w in shown]
        more = f"\n  … and {len(windows) - len(shown)} more" if len(windows) > len(shown) else ""
        return AgentResult.ok(
            f"🪟 {len(windows)} open windows:\n" + "\n".join(lines) + more,
            evidence=SystemQuery(source="user32.EnumWindows", detail=f"{len(windows)} visible"),
            data={
                "windows": [w["title"] for w in windows],
                "speech": f"{len(windows)} windows open.",
            },
        ).as_dict()

    registry.register(Skill(
        name="list_windows",
        read_only=True,
        description="What application windows are open — not running processes",
        patterns=[
            "[(what|which)] windows [(are open|do i have open|are there)]",
            "list [(my|the)] [open] windows",
            "(show|tell) me [(my|the)] [open] windows",
            "windows",
            "[(what|whats|what's)] open",
            "[(what|whats|what's)] [(do i have)] open right now",
        ],
        handler=show_windows,
        tier=1,
        offline=True,
    ))

    def switch_to(target: str = "", **_: Any) -> Dict[str, Any]:
        target = (target or "").strip().strip("\"'").lower()
        if not target:
            return AgentResult.failed(
                "Switch to what? Try 'switch to chrome'.",
                error="NO_WINDOW_NAMED",
            ).as_dict()

        windows = list_windows()
        matches = [w for w in windows if target in w["title"].lower()]
        if not matches:
            return AgentResult.failed(
                f"No open window matches '{target}'.",
                error="WINDOW_NOT_FOUND",
                data={"target": target, "open": [w["title"] for w in windows][:10]},
            ).as_dict()

        window = matches[0]
        if not focus_window(window["handle"]):
            # Windows refuses foreground changes from a background process often
            # enough that claiming success here would be a lie some of the time.
            return AgentResult.failed(
                f"I asked for '{window['title']}' to come forward and Windows "
                f"refused — it does that when the request comes from a "
                f"background process. Click it, or try again after clicking me.",
                error="WINDOW_FOCUS_REFUSED",
                data={"target": window["title"]},
            ).as_dict()

        return AgentResult.ok(
            f"✓ Switched to {window['title'][:70]}.",
            evidence=SystemQuery(
                source="user32.SetForegroundWindow",
                detail=f"handle {window['handle']} returned true",
            ),
            data={"target": window["title"], "speech": "Switched."},
        ).as_dict()

    registry.register(Skill(
        name="switch_window",
        read_only=False,
        description="Bring an already-open window to the front by name — it does not launch anything",
        patterns=[
            "switch to {target}",
            "(focus|activate) [(the)] {target} window",
            "bring {target} to the front",
            "go to [(the)] {target} window",
            "show me [(the)] {target} window",
        ],
        handler=switch_to,
        tier=1,
        offline=True,
    ))

    # ── Finding a file ───────────────────────────────────────────────────────
    def find_file(name: str = "", **_: Any) -> Dict[str, Any]:
        name = (name or "").strip().strip("\"'")
        if not name:
            return AgentResult.failed(
                "What am I looking for? Try 'find a file called notes'.",
                error="FIND_NO_NAME",
            ).as_dict()

        result = find_files(name)
        matches: List[Path] = result["matches"]
        scanned = result["scanned"]

        if not matches:
            # "Nothing found" from a search that gave up early is a different
            # answer from one that finished, and the user needs to know which.
            gave_up = " (I stopped at the cap, so there may be more)" if result["capped"] else ""
            # The roots are named from the list that was actually walked rather
            # than from a sentence written once and left behind.
            where = ", ".join(root.name or str(root) for root in _search_roots()[:5])
            return AgentResult.failed(
                f"No file matching '{name}' — I looked at {scanned:,} entries "
                f"under {where}{gave_up}.",
                error="FILE_NOT_FOUND",
                data={"name": name, "scanned": scanned,
                      "roots": [str(r) for r in _search_roots()]},
            ).as_dict()

        lines = []
        for path in matches:
            try:
                size = f"{path.stat().st_size / 1024:,.0f} KB"
            except OSError:
                size = "?"
            lines.append(f"  • {path}  ({size})")

        return AgentResult.ok(
            f"🔎 {len(matches)} match(es) for '{name}':\n" + "\n".join(lines),
            evidence=SystemQuery(
                source="filesystem walk",
                detail=f"{scanned:,} entries scanned, {len(matches)} matched",
            ),
            data={
                "name": name,
                "paths": [str(p) for p in matches],
                "scanned": scanned,
                "speech": f"{len(matches)} matches. The first is {matches[0].name}.",
            },
        ).as_dict()

    registry.register(Skill(
        name="find_file",
        read_only=True,
        description="Find a file by name in the user's own folders — it searches, it does not open or delete",
        patterns=[
            "find [(a|the)] file [(called|named)] {name}",
            "find [(a|the)] (document|doc|pdf) [(called|named)] {name}",
            "(where is|wheres|where's) [(my|the)] file [(called|named)] {name}",
            "(where is|wheres|where's) [(my|the)] {name} file",
            "search [(for)] [(a|the)] file [(called|named)] {name}",
            "look for [(a|the)] file [(called|named)] {name}",
            "locate [(the)] file {name}",
        ],
        handler=find_file,
        tier=1,
        offline=True,
    ))
