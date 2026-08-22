"""Mapping MASSIVE's 60 intents onto MONDAY's 7.

The mapping is the whole contribution of this module, so it is written out one
intent at a time with the reason attached, rather than as a dict of guesses.

The governing rule: **an utterance is kept only if MONDAY has somewhere to send
it.** A real command mapped to a class the app cannot serve does not make the
classifier better, it makes it confidently wrong — which is the failure this
whole repo has spent its commits removing. So 25 of MASSIVE's 60 intents are
dropped, and the drops are listed below with their reasons; they are not
silently absent.

Sizes after mapping (en-US, 16,521 utterances in, 10,686 kept):

    browser              3,845   qa · weather · news · recommendation
    communication        3,325   email · calendar
    desktop_automation   1,760   audio volume · datetime · hue/wemo
                                 (+ alarms from 2026-08-18, see below)
    memory_query           793   lists
    llm_fallback           829   general_quirky
    chitchat               134   general_greet · general_joke
    document_intel           0   nothing in MASSIVE resembles it

`document_intel` getting nothing is worth stating plainly: MASSIVE is a *voice*
assistant corpus, and nobody dictates "summarise chapter 3 of the PDF" to a
smart speaker. That class stays entirely generated, and it is the one to watch
if real-command accuracy for documents stays low.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = PROJECT_ROOT / "data" / "external" / "massive_en_us.csv"

# ── Kept ─────────────────────────────────────────────────────────────────────
MASSIVE_TO_MONDAY: Dict[str, str] = {
    # Volume control is a headline MONDAY feature and, before this, the corpus
    # had exactly six templated phrasings of it. These are 387 real ones.
    "audio_volume_up": "desktop_automation",
    "audio_volume_down": "desktop_automation",
    "audio_volume_mute": "desktop_automation",
    "audio_volume_other": "desktop_automation",
    # "what time is it" classified `memory_query` at 0.33 — one of the app's own
    # /help examples. datetime_query is 502 real phrasings of it.
    "datetime_query": "desktop_automation",
    "datetime_convert": "desktop_automation",
    # Smart-home control routes to `toggle_smart_light`, which reports
    # NOT_IMPLEMENTED honestly (handoff.md: "still registered so the planner's
    # route gives a useful answer"). Reaching an honest refusal is a better
    # outcome than being answered with a greeting, so these are kept — but only
    # the light and plug intents, which that tool names. `iot_cleaning` and
    # `iot_coffee` have no route at all and are dropped below.
    "iot_hue_lighton": "desktop_automation",
    "iot_hue_lightoff": "desktop_automation",
    "iot_hue_lightup": "desktop_automation",
    "iot_hue_lightdim": "desktop_automation",
    "iot_hue_lightchange": "desktop_automation",
    "iot_wemo_on": "desktop_automation",
    "iot_wemo_off": "desktop_automation",
    # Email is real SMTP in this app, behind the Tier-2 gate.
    "email_sendemail": "communication",
    "email_query": "communication",
    "email_querycontact": "communication",
    "email_addcontact": "communication",
    # `comms_agent` schedules and reads calendar events (data/calendar.json).
    # `calendar_remove` is dropped: there is no deletion path.
    "calendar_set": "communication",
    "calendar_query": "communication",
    # Knowledge questions go to Wikipedia then live web search
    # (`_is_knowledge_question`). "what is the capital of france" — the example
    # in that function's own docstring — classified `chitchat` at 0.47.
    "qa_factoid": "browser",
    "qa_definition": "browser",
    "qa_maths": "browser",
    # `bitcoin price` classified `desktop_automation` at 0.26. These two are the
    # real phrasings of a price lookup, which `PublicApiAgent` serves live.
    "qa_currency": "browser",
    "qa_stock": "browser",
    "weather_query": "browser",
    "news_query": "browser",
    # "find me somewhere to eat nearby" is a web search in this app.
    "recommendation_locations": "browser",
    "recommendation_events": "browser",
    "recommendation_movies": "browser",
    # Lists are how people phrase remember/recall out loud: "add milk to my
    # shopping list", "what's on my list". `recall prof` scored 0.40.
    "lists_createoradd": "memory_query",
    "lists_query": "memory_query",
    "lists_remove": "memory_query",
    # Timers and alarms, built in ROADMAP Phase 11 (`core/timers.py`). These
    # three were refused for "no alarm or timer exists" until 2026-08-18, which
    # was true and is the reason they were built.
    "alarm_set": "desktop_automation",
    "alarm_query": "desktop_automation",
    "alarm_remove": "desktop_automation",
    "general_greet": "chitchat",
    # MONDAY answers this live from jokeapi.dev.
    "general_joke": "chitchat",
    # MASSIVE's own catch-all for utterances that fit no intent. That is exactly
    # what `llm_fallback` means here — the low-confidence bucket 2.5 learns to
    # route — so this is the closest thing to a free, real, labelled negative
    # class the project could have asked for.
    "general_quirky": "llm_fallback",
}

# ── Dropped, and why ─────────────────────────────────────────────────────────
# Kept as data rather than prose so `test_intent_corpus.py` can assert that
# every one of MASSIVE's 60 intents is either mapped or explicitly refused —
# a new MASSIVE release adding an intent should fail a test, not be ignored.
MASSIVE_DROPPED: Dict[str, str] = {
    "calendar_remove": "events can be added and read, not deleted",
    "cooking_recipe": "no recipe route; would train browser on a capability MONDAY does not claim",
    "cooking_query": "same",
    "iot_cleaning": "no robot-vacuum route, unlike the hue/wemo intents above",
    "iot_coffee": "no coffee-machine route",
    "music_query": (
        "media keys can play, pause and skip what is already open; they cannot "
        "answer 'what song is this'"
    ),
    "music_likeness": "no music control",
    "music_dislikeness": "no music control",
    "music_settings": "no music control",
    # Reworded 2026-08-18: MONDAY has media keys now, so "no playback control"
    # became half wrong. The accurate refusal is narrower and is the reason this
    # stays refused: `play_music` is overwhelmingly "play <artist>", and a
    # play/pause key presses play on whatever is already open. Training 2.1 to
    # send "play some jazz" there would manufacture exactly the confident wrong
    # action ROADMAP Phase 9 was built to stop.
    "play_music": (
        "media keys control what is already playing; nothing here can choose "
        "what plays"
    ),
    "play_radio": "no playback control",
    "play_podcasts": "no playback control",
    "play_audiobook": "no playback control",
    "play_game": "no playback control",
    "social_post": "no social posting; WhatsApp sends to a contact, it does not post",
    "social_query": "no social feed to read",
    "takeaway_order": "no ordering capability",
    "takeaway_query": "no ordering capability",
    "transport_query": "no transit route",
    "transport_ticket": "no booking capability",
    "transport_taxi": "no booking capability",
    "transport_traffic": "no traffic route",
}


def map_rows(rows: Iterable[Dict[str, Any]]) -> pd.DataFrame:
    """Maps raw MASSIVE JSONL records to the `(text, intent, source)` shape.

    Unmapped intents are dropped. `partition` is deliberately discarded: MASSIVE
    splits for its own benchmark, and reusing that split here would silently mix
    two different evaluation protocols. This project makes its own split, and
    reports against `reports/real_command_evidence.py` besides.
    """
    kept: List[Dict[str, str]] = []
    for row in rows:
        target = MASSIVE_TO_MONDAY.get(row.get("intent", ""))
        if target is None:
            continue
        text = (row.get("utt") or "").strip()
        if not text:
            continue
        kept.append({
            "text": text,
            "intent": target,
            "source": "massive",
            "massive_intent": row["intent"],
        })

    df = pd.DataFrame(kept)
    # MASSIVE has near-duplicates across workers ("what time is it" appears many
    # times). Keeping them would weight common phrasings more heavily, which is
    # arguably realistic — but the generated half is deduplicated by
    # construction, and mixing the two conventions makes the class counts
    # impossible to reason about. Dedupe, and say so.
    return df.drop_duplicates(subset=["text"]).reset_index(drop=True)


def load_massive() -> pd.DataFrame | None:
    """Reads the committed derived CSV, or None if it has not been fetched.

    Never downloads. `datagen.generate` must work offline on a fresh clone, so
    a missing file degrades to the generated corpus alone rather than reaching
    for the network mid-build.
    """
    if not OUT_CSV.exists():
        return None
    try:
        df = pd.read_csv(OUT_CSV)
    except Exception:
        return None
    if "text" not in df.columns or "intent" not in df.columns:
        return None
    return df.dropna(subset=["text", "intent"]).reset_index(drop=True)
