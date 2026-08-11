"""
The audit log — append-only JSON Lines (CLO01 evidence).

`log_action` used to read the whole log, append one entry and write it all back,
on every action. That is O(file) per call against a file that only ever grows;
by 2026-08-10 `data/action_history.json` held 19,837 entries / 6.5 MB and the
cost was visible in everything the assistant did.

These tests pin the properties the format change is *for*: constant-cost writes,
no cross-writer loss, damage confined to a line, and old history still readable.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

import core.security as security


@pytest.fixture
def log(tmp_path, monkeypatch):
    """A fresh log per test, isolated from the session-wide one in conftest."""
    path = tmp_path / "action_history.jsonl"
    legacy = tmp_path / "action_history.json"
    monkeypatch.setattr(security, "ACTION_LOG_PATH", path)
    monkeypatch.setattr(security, "LEGACY_ACTION_LOG_PATH", legacy)
    return path


def _log(n=1, action="test_action"):
    for i in range(n):
        security.log_action(action, f"target_{i}", 1, "success", "TestAgent")


# ── Format ───────────────────────────────────────────────────────────────────
def test_each_action_is_one_line(log):
    _log(3)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        assert json.loads(line)["action"] == "test_action"


def test_a_record_never_contains_a_raw_newline(log):
    """A newline inside a record would split it across two lines, breaking both."""
    security.log_action("multi\nline", "tar\nget", 1, "success", "A", {"note": "a\nb"})
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_writes_do_not_get_slower_as_the_log_grows(log):
    """
    The whole point. Under the old read-modify-write, the second batch below
    would cost several times the first; appending makes them comparable.
    """
    _log(200)
    start = time.perf_counter()
    _log(200)
    first_extra = time.perf_counter() - start

    _log(2000)
    start = time.perf_counter()
    _log(200)
    second_extra = time.perf_counter() - start

    assert second_extra < first_extra * 5 + 0.5, (
        f"200 writes cost {first_extra:.3f}s at 400 entries and "
        f"{second_extra:.3f}s at 2400 — the cost is still growing with the log"
    )


# ── Durability ───────────────────────────────────────────────────────────────
def test_concurrent_threads_lose_nothing(log):
    """The property the lock already gave; it must survive the format change."""
    def worker(n):
        for i in range(n):
            security.log_action(f"thread_{threading.get_ident()}", str(i), 1, "success", "T")

    threads = [threading.Thread(target=worker, args=(60,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 480


def test_a_corrupt_line_does_not_destroy_the_log(log):
    """
    Previously one bad byte made the entire JSON array unparseable, and the
    recovery path moved the whole file aside. Now the damage is one record.
    """
    _log(2, action="before")
    with open(log, "a", encoding="utf-8") as f:
        f.write("{this is not json at all\n")
    _log(2, action="after")

    history = security.get_action_history(limit=50)
    actions = [h["action"] for h in history]
    assert actions.count("before") == 2
    assert actions.count("after") == 2


def test_blank_lines_are_tolerated(log):
    _log(1)
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n\n")
    _log(1)
    assert len(security.get_action_history(limit=50)) == 2


# ── Reading ──────────────────────────────────────────────────────────────────
def test_history_returns_the_most_recent_last(log):
    for i in range(10):
        security.log_action(f"action_{i}", "t", 1, "success", "A")
    recent = security.get_action_history(limit=3)
    assert [h["action"] for h in recent] == ["action_7", "action_8", "action_9"]


def test_missing_log_is_not_an_error(log):
    assert security.get_action_history(limit=10) == []


def test_legacy_array_history_is_still_readable(log, tmp_path):
    """
    The 6.5 MB array file predating the change must not become unreadable — it
    is the audit trail for everything the project did before 2026-08-10.
    """
    legacy = tmp_path / "action_history.json"
    legacy.write_text(
        json.dumps([
            {"timestamp": "2026-08-01T10:00:00", "action": "old_one", "target": "t",
             "tier": 1, "status": "success", "agent": "A", "details": {}},
            {"timestamp": "2026-08-01T10:00:01", "action": "old_two", "target": "t",
             "tier": 1, "status": "success", "agent": "A", "details": {}},
        ]),
        encoding="utf-8",
    )
    security.log_action("new_one", "t", 1, "success", "A")

    actions = [h["action"] for h in security.get_action_history(limit=10)]
    assert actions == ["old_one", "old_two", "new_one"]


def test_the_legacy_file_is_skipped_once_the_new_log_can_answer(log, tmp_path):
    """
    Every legacy record predates every new one, so once there are `limit` new
    entries the old file is irrelevant — and a 6.5 MB parse is avoided on a
    command the user types interactively.
    """
    legacy = tmp_path / "action_history.json"
    legacy.write_text("this is deliberately not valid json", encoding="utf-8")

    _log(5, action="new")
    history = security.get_action_history(limit=3)

    assert len(history) == 3
    assert all(h["action"] == "new" for h in history)


def test_the_legacy_file_is_never_written_to(log, tmp_path):
    legacy = tmp_path / "action_history.json"
    legacy.write_text("[]", encoding="utf-8")
    before = legacy.read_text(encoding="utf-8")

    _log(5)

    assert legacy.read_text(encoding="utf-8") == before
