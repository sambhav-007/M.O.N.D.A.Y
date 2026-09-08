"""
ROADMAP Phase 11, tranche 2 — clipboard, windows, and finding a file.

Unlike the timers tranche there is no coverage number to move here: MASSIVE is a
*voice assistant* corpus and nobody dictates "copy that to the clipboard" to a
smart speaker. The justification is that this is a **desktop** assistant, and
one that cannot say what is on the clipboard or which windows are open is
missing what its own surface makes obvious.

So what these tests protect is not coverage but the same property everything
else here protects: **nothing claims more than it did.**

* A clipboard write is read back before it is called a success, because `copy`
  fails silently on Windows when another process holds the clipboard open.
* A window focus that Windows refuses is a failure. It refuses foreground
  changes from background processes routinely, so a cheerful "switched!" would
  be a lie a good fraction of the time.
* A file search that gave up at its cap says so. "Nothing found" from a search
  that finished and one that stopped early are different answers.

The filesystem tests run against `tmp_path`, and the Windows API is stubbed —
a suite that opened real windows or read the developer's actual clipboard would
be doing to this machine what `tests/test_no_side_effects.py` exists to stop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

import core.skills_desktop as desktop
from core.planner import MasterPlanner
from ml.intent_classifier import predict_intent


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


def _run(planner, command) -> Dict[str, Any]:
    return planner.process_command(command)["execution_result"]


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


# ── Routing ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("command,skill", [
    ("what is on my clipboard", "read_clipboard"),
    ("read my clipboard", "read_clipboard"),
    ("what did i copy", "read_clipboard"),
    ("copy hello world to the clipboard", "copy_to_clipboard"),
    ("what windows are open", "list_windows"),
    ("list my open windows", "list_windows"),
    ("switch to chrome", "switch_window"),
    ("bring notepad to the front", "switch_window"),
    ("find a file called notes", "find_file"),
    ("where is my budget file", "find_file"),
])
def test_the_new_commands_reach_their_skills(planner, command, skill):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} routes nowhere"
    assert decision.skill.name == skill


def test_the_older_commands_are_undisturbed(planner):
    """These patterns are broad — "windows", "paste", "switch to X". The ones
    they could plausibly have stolen must still route where they did."""
    for command, skill in [
        ("what time is it", "tell_time"),
        ("open notepad", "open_app_or_website"),
        ("what is the capital of france", "answer_question"),
        ("what processes are running", "list_processes"),
        ("latest news", "latest_news"),
    ]:
        assert _route(planner, command).skill.name == skill, command


@pytest.mark.parametrize(
    "command,skill",
    [
        ("create a folder named abc", "create_desktop_folder"),
        ("rename that folder to abc", "rename_folder"),
        ("delete folder abc", "delete_folder"),
    ],
)
def test_folder_commands_have_explicit_skills(planner, command, skill):
    decision = _route(planner, command)
    assert decision.skill is not None
    assert decision.skill.name == skill


def test_delete_folder_requires_a_separate_confirmation(planner):
    result = _run(planner, "delete folder abc")
    assert result["awaiting_tier2_approval"] is True
    assert result["action_name"] == "delete_folder"
    assert "All files inside" in result["message"]
    planner.pending_clarification = None


# ── Clipboard ────────────────────────────────────────────────────────────────
class _FakeClipboard:
    """Stands in for pyperclip, so the suite never touches the real clipboard."""

    def __init__(self, contents: str = "", accept_writes: bool = True) -> None:
        self.contents = contents
        self.accept_writes = accept_writes

    def paste(self) -> str:
        return self.contents

    def copy(self, text: str) -> None:
        if self.accept_writes:
            self.contents = text


@pytest.fixture
def clipboard(monkeypatch):
    fake = _FakeClipboard()
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake)
    return fake


def test_reading_the_clipboard_reports_what_is_there(planner, clipboard):
    clipboard.contents = "some copied text"
    result = _run(planner, "what is on my clipboard")

    assert result["success"] is True
    assert "some copied text" in result["message"]
    assert result["evidence"]["kind"] == "system_query"


def test_an_empty_clipboard_says_empty(planner, clipboard):
    clipboard.contents = "   "
    result = _run(planner, "read my clipboard")
    assert result["success"] is True
    assert "empty" in result["message"].lower()


def test_a_long_clipboard_is_not_read_aloud_in_full(planner, clipboard):
    """`core/speech.py` would otherwise say every word of a pasted page."""
    clipboard.contents = "x" * 5000
    result = _run(planner, "what is on my clipboard")
    assert len(result["speech"]) < 100
    assert "5000 characters" in result["speech"]


def test_a_write_is_read_back_before_it_is_called_a_success(planner, monkeypatch):
    """`pyperclip.copy` fails silently on Windows when another process holds the
    clipboard open, so "copied" has to be checked rather than assumed."""
    refusing = _FakeClipboard(contents="unchanged", accept_writes=False)
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", refusing)

    result = _run(planner, "copy hello world to the clipboard")
    assert result["success"] is False
    assert result["error"] == "CLIPBOARD_NOT_CONFIRMED"


def test_a_confirmed_write_succeeds(planner, clipboard):
    result = _run(planner, "copy hello world to the clipboard")
    assert result["success"] is True
    assert clipboard.contents == "hello world"


# ── Windows ──────────────────────────────────────────────────────────────────
def test_listing_windows_reports_the_titles(planner, monkeypatch):
    monkeypatch.setattr(desktop, "list_windows", lambda: [
        {"handle": 1, "title": "Notepad"},
        {"handle": 2, "title": "Chrome — a page"},
    ])
    result = _run(planner, "what windows are open")

    assert result["success"] is True
    assert "Notepad" in result["message"]
    assert result["evidence"]["kind"] == "system_query"


def test_no_window_list_is_a_failure_not_an_empty_success(planner, monkeypatch):
    monkeypatch.setattr(desktop, "list_windows", lambda: [])
    result = _run(planner, "what windows are open")
    assert result["success"] is False
    assert result["error"] == "WINDOWS_UNAVAILABLE"


def test_switching_to_a_window_that_is_not_open_says_so(planner, monkeypatch):
    monkeypatch.setattr(desktop, "list_windows", lambda: [{"handle": 1, "title": "Notepad"}])
    result = _run(planner, "switch to chrome")

    assert result["success"] is False
    assert result["error"] == "WINDOW_NOT_FOUND"


def test_a_refused_focus_is_reported_as_refused(planner, monkeypatch):
    """Windows declines foreground changes from a background process routinely.
    Reporting "✓ switched" anyway would be wrong a good fraction of the time,
    and the user would be looking at the wrong window wondering."""
    monkeypatch.setattr(desktop, "list_windows", lambda: [{"handle": 1, "title": "Chrome"}])
    monkeypatch.setattr(desktop, "focus_window", lambda handle: False)

    result = _run(planner, "switch to chrome")
    assert result["success"] is False
    assert result["error"] == "WINDOW_FOCUS_REFUSED"


def test_an_accepted_focus_succeeds(planner, monkeypatch):
    monkeypatch.setattr(desktop, "list_windows", lambda: [{"handle": 7, "title": "Chrome"}])
    monkeypatch.setattr(desktop, "focus_window", lambda handle: handle == 7)

    result = _run(planner, "switch to chrome")
    assert result["success"] is True
    assert result["evidence"]["kind"] == "system_query"


# ── Finding a file ───────────────────────────────────────────────────────────
def test_a_search_finds_a_file_by_name_fragment(tmp_path, monkeypatch):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "budget_2026.xlsx").write_text("x", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(desktop, "_search_roots", lambda: [tmp_path])
    result = desktop.find_files("budget")

    assert [p.name for p in result["matches"]] == ["budget_2026.xlsx"]
    assert result["capped"] is False


def test_a_search_skips_the_folders_that_are_never_the_answer(tmp_path, monkeypatch):
    """`node_modules` and friends are expensive and never what was meant."""
    junk = tmp_path / "node_modules" / "deep"
    junk.mkdir(parents=True)
    (junk / "budget.js").write_text("x", encoding="utf-8")

    monkeypatch.setattr(desktop, "_search_roots", lambda: [tmp_path])
    assert desktop.find_files("budget")["matches"] == []


def test_a_search_stops_at_its_cap_and_admits_it(tmp_path, monkeypatch):
    for n in range(30):
        (tmp_path / f"file_{n}.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(desktop, "_search_roots", lambda: [tmp_path])
    monkeypatch.setattr(desktop, "MAX_SCANNED", 5)
    result = desktop.find_files("nothing_matches_this")

    assert result["capped"] is True
    assert result["matches"] == []


def test_an_unreadable_folder_does_not_stop_the_search(tmp_path, monkeypatch):
    """A permission error on one folder must not lose the whole search."""
    class _Exploding(type(tmp_path)):
        pass

    (tmp_path / "readable").mkdir()
    (tmp_path / "readable" / "target.txt").write_text("x", encoding="utf-8")

    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr(desktop, "_search_roots", lambda: [missing, tmp_path])

    assert [p.name for p in desktop.find_files("target")["matches"]] == ["target.txt"]


def test_nothing_found_names_where_it_looked(planner, monkeypatch, tmp_path):
    monkeypatch.setattr(desktop, "_search_roots", lambda: [tmp_path])
    result = _run(planner, "find a file called zzznotexistzzz")

    assert result["success"] is False
    assert result["error"] == "FILE_NOT_FOUND"
    assert "entries" in result["message"]
    assert result["roots"], "the roots searched must be reported, not described"


def test_asking_to_find_nothing_asks_rather_than_searching(planner):
    result = _run(planner, "find a file called")
    assert result["success"] is False


def test_the_new_skills_declare_themselves_honestly(planner):
    """`find_file` and `read_clipboard` read; the other three act. Getting this
    wrong would send a read through the stage-3 confirmation gate, or worse,
    let an acting skill run from a guess without one."""
    registry = planner.router.registry
    for name in ("read_clipboard", "list_windows", "find_file"):
        assert registry.get(name).read_only is True, name
    for name in ("copy_to_clipboard", "switch_window"):
        assert registry.get(name).read_only is False, name
    for name in ("read_clipboard", "copy_to_clipboard", "list_windows",
                 "switch_window", "find_file"):
        assert registry.get(name).offline is True, name
        assert registry.get(name).tier == 1, name
