"""Component 2.1 evidence on **real commands**, not a held-out synthetic split.

    py -3.12 -m reports.real_command_evidence

Writes:
    reports/real_command_accuracy.csv     per-command predictions
    reports/real_command_evidence.md      the summary

Why this exists
---------------
2.1 reports a macro-F1 on a held-out slice of the same corpus it trained on.
That number says the model learned the corpus; it does not say the corpus
resembles what users type. Measured on 2026-08-13, the gap was the whole story:

    held-out synthetic macro-F1      0.929
    the app's own advertised commands 0.657 accuracy, 0.549 mean confidence

`what time is it` — a `/help` example — came back `memory_query` at 0.33.
`battery` came back at 0.26. The corpus was 9,996 rows built from 117 sentence
skeletons over a 924-word vocabulary, and whole capabilities (battery, my ip,
kill, recall, bitcoin, iss, proactive) appeared in **none** of them.

The two sets below measure different things, and conflating them would be the
easiest way to lie with this file.

**COVERAGE** — the 67 commands the app advertises (`/help`, the demo-safe list
in handoff.md, the routing set). The generator's templates were written *from
that capability list*, so overlap is by construction and a high score here means
"the corpus covers what the app ships" — a coverage check. It is not evidence of
generalisation and must never be quoted as if it were.

**PARAPHRASE** — the same capabilities worded as a different person would word
them, using no template's phrasing. Written after the corpus was built and
deliberately not fed back into the generator, so it stays a real held-out set.
This is the number that means the model generalises. If a future change makes
COVERAGE rise while PARAPHRASE falls, the corpus is being overfitted to its own
checklist, and this file is how you would find out.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS = PROJECT_ROOT / "reports"

#: `predict_intent`'s own threshold — below this the planner asks an LLM.
LLM_FALLBACK_FLOOR = 0.65
#: `core.router.MIN_INTENT_CONFIDENCE` — below this stage 2 declines to route.
ROUTING_FLOOR = 0.50


# ── Set 1: coverage ──────────────────────────────────────────────────────────
# Ground truth is the class whose agent actually serves the command, taken from
# the routing table, not from a guess about what it "sounds like".
COVERAGE_SET: List[Tuple[str, str]] = [
    # desktop_automation — the machine it runs on
    ("set volume to 40", "desktop_automation"),
    ("mute", "desktop_automation"),
    ("volume 65", "desktop_automation"),
    ("turn the volume down", "desktop_automation"),
    ("system volume to 35", "desktop_automation"),
    ("screenshot", "desktop_automation"),
    ("take a screenshot", "desktop_automation"),
    ("health", "desktop_automation"),
    ("system health", "desktop_automation"),
    ("how is my pc doing", "desktop_automation"),
    ("battery", "desktop_automation"),
    ("battery status", "desktop_automation"),
    ("am i charging", "desktop_automation"),
    ("my ip", "desktop_automation"),
    ("what time is it", "desktop_automation"),
    ("what is the date", "desktop_automation"),
    ("kill notepad", "desktop_automation"),
    ("terminate chrome", "desktop_automation"),
    ("organize downloads", "desktop_automation"),
    ("how many files are on my desktop", "desktop_automation"),
    ("what is on my desktop", "desktop_automation"),
    ("open notepad", "desktop_automation"),
    ("open file explorer", "desktop_automation"),
    ("launch spotify", "desktop_automation"),
    # browser — the web
    ("open gmail", "browser"),
    ("open youtube.com on my browser", "browser"),
    ("open youtube in chrome", "browser"),
    ("go to github.com", "browser"),
    ("visit arxiv.org", "browser"),
    ("search web for youtube", "browser"),
    ("search for python tutorials", "browser"),
    ("search current AI news", "browser"),
    ("google weather in delhi", "browser"),
    ("research quantum computing", "browser"),
    ("find rust tutorials online", "browser"),
    ("what is the capital of france", "browser"),
    ("weather in delhi", "browser"),
    ("bitcoin price", "browser"),
    ("iss location", "browser"),
    ("where am i", "browser"),
    # communication
    ('send mail to a@b.com subject "Hi" body "Hello"', "communication"),
    ("send mail to a@b.com", "communication"),
    ("draft email to bob@example.com", "communication"),
    ("message 9876543210 saying hi", "communication"),
    ("message papa saying good morning", "communication"),
    ("open whatsapp", "communication"),
    ("whatsapp +919876543210", "communication"),
    ("schedule meeting tomorrow 3pm", "communication"),
    ("notify me the build finished", "communication"),
    ("read latest email", "communication"),
    # memory_query
    ("remember my prof is Dr. Gupta", "memory_query"),
    ("recall prof", "memory_query"),
    ("remember that the wifi password is on the fridge", "memory_query"),
    ("what did i say about the exam", "memory_query"),
    ("papa's number is 9876543210", "memory_query"),
    ("what is papa's whatsapp number", "memory_query"),
    ("look up my exam in my memory", "memory_query"),
    ("proactive", "memory_query"),
    # document_intel
    ("summarize README.md", "document_intel"),
    ("summarise the file notes.txt", "document_intel"),
    ("summarize report.pdf", "document_intel"),
    ("give me a summary of the contract", "document_intel"),
    # chitchat
    ("hello", "chitchat"),
    ("hey monday", "chitchat"),
    ("who are you", "chitchat"),
    ("thanks", "chitchat"),
    ("tell me a joke", "chitchat"),
]

# ── Set 2: paraphrase ────────────────────────────────────────────────────────
# The same capabilities, worded as somebody who had not read `/help` would word
# them. **Do not add templates for these.** The moment a phrasing here is fed
# back into `datagen/commands.py` it stops measuring generalisation and this set
# becomes a second coverage check.
PARAPHRASE_SET: List[Tuple[str, str]] = [
    # desktop_automation
    ("crank the sound up a bit", "desktop_automation"),
    ("how much juice is left in this thing", "desktop_automation"),
    ("what's eating my cpu right now", "desktop_automation"),
    ("shut down the frozen chrome window", "desktop_automation"),
    ("snap a picture of my screen", "desktop_automation"),
    ("which network address is this machine on", "desktop_automation"),
    ("quieten it down", "desktop_automation"),
    ("fire up the code editor", "desktop_automation"),
    ("tidy up my downloads directory", "desktop_automation"),
    ("got the time", "desktop_automation"),
    # browser
    ("who won the world cup in 2014", "browser"),
    ("is it going to rain tomorrow in mumbai", "browser"),
    ("pull up the hacker news front page", "browser"),
    ("how much is a dollar in rupees right now", "browser"),
    ("dig up some articles about transformers", "browser"),
    ("what's happening in the markets today", "browser"),
    ("show me that wikipedia page about mughal architecture", "browser"),
    ("whereabouts am i", "browser"),
    # communication
    ("shoot priyanka a quick note about the deadline", "communication"),
    ("drop rahul a whatsapp saying i'll be late", "communication"),
    ("put a meeting in for thursday afternoon", "communication"),
    ("did anyone write to me today", "communication"),
    ("ping the team that the deploy is done", "communication"),
    # memory_query
    ("jot down that the router password is on the modem", "memory_query"),
    ("what was that thing i told you about the exam", "memory_query"),
    ("stash my professor's email for later", "memory_query"),
    ("dig out whatever you kept about the budget", "memory_query"),
    # document_intel
    ("boil this pdf down to a paragraph", "document_intel"),
    ("what are the main takeaways from chapter3.pdf", "document_intel"),
    ("trim the minutes into bullet points", "document_intel"),
    ("skim thesis.pdf and tell me the gist", "document_intel"),
    # chitchat
    ("yo", "chitchat"),
    ("what's up monday", "chitchat"),
    ("cheers mate", "chitchat"),
    # unclear / llm_fallback
    ("sort my life out", "unclear"),
    ("you know the drill", "unclear"),
    ("do the usual", "unclear"),
]


def _evaluate(clf, pairs):
    from ml.intent_classifier import predict_intent

    rows = []
    for command, truth in pairs:
        intent, conf, fallback = predict_intent(clf, command)
        rows.append({
            "command": command,
            "expected_intent": truth,
            "predicted_intent": intent,
            "confidence": round(float(conf), 4),
            "correct": intent == truth,
            "below_routing_floor": conf < ROUTING_FLOOR,
            "llm_fallback": bool(fallback),
        })
    return rows


def _summarise(rows):
    n = len(rows)
    return {
        "n": n,
        "accuracy": sum(r["correct"] for r in rows) / n,
        "mean_confidence": sum(r["confidence"] for r in rows) / n,
        "below_routing_floor": sum(r["below_routing_floor"] for r in rows),
        "below_llm_floor": sum(r["confidence"] < LLM_FALLBACK_FLOOR for r in rows),
    }


def main() -> int:
    from ml.intent_classifier import get_trained_classifier

    clf = get_trained_classifier()

    sets = {"coverage": COVERAGE_SET, "paraphrase": PARAPHRASE_SET}
    results = {}
    all_rows = []
    for name, pairs in sets.items():
        rows = _evaluate(clf, pairs)
        for r in rows:
            r["set"] = name
        results[name] = _summarise(rows)
        all_rows.extend(rows)

    REPORTS.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS / "real_command_accuracy.csv"
    fields = ["set", "command", "expected_intent", "predicted_intent",
              "confidence", "correct", "below_routing_floor", "llm_fallback"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in all_rows)

    md = [
        "# 2.1 on real commands — coverage and generalisation",
        "",
        "Component 2.1's macro-F1 is measured on a held-out slice of the corpus it",
        "trained on. That says the model learned the corpus. It does not say the",
        "corpus resembles what a user types, and until 2026-08-13 it did not:",
        "",
        "| | held-out synthetic | the app's own commands |",
        "|---|---|---|",
        "| before | 0.929 macro-F1 | **0.657** accuracy, 0.549 mean confidence |",
        "",
        "`what time is it` returned `memory_query` at 0.33; `battery` scored 0.26.",
        "Both are `/help` examples. The cause was coverage, not modelling: 9,996 rows",
        "built from 117 sentence skeletons over a 924-word vocabulary, with no",
        "template at all for battery, my ip, kill, recall, bitcoin, iss or proactive.",
        "",
        "## Results",
        "",
        "| Set | n | Accuracy | Mean confidence | Below 0.50 routing floor | Below 0.65 LLM floor |",
        "|---|---|---|---|---|---|",
    ]
    for name in ("coverage", "paraphrase"):
        s = results[name]
        md.append(
            f"| **{name}** | {s['n']} | {s['accuracy']:.3f} | "
            f"{s['mean_confidence']:.3f} | {s['below_routing_floor']} | "
            f"{s['below_llm_floor']} |"
        )
    md += [
        "",
        "## What each set is worth",
        "",
        "**coverage** — the commands the app advertises. The generator's templates",
        "were written from that same capability list, so the overlap is by",
        "construction. A high score means the corpus covers what the app ships. It",
        "is a coverage check and must not be quoted as a generalisation result.",
        "",
        "**paraphrase** — the same capabilities in wordings no template contains,",
        "written after the corpus was built and never fed back into the generator.",
        "This is the number that means the model generalises.",
        "",
        "If a later change raises **coverage** while lowering **paraphrase**, the",
        "corpus is being fitted to its own checklist. That is what this split is for.",
        "",
        "## Misses",
        "",
    ]
    misses = [r for r in all_rows if not r["correct"]]
    if misses:
        md += ["| Set | Command | Expected | Predicted | Confidence |",
               "|---|---|---|---|---|"]
        md += [
            f"| {r['set']} | `{r['command']}` | {r['expected_intent']} | "
            f"{r['predicted_intent']} | {r['confidence']:.2f} |"
            for r in misses
        ]
    else:
        md.append("None.")
    md += [
        "",
        "## A note on `open <thing>`",
        "",
        "`open notepad` and `open gmail` are labelled `desktop_automation` and",
        "`browser` here, but `open_app_or_website` serves both — it tries a local",
        "binary and falls back to the web. The distinction is real in the label",
        "space and absent in the routing, so a confusion between those two classes",
        "on a launch command costs nothing operationally.",
        "",
        "_Generated by `py -3.12 -m reports.real_command_evidence`._",
    ]
    (REPORTS / "real_command_evidence.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    for name in ("coverage", "paraphrase"):
        s = results[name]
        print(f"{name:11} n={s['n']:3}  acc={s['accuracy']:.3f}  "
              f"mean_conf={s['mean_confidence']:.3f}  "
              f"<0.50={s['below_routing_floor']:2}  <0.65={s['below_llm_floor']:2}")
    if misses:
        print("\nMisses:")
        for r in misses:
            print(f"  [{r['set']:10}] {r['command']!r:52} "
                  f"{r['expected_intent']:19} -> {r['predicted_intent']:19} "
                  f"{r['confidence']:.2f}")
    print(f"\nWrote {csv_path.relative_to(PROJECT_ROOT)} and "
          f"{(REPORTS / 'real_command_evidence.md').relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
