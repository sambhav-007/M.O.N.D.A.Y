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
    #
    # Reclassified in tranche 4. It was a negative because the *battery* branch
    # fired on `"charge" in cmd_lower`. It is a question, and questions are now
    # answered by `answer_question` rather than falling through to a knowledge
    # search bolted on below the chain — so reaching a skill is the correct
    # answer here. The battery capture it was written to catch is still tested:
    # the assertion below is that it is not `battery_status`.
    ("how much do you charge for consulting", "answer_question"),
    # Reclassified in tranche 2, and the reason matters. This was a negative
    # because the *crypto* branch grabbed it — `"eth" in cmd_lower` matches
    # m-eth-od. It is genuinely a memory recall, so now that recall_memory
    # exists, reaching it is the correct answer rather than a capture. The
    # "eth" negative is still covered by the "whether it rains" case below,
    # which no skill should claim.
    ("what did i say about the method", "recall_memory"),
    ("tell me something about whether it rains", "answer_question"),   # "eth" again
    # Reclassified in tranche 4 and 6 respectively — both now have a skill.
    # `what is the capital of france` was a negative because nothing could serve
    # it; it is a question and `answer_question` answers questions.
    ("what is the capital of france", "answer_question"),
    ("send mail to a@b.com", "send_email"),
    # Both reclassified in tranche 3: the browser surface has skills now, so
    # reaching one is the correct answer rather than a capture. See below.
    ("open notepad", "open_app_or_website"),
    ("determination is important", "(fallback)"),                 # "terminate"
    ("i need to book a flight", "(fallback)"),
    ("search for python tutorials", "web_search"),
    ("this sentence is a statement", "(fallback)"),               # bare "{key} is {value}"
    ("the meeting is on friday", "(fallback)"),

    # ── Tranche 2 ────────────────────────────────────────────────────────────
    ("screenshot", "take_screenshot"),
    ("take a screenshot", "take_screenshot"),
    ("kill notepad", "terminate_process"),
    ("terminate chrome", "terminate_process"),
    ("remember my exam is on friday", "remember_fact"),
    ("remember that the wifi password is on the fridge", "remember_fact"),
    ("recall my exam", "recall_memory"),
    ("what did i say about the exam", "recall_memory"),
    ("summarize README.md", "summarize_document"),
    ("summarise the file notes.txt", "summarize_document"),
    # Contact numbers are a more specific reading of "remember X is Y" and must
    # reach the validated contact path, not the generic memory store.
    ("remember papa number is 9876543210", "save_contact_number"),
    ("mummy's number is 9876543210", "save_contact_number"),

    # ── From live use, 2026-08-10 ────────────────────────────────────────────
    # Asking what a number *is* is not asking to send anything. This fell into
    # the WhatsApp send flow, which read "what" as the recipient's name and
    # offered to save a contact called "what".
    ("what is papa's whatsapp number", "lookup_contact_number"),
    ("what's mummy's number", "lookup_contact_number"),
    ("what is the number for papa", "lookup_contact_number"),
    # Classified `chitchat` at 0.25 and answered with a web search that returned
    # an SEO article titled "How to Know How Many Files I Have on My PC". The
    # machine can just be asked.
    ("how many files are on my desktop", "desktop_contents"),
    ("what is on my desktop", "desktop_contents"),
    ("list my desktop", "desktop_contents"),

    # ── Tranche 3: the browser surface ───────────────────────────────────────
    # "open gmail" answered "✓ Recipient set to 'recipient@example.com'! What is
    # the subject of the email?" — the email branch fired on `"gmail" in
    # cmd_lower` ~70 lines above the launcher, so a request to open a website
    # became a half-built message to a placeholder address.
    ("open gmail", "open_app_or_website"),
    ("open file explorer", "open_app_or_website"),
    ("launch spotify", "open_app_or_website"),
    ("go to github.com", "open_app_or_website"),
    # Four words after the verb, so the launcher's word-count guard rejected it,
    # and it fell all the way to CoderAgent: "I'm not sure how to do that yet".
    ("open youtube.com on my browser", "open_app_or_website"),
    ("open youtube in chrome", "open_app_or_website"),
    # Searched DuckDuckGo for "web for YouTube" and reported five results, so it
    # looked like a success. The verb-stripping regex took "search" and left the
    # words that said *where* to search inside what was searched for.
    ("search web for YouTube", "web_search"),
    ("search the internet for rust tutorials", "web_search"),
    ("google weather in delhi", "web_search"),
    # Classified `desktop_automation` at 0.33 and dispatched to CoderAgent, which
    # wrote a scraper and ran it in a subprocess — the live fetch that
    # `--block-network` cannot see (handoff.md, Phase 1 note 1).
    ("search current AI news", "web_search"),
    ("research quantum computing", "research_topic"),

    # ── Tranche 3 negatives ──────────────────────────────────────────────────
    # The launcher's word count was load-bearing: it is what stopped this being
    # read as an application named "whatsapp and message papa saying hi". It
    # survives as the `:app` slot bound — and now that WhatsApp is a skill
    # (tranche 6) the command reaches the handler that can parse it directly
    # rather than falling through to reach it.
    ("open whatsapp and message papa saying hi", "whatsapp_message"),
    # "start" is not a launch verb here — `start {target:app}` would match this,
    # and it belongs to the audio agent, which is a skill as of tranche 5.
    ("start meeting recording", "start_meeting_recording"),

    # ── Tranche 4: live data, and the widest keyword lists in the chain ──────
    # `["bitcoin", "btc", "ethereum", "eth", "crypto"]`, tested with
    # `in cmd_lower`. "eth" is a substring of *m-eth-od*, *som-eth-ing* and
    # *wh-eth-er*, so all three were answered with the price of Ethereum.
    ("bitcoin price", "crypto_price"),
    ("what is the price of ethereum", "crypto_price"),
    ("eth price", "crypto_price"),
    ("crypto prices", "crypto_price"),
    ("weather in delhi", "weather"),
    ("what is the weather", "weather"),
    ("what's the weather in tokyo", "weather"),
    ("iss location", "iss_location"),
    ("where is the space station", "iss_location"),
    ("tell me a joke", "tell_joke"),
    # `my ip` was swallowed by the geolocation branch above it, so a question
    # about an IP address was answered by asking a third-party service where the
    # user lives. `/help` has always called this "local network details".
    ("my ip", "network_info"),
    ("what is my local ip address", "network_info"),
    ("where am i", "geolocation"),
    ("what is my city", "geolocation"),
    # `^` was read as Python's XOR, so this answered 1.
    ("calculate 2^3", "calculate"),
    ("what is 12 * 8", "calculate"),
    ("compute 100 / 4", "calculate"),
    ("who is ada lovelace", "answer_question"),
    ("tell me about the eiffel tower", "answer_question"),
    ("hello monday", "chitchat"),
    ("how are you", "chitchat"),
    ("who are you", "chitchat"),

    # ── Tranche 5: the desktop, and the two widest of all ────────────────────
    # `"screen" in cmd_lower` matched "screenshot" and "screen recording";
    # `"light" in cmd_lower` matched *f-light*, *de-light* and *high-light*, so
    # "i need to book a flight" reached the smart-home tool and was answered
    # "✓ Smart Home IoT: Turned 'Living Room Light' ON."
    ("what is on my screen", "analyze_screen"),
    ("read my screen", "analyze_screen"),
    ("turn on the living room light", "toggle_smart_light"),
    ("turn off the lights", "toggle_smart_light"),
    ("history", "audit_history"),
    ("proactive", "proactive_suggestions"),
    ("list processes", "list_processes"),
    ("say hello world", "speak_text"),
    ("organize C:/Downloads", "organize_folder"),
    ("read my latest email", "read_latest_email"),
    ("convert data.csv to json", "convert_csv_to_json"),
    ("schedule standup at tomorrow 10am", "schedule_event"),
    ("notify me the build finished", "desktop_notification"),
    ("create a folder on my desktop", "create_desktop_folder"),

    # ── Tranche 6: email and WhatsApp ────────────────────────────────────────
    ('send mail to a@b.com subject "Hi" body "Hello"', "send_email"),
    ("draft email to john@example.com hello", "compose_email"),
    ("draft a gmail to bob@example.com", "compose_email"),
    ("message +919876543210 saying hello", "whatsapp_message"),
    ("whatsapp +919876543210", "whatsapp_message"),
    ("send whatsapp to bhumi saying hi", "whatsapp_message"),
    ("papa on WhatsApp hello", "whatsapp_message"),
    ("message papa saying good morning", "message_contact"),

    # ── Tranche 4-6 negatives ────────────────────────────────────────────────
    # "flight" contains "light"; "screenshot" contains "screen"; "delight" and
    # "highlight" likewise. None of these may reach a skill.
    ("i need to book a flight", "(fallback)"),
    ("that was a delightful evening", "(fallback)"),
    # `"draft" in cmd_lower` put this in the email branch, which answered
    # "🔒 Contact Unresolved: no email address found for 'a report'".
    ("draft a report on q3 revenue", "(fallback)"),
    # `"say "` as a substring also matches "what did I say about X" — which is
    # why the voice override was anchored. The anchor is structural now.
    ("what did i say about the budget", "recall_memory"),
    # A bare number is a number, not a sum. `{expression:math}` requires an
    # operator so "what is 42" stays a question.
    ("what is 42", "answer_question"),
]


