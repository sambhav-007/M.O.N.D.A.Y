"""Does stage 3 pick the right skill? Measured, per model.

    py -3.12 -m reports.stage3_selection                    # the configured model
    py -3.12 -m reports.stage3_selection --model llama3.1:8b
    py -3.12 -m reports.stage3_selection --model llama3.2:3b --limit 60

Writes:
    reports/stage3_selection.csv     one row per command, per model
    reports/stage3_selection.md      the comparison table

Why this exists
---------------
ROADMAP Phase 8 swaps the model behind stage 3, and a model swap with no
measurement is a coin toss dressed as an upgrade. The observation that motivated
the phase, on `llama3.2:3b`:

    'dim the lights a bit'  -> chose volume_down    (wrong skill entirely)
    'put on some music'     -> chose chitchat       (gave up)

Both are plausible-looking wrong answers, which is the only kind a language model
produces and the only kind worth measuring.

How the set is built
--------------------
From `data/external/massive_en_us.csv` — real utterances — keeping **only the
ones stages 1 and 2 fail to route**. That is the point: stage 3 never sees a
command a pattern already caught, so an eval that included those would be
measuring the patterns and calling it the model.

Each MASSIVE intent carries a set of **acceptable** skills rather than one right
answer, because several are genuinely defensible: "what's on my shopping list"
is `recall_memory`, and a model that answered it with `upcoming_events` is
wrong, but "remind me about the dentist" is defensible as either
`schedule_event` or `desktop_notification`. Scoring a defensible choice as an
error would make the number look precise and be worth less.

What it does not measure
------------------------
Whether the skill then *worked*. This is selection accuracy — the decision, not
the outcome. Task success belongs to ROADMAP Phase 14.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

REPORTS = PROJECT_ROOT / "reports"
CORPUS = PROJECT_ROOT / "data" / "external" / "massive_en_us.csv"

#: The sample is drawn with this seed so two models are asked the same
#: questions. A model that wins on a different sample has not won — and one
#: generator shared across intents meant exactly that, because excluding a
#: single utterance shifted the draw for every intent sorted after it. The seed
#: is per intent now, so each intent's sample depends only on that intent.
SEED = 20260818

#: MASSIVE intent → the skills a correct stage 3 may choose, with the reasoning.
#: Anything not listed here is left out of the set entirely rather than guessed
#: at: an eval whose key is uncertain measures the key, not the model.
ACCEPTABLE: Dict[str, Set[str]] = {
    # Unambiguous — one skill does exactly this.
    "audio_volume_up": {"volume_up", "set_volume"},
    "audio_volume_down": {"volume_down", "set_volume"},
    "audio_volume_mute": {"mute_volume"},
    "audio_volume_other": {"set_volume", "read_volume", "volume_up", "volume_down"},
    "news_query": {"latest_news"},
    "weather_query": {"weather"},
    "general_joke": {"tell_joke"},
    "general_greet": {"chitchat"},
    "iot_hue_lighton": {"toggle_smart_light"},
    "iot_hue_lightoff": {"toggle_smart_light"},
    "iot_wemo_on": {"toggle_smart_light"},
    "iot_wemo_off": {"toggle_smart_light"},
    # Stocks: MASSIVE's `qa_stock` mixes "what is google trading at" with
    # "tell me news about the stock market", and both readings are correct.
    "qa_stock": {"stock_price", "latest_news"},
    # Time and date are one question to a person and two skills here.
    #
    # MASSIVE's `datetime_query` also contains "what time is it in london",
    # which MONDAY cannot answer at all — there is no timezone lookup, and
    # `tell_time` would reply with the time in Chandigarh. Those utterances are
    # excluded below rather than keyed, because scoring `tell_time` as correct
    # there rewards a confidently wrong answer, and that is the one thing this
    # repository has spent every commit removing. They belong in Phase 9's
    # negative set, where "reach nothing" is the right outcome.
    "datetime_query": {"tell_time", "tell_date"},
    # Calendar. `desktop_notification` is accepted for "remind me…" because a
    # reminder and an event are the same request in a different register.
    "calendar_set": {"schedule_event", "desktop_notification"},
    "calendar_query": {"upcoming_events"},
    # Lists are how people say remember/recall out loud (datagen/massive.py).
    "lists_query": {"recall_memory"},
    "lists_createoradd": {"remember_fact"},
    "lists_remove": {"recall_memory", "remember_fact"},
    # Mail. `send_email` and `compose_email` are the same intent at different
    # stages of the same flow, and both stop at the draft.
    "email_sendemail": {"send_email", "compose_email"},
    "email_query": {"read_latest_email"},
    "email_querycontact": {"lookup_contact_number", "read_latest_email"},
    # Knowledge. `web_search` and `research_topic` are the honest alternatives
    # when the answer is not in Wikipedia.
    "qa_factoid": {"answer_question", "web_search", "research_topic"},
    "qa_definition": {"answer_question", "web_search"},
    "qa_maths": {"calculate", "answer_question"},
    "qa_currency": {"crypto_price", "answer_question", "web_search"},
    "recommendation_locations": {"web_search", "answer_question", "geolocation"},
    "recommendation_events": {"web_search", "answer_question", "latest_news"},
    "recommendation_movies": {"web_search", "answer_question"},
}

#: Per intent, so one large class cannot decide the score on its own. At six, a
#: single command was worth 17% of an intent's score and the two models differed
#: by fewer commands than that noise; twelve makes the per-intent numbers worth
#: reading and the total worth comparing across runs.
PER_INTENT = 12

#: Utterances dropped from the set after inspection, with the reason. Kept as
#: data so the exclusions are reviewable — a benchmark that quietly drops what
#: the model got wrong is worth nothing, so each of these is excluded for a
#: property of the *question*, never for the answer any model gave.
#:
#: Matched as a substring, case-insensitively, against the utterance.
EXCLUDED: Dict[str, str] = {
    # No timezone lookup exists. `tell_time` would answer with local time,
    # which is wrong rather than unhelpful.
    "time is it in ": "asks the time in another city; MONDAY has no timezone lookup",
    "time in new york": "same",
    "time in london": "same",
}


def build_set(planner) -> List[Tuple[str, str, Set[str]]]:
    """The utterances stages 1 and 2 miss, sampled evenly across intents."""
    from ml.intent_classifier import predict_intent

    frame = pd.read_csv(CORPUS)
    by_intent: Dict[str, List[str]] = defaultdict(list)

    for text, massive_intent in zip(frame.text, frame.massive_intent):
        if massive_intent not in ACCEPTABLE:
            continue
        command = str(text)
        if any(fragment in command.lower() for fragment in EXCLUDED):
            continue
        intent, confidence, _ = predict_intent(planner.classifier, command)
        # Stage 3 only ever sees what the deterministic stages declined.
        if planner.router.route(command, intent=intent, confidence=confidence).routed:
            continue
        by_intent[str(massive_intent)].append(command)

    chosen: List[Tuple[str, str, Set[str]]] = []
    for massive_intent, commands in sorted(by_intent.items()):
        # One generator per intent, seeded from its name: excluding an utterance
        # from one intent must not reshuffle any other.
        random.Random(f"{SEED}:{massive_intent}").shuffle(commands)
        for command in commands[:PER_INTENT]:
            chosen.append((command, massive_intent, ACCEPTABLE[massive_intent]))
    return chosen


def load_cases(limit: int = 0) -> Tuple[List[Tuple[str, str, Set[str]]], object]:
    """Builds the sample once, for every model in the run to share.

    Built with stage 3 switched off, so which commands are asked does not depend
    on what any model would have done with them.
    """
    os.environ["MONDAY_LLM"] = "off"

    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    planner.router.llm = None
    cases = build_set(planner)
    return (cases[:limit] if limit else cases), planner


def run(model: str, cases, planner) -> Tuple[List[dict], dict]:
    os.environ.pop("MONDAY_LLM", None)          # stage 3 must be ON for this
    os.environ["MONDAY_LLM_MODEL"] = model

    from core.llm import LlmStage

    stage = LlmStage(planner.router.registry, model=model)
    if not stage.available():
        raise SystemExit(f"stage 3 unavailable for {model}: {stage.unavailable_reason}")
    planner.router.llm = stage

    # One throwaway call so the weights are resident: the cold start is a real
    # cost but it is paid once per session, and averaging it into 150 commands
    # would describe a machine nobody uses.
    stage.choose("warm up")

    rows: List[dict] = []
    for command, massive_intent, acceptable in cases:
        started = time.perf_counter()
        choice = stage.choose(command)
        elapsed = time.perf_counter() - started

        if choice is None:
            outcome, picked = "declined", ""
        elif choice.skill:
            picked = choice.skill
            outcome = "correct" if picked in acceptable else "wrong"
        else:
            outcome, picked = "answered", ""

        rows.append({
            "model": model,
            "command": command,
            "massive_intent": massive_intent,
            "acceptable": "|".join(sorted(acceptable)),
            "picked": picked,
            "outcome": outcome,
            "seconds": round(elapsed, 2),
        })

    latencies = [r["seconds"] for r in rows]
    counts = defaultdict(int)
    for row in rows:
        counts[row["outcome"]] += 1

    summary = {
        "model": model,
        "n": len(rows),
        "correct": counts["correct"],
        "wrong": counts["wrong"],
        "answered": counts["answered"],
        "declined": counts["declined"],
        "accuracy": counts["correct"] / len(rows) if rows else 0.0,
        "p50": statistics.median(latencies) if latencies else 0.0,
        "p95": (statistics.quantiles(latencies, n=20)[18]
                if len(latencies) >= 20 else max(latencies, default=0.0)),
    }
    return rows, summary


def write_reports(all_rows: List[dict], summaries: List[dict]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / "stage3_selection.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)

    lines = [
        "# Stage 3 — skill-selection accuracy, by model",
        "",
        "Real utterances from Amazon MASSIVE, **restricted to the ones stages 1",
        "and 2 fail to route** — so this measures the model, not the patterns.",
        "Each MASSIVE intent carries a set of acceptable skills, because several",
        "readings are genuinely defensible; the sets are in `reports/stage3_selection.py`",
        "with the reasoning attached.",
        "",
        "Selection accuracy only. Whether the skill then *worked* is task success,",
        "and belongs to Phase 14.",
        "",
        "| model | n | correct | wrong | answered instead | declined | accuracy | p50 | p95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            f"| `{s['model']}` | {s['n']} | {s['correct']} | {s['wrong']} | "
            f"{s['answered']} | {s['declined']} | **{s['accuracy']:.1%}** | "
            f"{s['p50']:.1f}s | {s['p95']:.1f}s |"
        )
    lines += ["", "Regenerate with `py -3.12 -m reports.stage3_selection --model <name>`.", ""]
    (REPORTS / "stage3_selection.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", default=None,
                        help="repeatable; compares models on the same sample")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    models = args.model or [os.environ.get("MONDAY_LLM_MODEL", "llama3.2:3b")]
    cases, planner = load_cases(args.limit)
    print(f"{len(cases)} commands, {len(set(c[1] for c in cases))} intents")

    all_rows: List[dict] = []
    summaries: List[dict] = []
    for model in models:
        print(f"── {model} ─────────────────────────────────")
        rows, summary = run(model, cases, planner)
        all_rows.extend(rows)
        summaries.append(summary)
        print(f"   {summary['correct']}/{summary['n']} correct "
              f"({summary['accuracy']:.1%})  p50 {summary['p50']:.1f}s  "
              f"p95 {summary['p95']:.1f}s")

    write_reports(all_rows, summaries)
    print(f"wrote {REPORTS / 'stage3_selection.md'}")


if __name__ == "__main__":
    main()
