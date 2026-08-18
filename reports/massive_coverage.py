"""How much of the real Alexa corpus can MONDAY actually route?

    py -3.12 -m reports.massive_coverage

Writes:
    reports/massive_coverage.csv     per-utterance routing decisions
    reports/massive_coverage.md      the per-capability summary

Why this exists
---------------
`reports/routing_evidence.py` measures routing against a labelled set written by
this project, and `reports/real_command_evidence.py` measures component 2.1
against paraphrases written by hand. Both are small, and both were written by
the same people who wrote the patterns — so both can be right while the app
still fails a stranger's first sentence.

This one uses `data/external/massive_en_us.csv`: 10,631 utterances Amazon
collected from people talking to a voice assistant, already mapped onto MONDAY's
seven intent classes by `datagen/massive.py`. It asks one question per
utterance — **does this reach a skill?** — and reports the answer per MASSIVE
intent, because one average hides exactly the holes worth finding.

What it found on 2026-08-18, before the work it motivated:

    OVERALL                     30.6%
    news_query        707 rows  32.0%   nearly all to `answer_question`
    qa_stock          200 rows  42.0%   there was no stock skill at all
    audio_volume_up   134 rows   9.0%   "turn up the volume" — wrong word order
    audio_volume_mute 156 rows   6.4%

Two honest limits on the number
-------------------------------
1. **Routing is not correctness.** An utterance that reaches `answer_question`
   counts as routed, and for "tell me the latest news" that is a Wikipedia
   lookup of the word "news" — reaching *a* skill, not the right one. The
   per-intent `top skills` column is there so this is visible rather than
   averaged away.
2. **Stage 3 is off.** A local model may or may not be running on any given
   machine, so it is not a capability the app can claim. This measures stages 1
   and 2 only, which is what a fresh clone with no Ollama gets.
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Before importing the planner: stage 3 must not be consulted, and this is the
# switch that guarantees it regardless of what is running on the machine.
os.environ["MONDAY_LLM"] = "off"

import pandas as pd  # noqa: E402

from core.planner import MasterPlanner  # noqa: E402
from ml.intent_classifier import predict_intent  # noqa: E402

REPORTS = PROJECT_ROOT / "reports"
CORPUS = PROJECT_ROOT / "data" / "external" / "massive_en_us.csv"


def measure() -> Tuple[List[dict], Dict[str, dict]]:
    """Routes every utterance and returns the rows plus the per-intent summary."""
    planner = MasterPlanner()
    planner.enable_voice = False
    # Belt and braces: `MONDAY_LLM=off` already declines, but a stage that is
    # absent cannot be accidentally consulted by a later refactor either.
    planner.router.llm = None

    frame = pd.read_csv(CORPUS)
    rows: List[dict] = []
    summary: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "routed": 0, "skills": defaultdict(int)}
    )

    for text, massive_intent, monday_intent in zip(
        frame.text, frame.massive_intent, frame.intent
    ):
        command = str(text)
        predicted, confidence, _ = predict_intent(planner.classifier, command)
        decision = planner.router.route(
            command, intent=predicted, confidence=confidence
        )
        skill = decision.skill.name if decision.routed else ""

        bucket = summary[str(massive_intent)]
        bucket["n"] += 1
        if decision.routed:
            bucket["routed"] += 1
            bucket["skills"][skill] += 1

        rows.append({
            "text": command,
            "massive_intent": massive_intent,
            "monday_intent_label": monday_intent,
            "predicted_intent": predicted,
            "confidence": round(float(confidence), 4),
            "stage": decision.stage,
            "skill": skill,
            "routed": int(decision.routed),
        })

    return rows, summary


def write_reports(rows: List[dict], summary: Dict[str, dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)

    with (REPORTS / "massive_coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    total = sum(b["n"] for b in summary.values())
    hit = sum(b["routed"] for b in summary.values())

    lines = [
        "# Routing coverage on the MASSIVE corpus",
        "",
        f"**{hit:,} of {total:,} real utterances reach a skill — {hit / total:.1%}.**",
        "",
        "Stages 1 and 2 only; stage 3 is switched off, because a local model may",
        "or may not be running and is therefore not a capability the app can claim.",
        "Reaching *a* skill is not the same as reaching the *right* one — the",
        "`top skills` column is there so that stays visible.",
        "",
        "| MASSIVE intent | n | routed | % | top skills |",
        "|---|---:|---:|---:|---|",
    ]
    for name in sorted(summary, key=lambda k: summary[k]["routed"] / summary[k]["n"]):
        bucket = summary[name]
        top = sorted(bucket["skills"].items(), key=lambda kv: -kv[1])[:3]
        top_str = ", ".join(f"`{s}` ({c})" for s, c in top) or "—"
        lines.append(
            f"| {name} | {bucket['n']} | {bucket['routed']} | "
            f"{bucket['routed'] / bucket['n']:.1%} | {top_str} |"
        )
    lines += [
        f"| **OVERALL** | **{total}** | **{hit}** | **{hit / total:.1%}** | |",
        "",
        "Regenerate with `py -3.12 -m reports.massive_coverage`.",
        "",
    ]
    (REPORTS / "massive_coverage.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if not CORPUS.exists():
        raise SystemExit(
            f"{CORPUS} is missing. Derive it with: py -3.12 -m datagen.fetch_massive"
        )
    rows, summary = measure()
    write_reports(rows, summary)
    total = len(rows)
    hit = sum(r["routed"] for r in rows)
    print(f"{hit:,}/{total:,} routed ({hit / total:.1%})")
    print(f"wrote {REPORTS / 'massive_coverage.md'}")
