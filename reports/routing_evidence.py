"""
Phase 3 evidence — end-to-end routing, not offline classifier accuracy.

Component 2.1 reports a 0.929 macro-F1. Until this phase that number described a
model whose output was computed on every command and then ignored: routing was
decided by ~350 lines of substring tests in `MasterPlanner._dispatch_to_agent`,
and `intent` was not consulted until roughly line 1811.

This script measures the thing that actually matters — **which handler a command
reaches** — and writes two artefacts:

    reports/routing_accuracy.csv      per-command routing decisions
    reports/routing_evidence.md       the summary table

Run:  py -3.12 -m reports.routing_evidence
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS = PROJECT_ROOT / "reports"

# ── The labelled routing set ─────────────────────────────────────────────────
# Every command a migrated skill is expected to serve, plus commands that must
# NOT reach one. The negatives matter more than the positives: the failure this
# phase exists to prevent is a command being grabbed by a handler that merely
# shares a substring with it.
ROUTING_SET: List[Tuple[str, str]] = [
    # tell_time
    ("what time is it", "tell_time"),
    ("what's the time", "tell_time"),
    ("current time", "tell_time"),
    ("tell me the time", "tell_time"),
    ("time", "tell_time"),
    # tell_date
    ("what is the date", "tell_date"),
    ("what's the date today", "tell_date"),
    ("today's date", "tell_date"),
    ("what day is it", "tell_date"),
    # battery
    ("battery", "battery_status"),
    ("battery status", "battery_status"),
    ("battery level", "battery_status"),
    ("what is my battery percentage", "battery_status"),
    ("am i charging", "battery_status"),
    ("power status", "battery_status"),
    # volume
    ("set volume to 40", "set_volume"),
    ("change the volume to 70", "set_volume"),
    ("set volume to 25 percent", "set_volume"),
    ("volume 65", "set_volume"),
    ("mute", "mute_volume"),
    ("mute the sound", "mute_volume"),
    ("turn the volume up", "volume_up"),
    ("increase the volume", "volume_up"),
    ("louder", "volume_up"),
    ("turn the volume down", "volume_down"),
    ("lower the volume", "volume_down"),
    ("quieter", "volume_down"),
    ("what is the current volume", "read_volume"),
    # health
    ("health", "system_health"),
    ("system health", "system_health"),
    ("computer stats", "system_health"),
    ("how is my pc doing", "system_health"),

    # ── Negatives: must fall through, not be captured ────────────────────────
    # Each of these was mis-served by the substring chain.
    ("how much do you charge for consulting", "(fallback)"),      # "charge" → battery
    ("what did i say about the method", "(fallback)"),            # "eth" → ethereum
    ("tell me something about whether it rains", "(fallback)"),   # "eth" again
    ("summarize the quarterly report", "(fallback)"),
    ("what is the capital of france", "(fallback)"),
    ("send mail to a@b.com", "(fallback)"),
    ("remember the wifi password is on the fridge", "(fallback)"),
    ("open notepad", "(fallback)"),
    ("determination is important", "(fallback)"),                 # "terminate"
    ("i need to book a flight", "(fallback)"),
    ("kill notepad", "(fallback)"),                               # not yet migrated
    ("search for python tutorials", "(fallback)"),
]


def main() -> int:
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    router = planner.router

    rows = []
    correct = 0
    stages: Counter = Counter()

    for command, expected in ROUTING_SET:
        decision = router.route(command)
        actual = decision.skill.name if decision.skill else "(fallback)"
        hit = actual == expected
        correct += hit
        stages[decision.stage] += 1
        rows.append({
            "command": command,
            "expected_skill": expected,
            "routed_skill": actual,
            "stage": decision.stage,
            "correct": hit,
            "slots": decision.slots or "",
        })

    total = len(ROUTING_SET)
    accuracy = correct / total

    positives = [r for r in rows if r["expected_skill"] != "(fallback)"]
    negatives = [r for r in rows if r["expected_skill"] == "(fallback)"]
    pos_acc = sum(r["correct"] for r in positives) / len(positives)
    neg_acc = sum(r["correct"] for r in negatives) / len(negatives)

    REPORTS.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS / "routing_accuracy.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    md = [
        "# Routing evidence — Phase 3",
        "",
        "End-to-end routing accuracy: *which handler does a command actually reach?*",
        "This supersedes component 2.1's offline macro-F1 as the measure of routing,",
        "because until this phase the classifier's output was computed and discarded.",
        "",
        f"- **Skills registered**: {len(router.registry.skills)}",
        f"- **Patterns compiled**: {router.registry.pattern_count()}",
        "",
        "| Set | n | Accuracy |",
        "|-----|---|----------|",
        f"| Commands that must reach a skill | {len(positives)} | {pos_acc:.3f} |",
        f"| Commands that must NOT be captured | {len(negatives)} | {neg_acc:.3f} |",
        f"| **Overall** | **{total}** | **{accuracy:.3f}** |",
        "",
        "## Stages used",
        "",
        "| Stage | n |",
        "|-------|---|",
    ]
    for stage, n in stages.most_common():
        md.append(f"| {stage} | {n} |")
    md += [
        "",
        "## Why the negatives are the interesting half",
        "",
        "Every negative below was mis-served by the substring chain this replaces:",
        "",
        "- `how much do you charge for consulting` → the battery branch fired on",
        "  `\"charge\" in cmd_lower`.",
        "- `what did i say about the method` → the crypto branch fired on",
        "  `\"eth\" in cmd_lower`, which matches *m-eth-od*, *som-eth-ing* and",
        "  *wh-eth-er*.",
        "- `determination is important` → contains `terminate`.",
        "",
        "Patterns match whole commands, so none of these can be captured by accident.",
        "",
        "## Not yet migrated",
        "",
        "Commands still handled by the legacy chain fall through to `(fallback)` by",
        "design — `kill notepad`, email and WhatsApp among them. The fallback count",
        "is the migration's progress bar, and it should shrink with each tranche.",
        "",
        f"_Generated by `py -3.12 -m reports.routing_evidence`._",
    ]
    md_path = REPORTS / "routing_evidence.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"Routing accuracy: {accuracy:.3f} ({correct}/{total})")
    print(f"  must-route     : {pos_acc:.3f} ({len(positives)} commands)")
    print(f"  must-not-route : {neg_acc:.3f} ({len(negatives)} commands)")
    print(f"  stages         : {dict(stages)}")
    for r in rows:
        if not r["correct"]:
            print(f"  MISROUTED: {r['command']!r} expected {r['expected_skill']} got {r['routed_skill']}")
    print(f"\nWrote {csv_path.relative_to(PROJECT_ROOT)} and {md_path.relative_to(PROJECT_ROOT)}")
    return 0 if accuracy == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
