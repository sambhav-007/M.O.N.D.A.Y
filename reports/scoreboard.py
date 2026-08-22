"""ROADMAP Phase 14 — "smarter" as a number, in one table.

    py -3.12 -m reports.scoreboard              # the fast checks
    py -3.12 -m reports.scoreboard --with-model # plus stage-3 selection

Writes `reports/scoreboard.md`.

Why this exists
---------------
Six phases of work with no scoreboard is six phases of opinion. Each number
below already had a generator; what was missing was one command that prints them
together, so a change can be judged against all of them at once instead of the
one its author was thinking about.

That matters because these numbers **trade against each other**, and the
trade is the interesting part:

* Phase 9 added a plausibility check to stage 1 and coverage went *down*
  (35.3% → 35.1%), because 25 parses that used to "route" were junk. Coverage
  alone would have called that a regression. Precision alone would have called
  matching nothing at all a triumph.
* Phase 11 added alarms and coverage stayed flat, because 549 new rows entered
  the denominator at the same time. The per-intent view is what showed the gain.

A single headline number would have hidden both.

Task success
------------
Added 2026-08-18 by `reports/task_success.py`, and it was the row worth waiting
for: on its first run it found four reads — battery, health, my ip, the process
list — reporting `success: True` with **no evidence at all**. They were not
lying; each really does read psutil or a socket. They simply could not prove it,
having returned bare dicts that never passed through `AgentResult`, which is the
one thing that makes an unwitnessed success unrepresentable.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS = PROJECT_ROOT / "reports"

# Stage 3 must not answer during the deterministic measurements: a local model
# may or may not be running, and a number that depends on that is not a property
# of the app.
os.environ["MONDAY_LLM"] = "off"


def _planner():
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    planner.router.llm = None
    return planner


def measure_coverage(planner) -> Dict[str, Any]:
    """How much of the real corpus reaches a skill (stages 1 and 2 only)."""
    import pandas as pd

    from ml.intent_classifier import predict_intent

    corpus = PROJECT_ROOT / "data" / "external" / "massive_en_us.csv"
    if not corpus.exists():
        return {"value": "—", "detail": "corpus not derived (datagen.fetch_massive)"}

    frame = pd.read_csv(corpus)
    routed = 0
    for text in frame.text:
        command = str(text)
        intent, confidence, _ = predict_intent(planner.classifier, command)
        if planner.router.route(command, intent=intent, confidence=confidence).routed:
            routed += 1
    return {
        "value": f"{routed / len(frame):.1%}",
        "detail": f"{routed:,} of {len(frame):,} real utterances reach a skill",
    }


def measure_precision(planner) -> Dict[str, Any]:
    """The negative set: commands that must reach nothing, and do.

    Coverage can always be raised by matching more, so it is only meaningful
    beside this. These are the commands MONDAY has no honest answer for.
    """
    from ml.intent_classifier import predict_intent

    must_refuse = [
        "book me a flight to delhi on tuesday",
        "book me a table for two tonight",
        "summarise my last email and reply to it",
        "order me a pizza",
        "play some jazz",
        "call me an uber to the airport",
        "transfer 500 rupees to mum",
        "delete all my photos",
    ]
    refused = 0
    reached: List[str] = []
    for command in must_refuse:
        intent, confidence, _ = predict_intent(planner.classifier, command)
        decision = planner.router.route(command, intent=intent, confidence=confidence)
        if not decision.routed:
            refused += 1
        else:
            reached.append(f"{command} → {decision.skill.name}")
    return {
        "value": f"{refused / len(must_refuse):.0%}",
        "detail": f"{refused}/{len(must_refuse)} correctly refused"
                  + (f"; reached: {'; '.join(reached)}" if reached else ""),
    }


def measure_skills(planner) -> Dict[str, Any]:
    registry = planner.router.registry
    total = len(registry.skills)
    offline = sum(1 for s in registry.skills if s.offline)
    return {
        "value": str(total),
        "detail": f"{offline} work offline, {registry.pattern_count():,} patterns, "
                  f"{len(registry.tier2_names())} behind the Tier-2 gate",
    }


def measure_suite() -> Dict[str, Any]:
    """The test suite. Run as a subprocess: it must not share this process."""
    started = datetime.now()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "--tb=no"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    seconds = (datetime.now() - started).total_seconds()
    summary = ""
    for line in reversed(proc.stdout.splitlines()):
        if "passed" in line or "failed" in line:
            summary = line.strip()
            break
    passed = "failed" not in summary and proc.returncode == 0
    return {
        "value": "green" if passed else "RED",
        "detail": f"{summary} ({seconds:.0f}s)",
    }


def measure_task_success(with_network: bool = False) -> Dict[str, Any]:
    """Whether a routed command then *worked*. Runs the skills, safely."""
    from reports.task_success import run

    rows = run(with_network)
    measured = [r for r in rows if r["outcome"] != "skipped"]
    passed = [r for r in measured if r["outcome"] == "passed"]
    failed = [r["command"] for r in measured if r["outcome"] == "FAILED"]
    return {
        "value": f"{len(passed) / len(measured):.0%}" if measured else "—",
        "detail": f"{len(passed)}/{len(measured)} tasks completed end to end"
                  + (f"; failed: {', '.join(failed)}" if failed else ""),
    }


def measure_selection() -> Dict[str, Any]:
    """Stage 3's skill-selection accuracy. Needs a running model, so opt-in."""
    from reports.stage3_selection import load_cases, run

    os.environ.pop("MONDAY_LLM", None)
    try:
        cases, planner = load_cases()
        _, summary = run(os.environ.get("MONDAY_LLM_MODEL", "llama3.2:3b"), cases, planner)
    except SystemExit as exc:
        return {"value": "—", "detail": str(exc)}
    finally:
        os.environ["MONDAY_LLM"] = "off"
    return {
        "value": f"{summary['accuracy']:.1%}",
        "detail": f"{summary['correct']}/{summary['n']} on {summary['model']}, "
                  f"p50 {summary['p50']:.1f}s",
    }


