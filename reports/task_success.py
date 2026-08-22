"""Did the command actually *work*? — the scoreboard row that was missing.

    py -3.12 -m reports.task_success
    py -3.12 -m reports.task_success --with-network

Writes `reports/task_success.md`.

What this measures that nothing else does
-----------------------------------------
`reports/routing_evidence.py` asks which handler a command reaches.
`reports/massive_coverage.py` asks how many real utterances reach any handler.
`reports/stage3_selection.py` asks whether the model picks the right one. All
three stop at the decision. **None of them runs the skill**, so a capability
that routes perfectly and then fails would score full marks everywhere.

This one executes the command and checks the outcome: the success flag, the kind
of evidence attached, and something specific about the result that a broken
implementation could not fake.

Why it was left out of the scoreboard until now
-----------------------------------------------
Because doing it wrongly is worse than not doing it. A task-success set that
runs `terminate_process` or `send_email` to see whether they work is a set that
closes your programs and emails your contacts every time someone measures. The
constraint drove the design:

* **Every task here is safe to run repeatedly.** Reads, or writes to a temporary
  directory, or state this file creates and then removes.
* **Tier-2 skills are represented by their gate, not their effect.** The correct
  outcome for "kill notepad" is *the approval prompt*, and that is exactly what
  is asserted. Whether the kill then works is not measurable without killing
  something.
* **Network tasks are opt-in** (`--with-network`) and excluded from the headline,
  because a number that changes with the weather is not a measure of the app.

A task that cannot be checked safely is listed as **unmeasurable** with the
reason, rather than being dropped quietly or given a weak check that always
passes.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS = PROJECT_ROOT / "reports"

# The deterministic path is what is being measured: a local model may or may not
# be running, and task success that depends on that is not a property of the app.
os.environ["MONDAY_LLM"] = "off"


class Task:
    """One command, and what "it worked" means for it."""

    def __init__(
        self,
        command: str,
        check: Callable[[Dict[str, Any]], bool],
        why: str,
        network: bool = False,
        setup: Optional[Callable[[Path], str]] = None,
    ) -> None:
        self.command = command
        self.check = check
        self.why = why
        self.network = network
        self.setup = setup


def _ok(result: Dict[str, Any]) -> bool:
    return bool(result.get("success"))


def _evidence(result: Dict[str, Any], kind: str) -> bool:
    return (result.get("evidence") or {}).get("kind") == kind


def build_tasks(scratch: Path) -> List[Task]:
    """The set. Every entry is safe to run again, immediately, forever."""
    document = scratch / "meeting_notes.md"
    document.write_text(
        "Project notes for the autumn release.\n"
        "The deadline for the final report is the 30th of November.\n"
        "Anna owns the migration and Ben owns the changelog.\n",
        encoding="utf-8",
    )

    return [
        # ── Reads that must produce real evidence ────────────────────────────
        Task("what time is it",
             lambda r: _ok(r) and _evidence(r, "system_query") and ":" in r["message"],
             "reads the system clock and reports a time"),
        Task("battery",
             lambda r: _ok(r) and _evidence(r, "system_query"),
             "reads the battery through psutil"),
        Task("health",
             lambda r: _ok(r) and _evidence(r, "system_query") and "%" in r["message"],
             "reports CPU, memory and disk"),
        Task("my ip",
             lambda r: _ok(r) and _evidence(r, "system_query"),
             "reads local adapters, not a public lookup"),
        Task("what processes are running",
             lambda r: _ok(r) and _evidence(r, "system_query"),
             "enumerates real processes"),
        Task("calculate 2^3",
             lambda r: _ok(r) and "8" in r["message"],
             "evaluates rather than eval()s — 2^3 is 8, not 1"),
        Task("what windows are open",
             lambda r: _ok(r) and _evidence(r, "system_query"),
             "enumerates real windows through user32"),

        # ── Writes, to state this file owns ──────────────────────────────────
        Task("remember the report deadline is november 30",
             lambda r: _ok(r) and _evidence(r, "record_stored"),
             "writes to memories.db and says where"),
        Task("recall the report deadline",
             lambda r: _ok(r) and "november" in r["message"].lower(),
             "reads back what the previous task wrote"),
        Task("set a timer for 10 minutes",
             lambda r: _ok(r) and _evidence(r, "task_queued"),
             "schedules a real timer on the tick thread"),
        Task("what timers do i have",
             lambda r: _ok(r) and "1 pending" in r["message"],
             "sees the timer the previous task created"),
        Task("cancel my timers",
             lambda r: _ok(r) and "Cancelled" in r["message"],
             "removes it again, leaving no state behind"),

        # ── Documents, against a file this file wrote ────────────────────────
        Task(f"summarize {document}",
             lambda r: _ok(r) and _evidence(r, "file_read"),
             "reads the file and summarises what is in it"),
        Task(f"what does {document} say about the deadline",
             lambda r: _ok(r) and "november" in r["message"].lower(),
             "retrieves the passage that answers the question"),
        Task(f"search {scratch} for the migration",
             lambda r: _ok(r) and "meeting_notes" in r["message"],
             "finds the right document in a folder"),

        # ── Honest failures. Succeeding here would be the defect ─────────────
        Task("summarize no_such_file_xyzzy.pdf",
             lambda r: not _ok(r) and r.get("error") == "DOCUMENT_NOT_FOUND",
             "refuses a file that does not exist instead of summarising its name"),
        Task("book me a flight to delhi on tuesday",
             lambda r: not _ok(r),
             "refuses rather than writing a junk calendar entry"),
        Task("xyzzy plugh nothing matches this",
             lambda r: not _ok(r) and r.get("error") == "NO_SKILL_MATCHED",
             "says it does not know"),

        # ── Tier 2, measured by its gate ─────────────────────────────────────
        # A Tier-2 prompt reports success=True — it succeeded at *asking*, which
        # is the distinction core/multi_step.py had to learn when the old DAG
        # engine walked straight through the gate by checking only that flag.
        # What proves the gate held is the pending state and the prompt itself.
        Task("kill notepad",
             lambda r: bool(r.get("requires_approval") or r.get("pending_clarification")
                            or "Approve" in str(r.get("message", ""))),
             "asks before an irreversible action — the effect is deliberately "
             "not exercised"),

        # ── Multi-step ───────────────────────────────────────────────────────
        Task("what time is it and then tell me the date",
             lambda r: _ok(r) and r.get("steps_completed") == 2,
             "runs both steps and reports both"),

        # ── Network, opt-in ──────────────────────────────────────────────────
        Task("latest news",
             lambda r: _ok(r) and _evidence(r, "http_response"),
             "fetches real headlines", network=True),
        Task("ifci share price",
             lambda r: _ok(r) and _evidence(r, "http_response"),
             "fetches a real quote", network=True),
    ]


#: Things a user can ask for that this file will not measure, and why. Kept as
#: data so the gaps are visible rather than implied by absence.
UNMEASURABLE = {
    "send an email": "would deliver mail to a real recipient on every run",
    "message a contact on whatsapp": "opens a chat window and needs a keypress",
    "terminate a process": "closes a real program; the gate is measured instead",
    "take a screenshot": "writes an image per run; the skill is exercised in tests",
    "speak out loud": "makes noise on the machine measuring it",
    "organize a folder": "moves real files; exercised against tmp_path in tests",
}


def run(with_network: bool = False) -> List[Dict[str, Any]]:
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    planner.router.llm = None
    planner.timer_service.cancel()

    scratch = Path(tempfile.mkdtemp(prefix="monday_task_success_"))
    rows: List[Dict[str, Any]] = []

    for task in build_tasks(scratch):
        if task.network and not with_network:
            rows.append({"command": task.command, "outcome": "skipped",
                         "why": "needs the network", "network": True})
            continue
        try:
            result = planner.process_command(task.command)["execution_result"]
            passed = bool(task.check(result))
            detail = str(result.get("error") or result.get("message", ""))[:80]
        except Exception as exc:  # noqa: BLE001 — a crash is a failed task
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        rows.append({
            "command": task.command,
            "outcome": "passed" if passed else "FAILED",
            "why": task.why,
            "detail": detail.replace("\n", " "),
            "network": task.network,
        })

    planner.timer_service.cancel()
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-network", action="store_true")
    args = parser.parse_args(argv)

    rows = run(args.with_network)
    measured = [r for r in rows if r["outcome"] != "skipped"]
    passed = [r for r in measured if r["outcome"] == "passed"]

    print()
    for row in rows:
        mark = {"passed": "  ok  ", "FAILED": " FAIL ", "skipped": " skip "}[row["outcome"]]
        print(f"{mark} {row['command'][:66]}")
        if row["outcome"] == "FAILED":
            print(f"        expected: {row['why']}")
            print(f"        got     : {row.get('detail', '')}")
    rate = len(passed) / len(measured) if measured else 0.0
    print(f"\n  {len(passed)}/{len(measured)} tasks completed ({rate:.0%})\n")

    lines = [
        "# Task success",
        "",
        f"**{len(passed)} of {len(measured)} tasks completed — {rate:.0%}.**",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py -3.12 -m reports.task_success`.",
        "",
        "Every other report stops at the routing decision. This one runs the",
        "command and checks the outcome: the success flag, the evidence kind, and",
        "something specific a broken implementation could not fake.",
        "",
        "Every task is safe to run repeatedly — reads, writes to a temporary",
        "directory, or state this file creates and removes. Tier-2 skills are",
        "measured by their **gate**, not their effect: the right outcome for",
        "\"kill notepad\" is the approval prompt, and whether the kill then works",
        "is not measurable without killing something.",
        "",
        "| Task | Outcome | What \"worked\" means |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['command'][:60]}` | {row['outcome']} | {row['why']} |")
    lines += [
        "",
        "## Deliberately not measured",
        "",
        "Listed rather than omitted, so the gaps are visible:",
        "",
    ]
    for what, why in UNMEASURABLE.items():
        lines.append(f"- **{what}** — {why}")
    lines.append("")
    (REPORTS / "task_success.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORTS / 'task_success.md'}")


if __name__ == "__main__":
    main()