def main() -> int:
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    planner.enable_voice = False
    router = planner.router

    # Stage 3 off. This report is a claim about the deterministic stages, and it
    # has to reproduce on a machine with no model as well as on one with a model
    # running — otherwise the same command routes two ways in two runs and the
    # figure stops being evidence. It matters most for the negatives: a language
    # model will happily find a plausible skill for "determination is
    # important", which is exactly what the negatives exist to catch.
    router.llm = None

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
        "- `open gmail` → the email branch fired on `\"gmail\" in cmd_lower` and",
        "  answered a request to open a website by starting a message to",
        "  `recipient@example.com`.",
        "- `i need to book a flight` → the smart-home branch fired on",
        "  `\"light\" in cmd_lower`, which matches *f-light*, *de-light* and",
        "  *high-light*, and answered \"✓ Smart Home IoT: Turned 'Living Room",
        "  Light' ON.\"",
        "",
        "Patterns match whole commands, so none of these can be captured by accident.",
        "",
        "## The chain is gone",
        "",
        "Earlier versions of this report tracked a fallback count as the migration's",
        "progress bar, because commands the router could not place were handed back",
        "to the substring chain. There is no chain to hand them back to:",
        "`_dispatch_to_agent` is now refuse → help → route → run, and a command no",
        "skill claims gets an honest `NO_SKILL_MATCHED` rather than being passed to",
        "a code generator that writes a Python script and runs it.",
        "",
        "So the `(fallback)` rows below are the **negatives** — commands that must",
        "not be captured — and nothing else. A positive falling through is now a",
        "user-visible failure, not a deferred migration step.",
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