ROWS = [
    ("Coverage", "% of 11k real utterances that reach a skill", "massive_coverage.py"),
    ("Precision", "% of the negative set correctly refused", "this file"),
    ("Capability", "skills registered", "the registry"),
    ("Suite", "tests, offline", "pytest"),
]


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-model", action="store_true",
                        help="also score stage 3, which needs Ollama running")
    parser.add_argument("--no-suite", action="store_true",
                        help="skip the test suite (the slow row)")
    parser.add_argument("--with-network", action="store_true",
                        help="include the task-success entries that need the network")
    args = parser.parse_args(argv)

    planner = _planner()
    results = [
        ("Coverage", measure_coverage(planner)),
        ("Precision", measure_precision(planner)),
        ("Capability", measure_skills(planner)),
        ("Task success", measure_task_success(args.with_network)),
    ]
    if not args.no_suite:
        results.append(("Suite", measure_suite()))
    if args.with_model:
        results.append(("Selection", measure_selection()))

    width = max(len(name) for name, _ in results)
    print()
    for name, row in results:
        print(f"  {name:<{width}}  {row['value']:>8}   {row['detail']}")
    print()

    lines = [
        "# MONDAY scoreboard",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py -3.12 -m reports.scoreboard`.",
        "",
        "These numbers trade against each other, which is the reason they are in",
        "one table. Phase 9 raised precision and coverage went *down*, because 25",
        "parses that used to \"route\" were junk; Phase 11 added a capability and",
        "coverage stayed flat, because new rows entered the denominator at the",
        "same time. Either number alone would have told a wrong story.",
        "",
        "| Measure | Value | Detail |",
        "|---|---:|---|",
    ]
    for name, row in results:
        lines.append(f"| {name} | **{row['value']}** | {row['detail']} |")
    lines += [
        "",
        "**Task success** runs each command and checks the outcome, not the",
        "routing decision — see `reports/task_success.md` for the set and for",
        "what it deliberately does not measure (sending mail, killing processes,",
        "anything that cannot be run twice safely).",
        "",
    ]
    (REPORTS / "scoreboard.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORTS / 'scoreboard.md'}")


if __name__ == "__main__":
    main()
