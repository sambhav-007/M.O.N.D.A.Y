# M.O.N.D.A.Y — Session Handoff

_Last updated: 2026-08-14. Machine: Windows 11 Home, user `sambh`._

> **Read this first.** `README.md` § *Status & Known Limitations* is the
> authoritative statement of what works and what does not. This file is a running
> log and parts of it age badly — several items below are struck through because
> they turned out to be stale or simply wrong.

## 0. Changes 2026-08-07 → 08

Ten commits, `16157ee` … `81b06f7`. All committed; nothing is left staged.

### 2026-08-07

| Area | Change |
|------|--------|
| Secrets | Pre-commit guard in `.githooks/` blocks staging `.env` or a real secret value. Enable per clone: `git config core.hooksPath .githooks`. **Verified: no credential was ever committed** — `.env` is untracked and the password appears in no blob on any ref. |
| Ignores | `logs/`, `*.log`, `.env.*` (keeping `.env.example`), and `data/calendar.json` (untracked). |
| **2.6 XAI** | Rewritten to compute **exact Shapley values in closed form** — `shap` is uninstallable here (§8). Verified bit-for-bit identical to `shap.LinearExplainer`. Emits 2 CSVs + 3 figures. Fixed a fabricated `explain_command_intent()` that was live on an API endpoint. |
| **Tier-2 gate** | Now genuinely enforced (PRD §9). See the resolved note in §2c. |
| Docs | README / PRD / MONDAY_ACADEMIC / PROJECT_PLAN reconciled against the code. |

### 2026-08-08

| Area | Change |
|------|--------|
| **`/help`** | New capability menu, shared by the app, CLI and API from `core.planner.build_help_text()` — one source of truth. Replaced a menu advertising a `mondayvoice.mp3` voice clone (abandoned) and a "Self-Evolution Plugin System" that does not exist. Trigger is exact: `help me summarize x.pdf` used to print the menu instead of summarising. `history` and `proactive` were CLI-only and now work everywhere. |
| Email UX | A bare `send mail to a@b.com` collected subject and body instead of offering to send an empty email, and the confirmation now accepts `subject: … body: …` as an edit — previously the draft could not be corrected at all, leaving only "send it empty" or "cancel". |
| **WhatsApp** | Genuinely implemented — see §9. |
| Noise | Stopped printing `❌ Raw Google Gmail API Error: No module named 'googleapiclient'` on every draft; the Google client libs are optional and undeclared, so their absence is normal. |
| Tests | **276 passing**, up from 140. New files: `test_tier2_gate.py` (28), `test_help_command.py` (34), `test_whatsapp.py` (67), `test_email_and_whatsapp_ux.py` (7). |

### 2026-08-08 (later) — UPGRADE_PLAN Phase 1

See `UPGRADE_PLAN.md` for the full five-phase plan this belongs to.

| Area | Change |
|------|--------|
| **Test suite** | **308 passing, 0 failing, offline, in ~70s** (was 276 + 1 flaky failure in 187s). `pytest-recording` replays cassettes from `tests/cassettes/`; `--block-network` is on by default; the 4 genuinely-live tests are `@pytest.mark.network` and deselected. A red suite now means a regression. |
| **2.5 bandit** | `core/planner.py` credited `direct_dispatch` on *both* reward branches regardless of the arm selected, so three of four arms never left Q=0 and `get_policy()`'s argmax was decided by array initialisation. Now credits `routed_arm`. `tests/test_rl_reward_credit.py`. |
| **Tier-2 gate** | An armed gate was silently discarded when the next turn contained "what"/"show"/etc. Now: a clear yes/no resolves the gate first, and abandoning one is announced (`cancelled_pending_approval`). Low-stakes clarifications still clear quietly. |
| **`parse_confirmation`** | `"no, cancel that"` parsed as *unclear* — the prefix test is whitespace-delimited and a comma defeated it. Commas are now normalised. Exact-match and negation behaviour unchanged. |
| **Cassette hygiene** | `tests/test_cassette_hygiene.py` — cassettes are committed, and the first recording carried the user's real IP, city, postcode, ISP, coordinates and elevation. Scrubbed in `conftest.py`; the guard tests were verified against a deliberately leaky decoy. |
| Speed | `test_100_ruthless.py` built a fresh `MasterPlanner` per test (~106×), each loading the ML pipelines and starting an `AutonomyDaemon` thread. Now class-scoped with per-test state reset. |

**Three things worth knowing:**

1. **`--block-network` cannot see subprocesses.** `test_planner_process_command_search`
   took 40s because "search current AI news" classifies as `desktop_automation`
   at **0.33 confidence**, routes to `CoderAgent`, which writes a `web_scraper`
   script and runs it via `subprocess.run` — a live fetch the blocker never sees,
   timing out at 20s, twice. Marked `network`. **The routing is the real defect**
   (UPGRADE_PLAN §1.2): a low-confidence classification reaching generated-code
   execution is Phase 3's problem to remove.
2. **No cassette yet for open-notify or DuckDuckGo.** Both were unreachable /
   rate-limiting on 2026-08-08 and a cassette recorded from an outage pins the
   outage. Each test says so and names the command to record it later.
3. **Re-recording is not routine.** `--record-mode=once` writes real responses;
   read the diff before committing. `test_cassette_hygiene.py` catches the PII
   classes seen so far, not every possible one.

### 2026-08-08 (later still) — UPGRADE_PLAN Phase 2, partial

**`core/contracts.py`** — `AgentResult` may only claim success if it carries
`Evidence`: a `ProcessExit`, `HttpResponse`, `FileRead`/`FileWritten`,
`SystemQuery`, `SmtpAccepted`, `KeypressSent` or `RecordStored`. There is no
variant meaning "trust me". A failure must carry an `error` code. `as_dict()`
emits the `{success, message, error, …data}` shape everything already reads, so a
migrated handler is a drop-in for the one it replaces.

`KeypressSent` exists so WhatsApp keeps reporting at exactly its real strength —
a keypress was sent, not a message delivered. Do not add an evidence variant that
asserts more than the code can observe.

**Migration complete.** All 11 agent modules and `core/tool_registry.py` route
through the contract. `test_all_agent_modules_import_the_contract` fails the
moment a twelfth agent appears without it.

**One limit to remember:** the contract governs *this process*. A generated
script running under `subprocess` can print `[SUCCESS]`, exit 0, and be believed
— that is exactly what `web_scraper` did. Check generated templates by hand.

**Thirteen fabrications removed:**

| Where | Was | Now |
|-------|-----|-----|
| `AudioSummarizerAgent.start/stop_meeting_recording` | "🎙️ Capturing meeting audio streams…" while capturing nothing. No audio capture exists anywhere; `recorded_transcripts` is only ever assigned `[]` | `NOT_IMPLEMENTED` up front |
| `coder_agent` web_scraper template | Printed `[SUCCESS]` and exited 0 when the fetch raised, so the parent believed it | `[FAILED]` to stderr, `sys.exit(1)` |
| `coder_agent` volume template | Same, on non-Windows | Same fix |
| `HabitAgent.detect_habits_and_suggest` | On *any* exception returned a hardcoded habit — "git commit after running tests", 0.85 confidence, 3.2 lift — phrased as "🤖 Habit Detected: I noticed you frequently…". Component 2.4's failure dressed as its output | `HABIT_MINING_FAILED` |
| `PublicApiAgent.get_geolocation` | Fallback returned central Delhi coordinates and `127.0.0.1` as "Local Geolocation Fallback Active". `get_weather` reads lat/lon from it, so a failed lookup became a confident forecast for a city the user was not in | `GEOLOCATION_UNAVAILABLE` |
| `VisionAgent.capture_active_screen` | On grab failure, built a blank dark rectangle and reported "✓ Screen captured (1920x1080)", then fed it to the analyser | `SCREEN_CAPTURE_FAILED` |
| `VisionAgent.analyze_screen_context` | Without Gemini, headed its answer "✓ Screen Vision Analysis" and ended "Visual Inspection: Onscreen content identified", having identified none — it reports mean pixel brightness | Says plainly it can't read the screen without a key |
| `VoiceAgent.speak` | `audio_synthesized: True, trained_voice_used: True` returned before the thread ran; both synthesis paths swallow exceptions | `TaskQueued` — speech was queued |
| `MondayVoiceModel.train_from_reference` | "Extracts acoustic features" but hardcodes `pitch_hz: 185.0`, `spectral_centroid: 1450.0`, `harmonic_ratio: 0.94`. Only the file *size* is read | Fields marked `measured: False`, described as playback defaults |
| `MondayVoiceModel.synthesize_speech` | `success: True` even when gTTS raised **and** pyttsx3 was absent, so no audio existed | `TTS_UNAVAILABLE` |
| `BrowserAgent.open_app_or_website` | Discarded `webbrowser.open`'s return value and reported "✓ Opened Web URL" regardless | `BROWSER_LAUNCH_FAILED` when it returns False |
| `MemoryAgent.auto_store_conversation_turn` | Reported success even when the write it delegates to had failed | Carries the store's verdict |
| `MemoryAgent.recall` | Fallback attached a constant `similarity: 0.5` to every substring hit; callers ranked on a placeholder | `match_method` names the source |

**Three from `tool_registry.py`, as planned:**

| Was | Now |
|-----|-----|
| `read_latest_email` checked whether `data/google_token.json` *existed* and returned a hardcoded subject/sender ("Project Monday Status Update" from "team@monday.ai") as though fetched | Delegates to the real reader |
| `change_volume`'s f-string never interpolated `level`, so 20% and 90% did the same thing, both reported as done | Delegates to `set_system_volume` |
| `toggle_smart_light` returned success with no protocol, no address, no device — the entirety of "Pillar 5: IoT" | `NOT_IMPLEMENTED`, still registered so the planner's route gives a useful answer |
| `ComputerAgent.get_system_volume` returned a hardcoded `50` as a reading; the CIM query never works, so this was the only path | `VOLUME_READ_UNSUPPORTED` |
| `CommunicationAgent.read_latest_email` said "0 unread messages" whenever the inbox was *unknown* | `NOT_CONFIGURED` |

`set_system_volume` also used `subprocess.Popen` and reported success on the next
line, before PowerShell had done anything. It now waits and reports the exit
status. That made the side effect *dependable*, which is why the two tests that
drive it use the new `fake_powershell` fixture — running the suite used to leave
the machine muted.

Two stale assertions updated: `test_agent_computer_get_system_volume` and
`test_agent_comms_read_latest_email` both asserted `success is True`, which held
only because of the fabrication each one was sitting on.

### 2026-08-10 — audit log is append-only

`core.security.log_action` read the entire JSON array, appended one entry and
wrote it all back, **on every action**. O(file) per call against a file that only
grows. Measured on the real log (19,837 entries / 6.5 MB):

| | per action |
|---|---|
| old: read 85 ms + write 255 ms | **340 ms** |
| new: append one line | **0.39 ms** |

That is **872× faster**, and the cost no longer depends on how much history
exists. It was degrading the actual assistant, not just the suite — every
command a user issued paid to re-serialise their whole history.

- Format: `data/action_history.jsonl`, one record per line, never rewritten.
- `data/action_history.json` (the old array) is **still read** so nothing is
  lost, and never written to again. It is skipped entirely once the new log can
  satisfy the request on its own, since every legacy record is older.
- **Cross-process loss is fixed.** The old note in `core/security.py` said this
  "would need a file lock or an append-only format" — this is that format.
  Writers append whole lines instead of overwriting each other's copy.
- **Corruption is confined to a line.** One bad byte used to make the whole array
  unreadable; the reader now skips the line and carries on. The
  `action_history.corrupt-*.json` salvage path is gone because it cannot happen.
- `HabitAgent` read the log with `json.load` inside `except: pass`, so it would
  have silently stopped finding history. It now goes through `get_action_history`
  — and takes the most recent 200 rather than feeding all 19,837 actions into
  component 2.4 as one session, which had been swamping the 300 synthetic ones.

Covered by `tests/test_audit_log.py` (11 tests), including that write cost stops
growing with the log.

### 2026-08-13 — the browser surface (router tranche 3)

Four commands typed into the app, and what came back:

| Typed | Answered |
|-------|----------|
| `open Gmail` | "✓ Recipient set to `recipient@example.com`! What is the subject of the email?" |
| `open WhatsApp` | ✓ Opened WhatsApp *(correct)* |
| `open youtube.com on my browser` | "I'm not sure how to do that yet." |
| `search web for YouTube` | "✓ Found 5 web search results for **'web for YouTube'**." |

Three defects, one shape — the substring chain decided routing before anything
could parse the command:

- **`open gmail` opened an email composer.** The email branch fired on `"gmail"
  in cmd_lower` and sat ~70 lines above the launcher, so a request to open a
  website silently became a half-built message to a placeholder address. This is
  the exact collision `core/skills.py` names in its header; it survived because
  the launcher could never be reached to disagree. Bare `"gmail"` is out of that
  keyword list — every real phrasing containing it (`send a gmail to bob@x.com`)
  also contains `"mail to"`.
- **`open youtube.com on my browser` was not understood at all.** The launcher
  stripped the verb and gave up if more than three words were left, so a URL plus
  a destination failed the count, fell through to `CoderAgent` and got its honest
  refusal. Saying *where* to open something was never a thing the system could
  hear.
- **`search web for YouTube` searched for "web for YouTube".** The branch
  stripped `^(search for|search|find|look up|google)\s+` and searched for
  whatever remained, so the words saying where to search became part of what was
  searched for. It reported five results and looked like a success — the failure
  was in the query, never in the status.

Fixed as tranche 3 of the router (`core/skills_builtin.py`): `open_app_or_website`,
`web_search`, `research_topic`. 17 skills → **20**, routing accuracy **1.000
(74/74)**, 381 → 818 patterns at 0.29 ms per command. Tests:
`tests/test_browser_skills.py` (35). Suite **489 passing, 0 failing, ~65s**.

**Two things worth knowing:**

1. **The word count was load-bearing.** It is what stopped "open whatsapp and
   message papa saying hi" being read as an application named "whatsapp and
   message papa saying hi". It survives as the `{name:app}` slot type
   (`core/intent_patterns.py`, `MAX_APP_TOKENS = 3`), so it now bounds the
   *target* rather than the whole command — which is precisely what let the
   browser suffix be matched instead of counted. Do not widen it without
   re-reading that test.
2. **`start` is deliberately not a launch verb.** `start {target:app}` matches
   "start meeting recording", which belongs to the audio agent. The legacy chain
   still serves `start <app>`, and it runs after that intercept.

This also closes UPGRADE_PLAN §1.2 (Phase 1 note 1 below): `search current AI
news` classified `desktop_automation` at **0.33** and reached `CoderAgent`, which
wrote a scraper and ran it under `subprocess` — the live fetch `--block-network`
cannot see. Stage 1 now places it before any classification is consulted.

One deliberate move: `search api for X` used to reach the public-API directory
(`"search api" in cmd_lower`) and now reaches the web search. The directory is
still served by its own phrasing (`public api for X`), and a command that says
"search" should search.

### 2026-08-13 — the intent corpus is half real now

**The gap that started it.** 2.1 publishes a macro-F1 measured on a held-out
slice of the corpus it trained on. That says the model learned the corpus. It
does not say the corpus resembles what a user types — and it did not:

| | held-out synthetic | the app's own commands | paraphrases of them |
|---|---|---|---|
| before | 0.929 macro-F1 | **0.657** @ 0.549 conf | **0.486** @ 0.444 conf |
| after | 0.919 macro-F1 (SVM) | **1.000** @ 0.813 conf | **0.703** @ 0.547 conf |

`what time is it` returned `memory_query` at **0.33**. `battery` scored **0.26**.
`bitcoin price` → `desktop_automation` at 0.26. All three are `/help` examples.
42% of the app's own commands sat below the router's 0.50 stage-2 floor, and 46
of 67 below `predict_intent`'s 0.65 LLM-fallback threshold — the app believed it
did not understand most of what it could do.

**The cause was coverage, not modelling.** 9,996 rows sounds like a dataset; it
was **117 sentence skeletons** over a **924-word vocabulary**, and the row count
was slot permutation. Battery, my ip, kill, recall, bitcoin, iss and proactive
appeared in *no template at all*. Vocabulary is now **4,871** words.

**And 72% of it was thrown away anyway.** `build_synthetic_dataset` capped at
**500 rows per class**, so the 9,996-row corpus was fitted on 2,800 rows.
Growing a dataset does nothing while that cap binds. It is now
`ml.intent_classifier.SAMPLES_PER_CLASS = 2500`, named once and asserted.

**What was added.** Amazon MASSIVE en-US (16,521 real utterances spoken to a
virtual assistant, Apache 2.0), mapped onto MONDAY's 7 intents by
`datagen/massive.py` — 35 of its 60 intents mapped, the other 25 listed with the
reason they were refused. The rule: **an utterance is kept only if MONDAY has
somewhere to send it.** `transport_ticket` and `play_music` are dropped because
there is no booking or playback; `general_quirky` maps to `llm_fallback` because
MASSIVE's catch-all is exactly this project's low-confidence bucket.

`py -3.12 -m datagen.fetch_massive` re-derives it (39.5 MB download). The output
is committed, so a fresh clone trains offline.

**Four things worth knowing:**

1. **The 1.000 is a coverage check, not accuracy.** The generator's templates
   were written from the same capability list the coverage set is drawn from, so
   the overlap is by construction. The number that means the model generalises is
   the **paraphrase** set — 0.486 → 0.703 — written after the corpus was built and
   deliberately never fed back into the generator.
   `test_the_paraphrase_set_is_not_in_the_corpus` enforces that mechanically, so
   a well-meaning "let's cover these too" fails a test instead of quietly turning
   the generalisation number into a second coverage check.
2. **A generated floor per class is load-bearing.** The first version of
   `build_corpus` topped up with generation only where MASSIVE fell short — so
   MASSIVE filled `browser` and `communication` outright, they got 88 and 98
   generated rows, and **every MONDAY-specific template for them was absent**.
   `search web for youtube` scored 0.29. MASSIVE is a *spoken* corpus: no bare
   URLs, no `subject "…" body "…"`, no WhatsApp, no `iss location`.
   `MIN_GENERATED_PER_CLASS = 800` is coverage, not padding.
3. **Label noise is applied to generated rows only.** Corrupting real human
   labels to make a benchmark harder would be vandalism.
4. **`document_intel` gets nothing from MASSIVE**, and `chitchat` almost nothing —
   nobody dictates "summarise chapter 3 of the PDF" to a smart speaker. Those two
   classes are still effectively synthetic-only and are the least well evidenced
   of the seven.

**A stale artefact found on the way.** `reports/intent_classifier_comparison.csv`
and `intent_classifier_report.md` were last written on **2026-07-23** by a
generator that no longer exists, and nothing in the repo rewrote them — while
`data/DATASET.md` cited the report as the five-model evidence. Anyone quoting it
was quoting 0.9417 from a corpus that had since been replaced twice.
`ml.intent_classifier.run()` writes both now, including which model production
actually loads (Logistic Regression — SVM wins by +0.009 macro-F1 and costs ~47×
the fit time).

Tests: `tests/test_intent_corpus.py` (15). Suite **505 passing, ~50s**.

### 2026-08-14 — identity, WhatsApp, spoken length, and live voice

**Confirmed working by the user on the real machine**, which matters for the
voice half specifically: none of it could be exercised here. Wake-word matching,
echo suppression and barge-in were verified against a real `speechSynthesis` in
a browser, but no audio ever went through a microphone during development, and
whether WebView2 exposes `webkitSpeechRecognition` at all was an open question
until it ran. It does. If that ever changes, the Live button disables itself and
says why, and push-to-talk still works.

**The name bug was self-amplifying.** The identity branch fired on `"my name" in
cmd_lower`, called `memory_agent.recall("name")` and read `matches[0]["value"]`
as the answer. `recall` is a TF-IDF *similarity* search and
`auto_store_conversation_turn` writes one row per exchange whose value is the
whole turn serialised, so:

```
> whats my name
✓ Your name is Agent: MasterPlanner | User: is my name | Assistant:
  ✓ Your name is Agent: MasterPlanner | User: name is sambhag | Assistant:
    Hello! I am M.O.N.D.A.Y. … (OS User: sambh). (OS User: sambh).
```

Every answer was stored as the next turn, so each retelling nested the previous
one and the reply grew without bound. It also fired on *statements* — "my name
is sambhav" ran the reader — while "name is sambhag" missed the branch entirely
and got the chitchat greeting.

Replaced by two skills, `set_user_name` and `get_user_name`: reading and writing
are separate, the name lives under one canonical key, and machine-written rows
are refused via `agents.memory_agent.is_machine_written` — the same guard the
WhatsApp contact lookup already used, now shared rather than duplicated. The old
`boot_context.get("username", "Siddhant")` default is gone too.

**WhatsApp no longer claims to send.** Reported from live use: the Tier-2 gate
was approved, the reply read "Opened the chat for +91… and pressed Enter", and
no message was sent. `send_whatsapp_now` is deleted, not reworded — it slept a
fixed 8 seconds and fired `pyautogui.press("enter")` into whatever window held
focus, so a slow launch, a notification or one stray click sent the keystroke
elsewhere, and nothing here can read WhatsApp back to notice. **A gate in front
of an action that does not happen is worse than no gate**: it asks the user to
authorise something and then reports it done.

The deep link pre-fills and declines to send by design (anti-spam), so preparing
the message *is* the feature. `send_whatsapp` is out of `TIER_2_IMPLEMENTED` and
stays in `TIER_2_ACTIONS`, where default-deny keeps it gated if it is ever
implemented for real. The live Tier-2 surface is now `send_email` and
`terminate_process`.

**Speaking is not printing.** The UI passed `execution_result.message` straight
to `speechSynthesis`, so a scraped search result was read to the end and a
Tier-2 prompt was recited including "can't be undone · est. 1s". `core/speech.py`
decides the spoken form once for every surface: a handler that knows its own
short form sets `speech`, otherwise the message is stripped of decoration, URLs
and citations and cut to whole sentences within `MAX_SPEECH_CHARS` (240).

**Live voice, in the UI.** Wake word ("Hey Monday" / "Hello Monday", Live button
or Ctrl+L), continuous listening, and barge-in — talk over MONDAY and it stops.
All browser-native. Three things worth knowing:

1. **Interim results are the whole trick.** They arrive while the user is still
   speaking, which is what makes barge-in feel immediate; a final result would
   be far too late.
2. **`speaking` must be set synchronously.** It was set in the utterance's
   `onstart`, which fires 100 ms+ after `speak()` returns, so interrupting the
   instant a reply arrived — the most natural moment — did nothing. Caught by
   driving the real `speechSynthesis` in a browser, not by the unit tests.
3. **The microphone hears the speakers.** Without `isEcho`, MONDAY barges in on
   its own voice and cuts every reply off after three words. Proper acoustic
   echo cancellation is the real answer; comparing against what it is currently
   saying is the cheap one that works.

This also settles the double-speak item in §6: gTTS and pyttsx3 are both absent
on this machine, so the backend has no TTS at all and `speechSynthesis` is the
only voice. One path, not two.

`tests/test_voice_ui.py` (14) extracts the `Voice` object *from `ui/index.html`*
and runs it under node, so it tests the shipped source rather than a copy that
can drift. Skipped where node is absent. Suite **517 passing**.

## 9. WhatsApp (added 2026-08-08)

WhatsApp has **no API a desktop script may send through**. The deep link
(`whatsapp://send?phone=…&text=…`) opens a chat with the message pre-typed but
deliberately will not send it. Simulating the Enter keypress is the only route,
so that is what the approved path does.

> **Superseded 2026-08-14.** This section described a Tier-2 gate followed by a
> simulated Enter keypress. Both are gone — the keypress did not work and could
> not be made to. See the 2026-08-14 entry above. What remains below is current.

- **Every message is prepared, never sent.** The chat opens with the text typed
  in the box and MONDAY stops there; the user presses Enter. Tier 1 throughout —
  nothing leaves the machine, so there is nothing to confirm.
- A command with no text just opens the chat.
- Numbers default to **+91** (`DEFAULT_COUNTRY_CODE` in `.env`). Lengths are
  validated, not merely bounded.
- Unknown name → asks for the number, saves it as `<name>'s number`, and resumes
  the message that was originally asked for, typed and waiting.
- No optional dependency. `pyautogui` was only ever needed for the keypress.

**Two things that must not drift:**

1. It reports that the message was **typed**, never that it was sent or
   delivered. Nothing here can read WhatsApp back.
2. Number lookup is deliberately strict. `normalise_phone` once stripped every
   non-digit from arbitrary text, and `memory_agent.recall` is a TF-IDF
   *similarity* search — together they addressed a message to a number lifted
   from an unrelated saved conversation transcript. A memory row is now accepted
   only if it is not machine-written (`turn_`/`session_`/`log_`), its key names
   the person, its key reads like a contact record, and its value yields a real
   number. Do not loosen any of those four.

## 8. Environment constraints discovered 2026-08-07 → 08

- **`shap` cannot be installed.** It hard-imports `numba`. numba 0.66 (the only
  build supporting `numpy>=2.3.5`, which `mlxtend`/2.4 requires) is blocked by
  Smart App Control; numba 0.61.2 loads but pins `numpy<2.2` and breaks `mlxtend`.
  No version satisfies both. Do not retry — see `reports/2_6_shap_equivalence.md`.
- **Known-good env:** numpy 2.5.1, pandas 2.3.3, sklearn 1.9.0, scipy 1.18.0,
  mlxtend 0.25.0, starlette 1.3.1, pyautogui 0.9.54. Check with
  `py -3.12 -m pip check`.
- **SAC blocks lift over time.** pandas 3.0.5 was blocked on 2026-08-06 and
  imported fine on 2026-08-07. Reputation-based blocks are not permanent, so a
  block observed once is worth re-testing rather than treating as permanent.
- **`pyautogui` installs cleanly** — SAC does not block it.
- **`app.routes` is unreliable for introspection** in FastAPI 0.140.13 — routes
  added via `include_router` do not appear there but *do* serve. Use
  `app.openapi()['paths']`. This cost real time: the `/ml/*` endpoints looked
  missing and were nearly written up as a critical finding before a `TestClient`
  call returned 200.
- **Tests must not write to `data/memories.db`.** It is the user's real assistant
  memory. Contact-saving tests stub `remember`/`recall`; manual testing left
  fake relatives in it more than once and they had to be deleted by hand.

This captures the state of work so anyone (teammate or future session) can pick up
without re-deriving the hard-won environment knowledge.

## 10. The UI starts offline (2026-08-14)

**Was:** `ui/index.html` loaded **eight** libraries from three CDNs (I said seven
first time — it is Tailwind plus seven three.js files) and imported Google Fonts.
They are plain `<script src>` tags, so a failed load is silent, and the
`ReferenceError: THREE is not defined` it caused in the inline script aborted
everything after it — `sendCommand`, `Voice`, the input handler. With no network
the app was not degraded, it was dead: no commands, no voice, no console, no
visible error. A working connection hides that completely, which is why it
survived this long; it turned up in a sandboxed browser while testing something
else.

**Now:** all eight, plus the two font families (latin + latin-ext, 12 woff2
files), live in `ui/vendor/`. ~1.3 MB committed.

    py -3.12 -m ui.vendor.fetch_vendor          # verify what is committed
    py -3.12 -m ui.vendor.fetch_vendor --write  # re-download

That script records every source URL, version and licence, so the files are
auditable rather than unattributed blobs. three.js and Tailwind are MIT; both
fonts are SIL OFL 1.1. Versions are pinned together on purpose — the three.js
`examples/js` add-ons attach to the `THREE` global and only work against a
matching core.

**The part that nearly shipped broken.** Vendoring the files is the obvious
half; *serving* them is the half that is easy to miss. `/app` returns the HTML
with a `FileResponse`, which serves one file and nothing beside it — and both
entry points go through it, because `app.py` points the pywebview window at
`http://127.0.0.1:8000/app` rather than opening the file from disk. Without a
static mount every `vendor/*.js` request 404s and the fix reintroduces the exact
bug it was meant to remove. `api/main.py` mounts `/vendor`;
`tests/test_offline_assets.py` (8) asserts it, and was checked against a
deliberately removed mount to confirm it can actually fail.

Verified in a browser at `/app`: THREE r128 and all six add-ons defined,
Tailwind applied, WebGL canvas up at 165 FPS, `Voice` and `sendCommand` present,
both vendored fonts loading. Suite **525 passing**.

---

## 1. Environment (the hard-won part)

This machine has **no working system Python installer** — the classic MSI fails with
`0x80070003` (broken per-user Windows Installer). Do **not** retry the MSI.

| What | Where | Notes |
|------|-------|-------|
| **Real Python (use this)** | `C:\Users\sambh\AppData\Local\Python\pythoncore-3.12-64\python.exe` | 3.12.10, **has tkinter**. Installed via the **Python Install Manager** MSIX (`py`, `python`, `pymanager` on PATH). Reachable as `py -3.12`. |
| App/ML deps | (in the real Python above) | numpy/pandas/scikit-learn/rich/mlxtend/fastapi/uvicorn/pydantic/psutil/pypdf/pillow/pygame/**pywebview 6.2.1**/**sounddevice**/**SpeechRecognition**. `shap` **cannot** be installed here — see §8. |
| Voice-clone venv (parked) | `C:\Users\sambh\monday-tts\` | Isolated venv with torch 2.13+cpu, coqui-tts 0.27.5, torchaudio. **Blocked — see §5.** |
| Old embeddable (obsolete) | `C:\Users\sambh\Python312emb\` | Lacks tkinter. Ignore/​delete. |

### Run the app
```bash
py -3.12 app.py
```
Starts the FastAPI engine on `127.0.0.1:8000` and opens the frameless WebGL window
(pywebview → WebView2). Falls back to a tkinter window if pywebview is missing.
Browser-only alternative: `http://localhost:8000/app` (same UI) and `/docs` (Swagger).

---

## 2. Changes made this session (NOT yet committed)

All working, verified. See §4 for git-state caveat before committing.

| File | Change | Why |
|------|--------|-----|
| `ui/index.html` | Made `setEntityMode()` null-safe | **The big bug:** it wrote to a non-existent element `presence-state-badge`, throwing before the fetch — so **every typed command silently did nothing**. Fixed → console now replies. |
| `api/ml_router.py` (**new**) | Endpoints for ML components 2.2–2.5 + `/ml/clo-map` | Only 2.1 was exposed before; now all 5 ML models are demoable at `/docs`. |
| `api/main.py` | `include_router(ml_router)` (2 lines) | Wire the above in. |
| `agents/coder_agent.py` | Unsupported "dynamic task" → honest failure | Was fabricating fake "✓ compiled plugin" success (did nothing, littered `data/plugins/`). Now says it can't do it. Real domains (system_volume, desktop_folder, web_scraper) still work. |
| `agents/computer_agent.py` | Added `file explorer`/`files`/`my computer`/`this pc` aliases → `explorer.exe` | "open file explorer" was doing a Google search. |
| `agents/comms_agent.py` | `send_email` returns honest "not sent" | Was faking "✓ Email successfully sent" without sending. |

### Endpoint map (actual, live)
```
POST /intent/classify        2.1  Intent (CLO04)
POST /ml/eta/predict         2.2  ETA regression (CLO03)
GET  /ml/memory/clusters     2.3  Clustering (CLO04)
GET  /ml/workflows/rules     2.4  Association mining (CLO05)
GET  /ml/router/policy       2.5  RL bandit (CLO05)
GET  /ml/clo-map             summary of all five
POST /agent/execute          full pipeline (intent → RL route → agent)
```
> `/intent/classify` did not actually exist until 2026-08-03 — `/ml/clo-map`
> advertised it but no route implemented it. It is now served from `api/main.py`.
> The README API tables were regenerated on 2026-08-03 and verified against the
> live OpenAPI schema (no drift in either direction).

---

## 2b. Changes made 2026-08-03 (NOT yet committed)

| File | Change | Why |
|------|--------|-----|
| `ml/intent_classifier.py` | `build_synthetic_dataset()` now loads the `datagen/` corpus | It looked for a `command` column; datagen writes `text`, so it silently self-generated a trivially separable dataset. Accuracy fell from a meaningless **1.000** to a defensible **0.929** macro-F1 with a real model spread (DT 0.761). |
| `core/planner.py` | `CognitiveResponseDict.__bool__` reflects real success | It returned `True` unconditionally, so **every failed dispatch** was overwritten with a fake "🤖 Cognitive Response" success. Now falsy when no LLM answered. |
| `core/planner.py` | New `_is_knowledge_question()` → live web search | "what is the capital of France" returned a canned greeting / empty placeholder. |
| `core/planner.py` | Wikipedia miss falls through instead of returning failure | Phrasal topics ("the capital of France") have no wiki page. |
| `core/planner.py` | Voice override anchored to start of command, moved above chitchat | `"say "` as a substring hijacked "what did I **say** about X"; chitchat shadowed "say hello world". |
| `core/security.py` | `log_action` is lock-guarded, writes atomically, retries, never raises | Unlocked read-modify-write from the autonomy daemon thread; on any parse failure the `except` **discarded the entire audit log**. Now lossless in-process (verified 480 writes / 8 threads). Multi-process writers still lose entries to last-writer-wins — documented in the module, would need a file lock or append-only format. Corrupt files are preserved as `data/action_history.corrupt-*.json` (gitignored). |
| `agents/browser_agent.py` | `lite.duckduckgo.com` fallback; non-200 is a failure | DDG answers HTTP 202 with a challenge page; the old code reported `success: True` with 0 results. |
| `agents/public_api_agent.py` | Browser User-Agent; watchdog 10s > request 8s | CoinGecko rejected `MONDAY-Assistant/1.0`, and the 5s outer watchdog fired before the 5s inner request could finish. Crypto prices now return live. |
| `api/main.py` | Added `POST /intent/classify` | Component 2.1 had no endpoint despite being advertised. |
| `data/plugins/` | Deleted 13 fabricated plugins | Products of the old fake dynamic-task path. Kept the 3 real ones. |
| `.gitignore` | Ignore `data/action_history.json`, `models/monday_voice_profile.joblib` | Both are machine-generated and caused the merge conflicts; the voice profile embeds an absolute path to the training machine. |
| `tests/` | Updated 5 stale assertions | They asserted the fabricated-success behaviour that was deliberately removed. |

## 2c. Changes made 2026-08-06 (NOT yet committed)

| File | Change | Why |
|------|--------|-----|
| `requirements.txt` | `pandas>=2.3.3,<3.0` | Smart App Control blocked pandas **3.0.5** (`pandas/_libs/index.*.pyd`, "An Application Control policy has blocked this file"), killing the engine at import. SAC blocks freshly-published binaries by reputation. 2.3.3 is also the floor `mlxtend` needs — 2.2.3 imports fine but breaks component 2.4. |
| `app.py` | Server thread records its exception; `main()` refuses to open the UI if the engine never came up | The engine ran on a daemon thread, so its `ImportError` vanished; the health-check loop then *ignored its own result* and opened a window onto a dead engine. |
| `core/planner.py` | New `_parse_email_command()` + shared `_handle_send_email()` | The raw command was passed to `send_email()` as the recipient ("Cannot send email to 'send mail to a@b.com subject: ...'"), and subject/body were dropped. Two duplicated branches both did this; the `"gmail"` keyword matched *inside the address*, so the first one won. |
| `agents/comms_agent.py` | `draft_email` writes the local draft before calling Gmail | It built `draft_content`/`draft_file`, returned `file_path`, and claimed "(Draft saved in Web Composer)" — but never wrote the file. A Gmail failure lost the message. |
| `datagen/commands.py` | Added system-settings templates to `desktop_automation` | No volume/brightness/screenshot vocabulary existed, so "change the volume to 100%" classified as `communication`. Now `desktop_automation` at 85.6%. Macro-F1 0.929 → 0.920 (broader, more realistic class). |
| `agents/browser_agent.py` | `_unwrap_ddg_redirect` | The lite endpoint wraps results in `//duckduckgo.com/l/?uddg=…`, so citations showed a redirect instead of the source. |
| `ml/voice_cloner.py`, `ui/index.html` | Stopped replaying `mondayvoice.mp3` on every reply | The reference recording was played before every spoken response from both the backend and the UI, so the same lines repeated endlessly. |
| `agents/comms_agent.py` | **Real SMTP sending** (`smtplib` + `EmailMessage`), plus `_smtp_config()` / `_load_env_value()` / `_load_saved_draft()` | `send_email()` had no `subject`/`body` parameters at all — it structurally could not send anything. Now delivers for real; STARTTLS on 587, implicit SSL on 465. |
| `core/planner.py` | Draft → **confirm** → send state machine (`confirm_send`) | Requested behaviour: ask before sending, send on "send". |
| `core/planner.py` | Email handler ignores `user_approved` | `ui/index.html:584` hardcodes `user_approved: true` on **every** command, which skipped the confirmation and fired a real email on the first message. |
| `core/planner.py` | Subject/body separator optional when quoted | `subject "Greetings"` (no colon) silently parsed as empty — a real email went out with `(no subject)` and no body. |
| `core/planner.py` | Added `send mail`/`mail to`/`draft mail`… to the email keyword guard | `send mail to a@outlook.com` fell through to the chitchat block and returned a greeting. It only appeared to work because `"gmail"` is a substring of a Gmail address. |
| `.env.example` | Documented `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | Gmail needs a 16-char **App Password** (2FA on), not the account password. |

### Email flow (as built)

```
send mail to a@b.com subject "Greetings" body "hello"
  → draft written to data/staging/email_draft_*.json
  → "📧 Draft ready. … Send it? Reply 'send' or 'cancel'."
      'send'    → real SMTP delivery
      'cancel'  → nothing sent, draft kept
      anything else → re-asks (never guesses at a send)
```

Accepts `subject:` and `subject "…"`; unquoted values still need `:` or `=`.
Without SMTP credentials it composes and saves the draft, then says plainly that
sending is not configured — it does not fake a delivery.

> ✅ **Resolved 2026-08-07** (was: `ui/index.html:584` sends `user_approved: true`
> for every command, so every Tier-2 action except email auto-approved).
> `MasterPlanner.require_tier2_approval()` now gates all Tier-2 actions through the
> same confirm-then-act pattern, the UI no longer sends the flag, and the method
> takes no `user_approved` parameter so the bypass cannot be reintroduced.
> Covered by `tests/test_tier2_gate.py`.
>
> Worth knowing: the Tier-2 actions the original note listed (`delete_file`,
> `overwrite_file`, …) **do not exist** in the codebase. The genuinely reachable
> Tier-2 surface is now `send_email`, `send_whatsapp` and `terminate_process`
> (`core.security.TIER_2_IMPLEMENTED`). See PRD §3.

---

## 3. Voice

- **Listening**: `sounddevice` + `SpeechRecognition` installed. Works on a machine
  with a mic + internet (Google Web Speech). Use the mic/press-to-talk in the app.
- **Speaking (current)**: the UI's `speechSynthesis`, and only that. It does not
  use the `ui/mondayvoice.mp3` voice.
- ~~**Replies are still spoken twice**~~ — RESOLVED 2026-08-14, and partly by
  circumstance: gTTS and pyttsx3 are both absent on this machine, so the backend
  `speak()` has no synthesiser to reach and returns `TTS_UNAVAILABLE`. There is
  one voice path, in the UI. Installing gTTS would bring the second one back, so
  if `cli.py` ever needs to talk, route it through the same decision rather than
  letting both fire.
- **What is spoken is not what is printed.** `core/speech.py` decides once, for
  every surface; the UI reads `execution_result.speech`, never `.message`.
- **Real cloning of mondayvoice.mp3**: attempted, **blocked** — see §5.

---

## 4. Git state — RESOLVED AND COMMITTED

> **Updated 2026-08-07.** This section previously said the merge was unstaged and
> uncommitted. That is no longer true: the merge was committed, and work has
> continued on top of it. `git log` is the authority, not this file.

Recent history (newest first):

```
81b06f7 feat(whatsapp): ask "Send it?" and actually send, instead of leaving it typed
2db0860 fix(whatsapp): default +91, validate lengths, and let numbers actually be taught
738baec fix(whatsapp): send to the number the user typed, not one found in memory
507de22 feat(whatsapp): prepare messages by default, auto-send behind the Tier-2 gate
3755255 fix(ux): email drafts you can complete, and no fake WhatsApp sends
3fc2833 feat: /help capability menu, accurate and shared across surfaces
a2687cc docs: reconcile every claim against the code
c17d4ed feat(security): enforce the Tier-2 approval gate (PRD §9)
fbce7e7 feat(2.6): real XAI layer via exact closed-form Shapley values
16157ee chore(security): add pre-commit secret guard, ignore runtime logs and calendar
23aa4e9 feat(email): confirm-then-send over SMTP; fix parsing, routing and startup
```

> **Resolved 2026-08-14.** `voice/tts_bridge.py` is committed — it is real
> source and the only record of how far the XTTS attempt got (§5).
> `ui/_monday_ref_22k.wav` is now **gitignored**: `tts_bridge.py` writes it
> itself when torchaudio cannot read the mp3 directly, so it is generated, not
> authored, like `action_history.json` and the voice profile.

How each merge conflict was originally resolved:
- `agents/comms_agent.py` — kept the honest "not sent" branch; folded in the other
  side's credentials check. Their branch built a Gmail service object and returned
  `"✓ Email transmission initiated"` **without ever calling `.send()`**.
- `data/action_history.json` — unioned both sides (135 entries, deduped, sorted).
  Moot in practice: the file is now gitignored, see below.
- `models/monday_voice_profile.joblib` — regenerated locally. Neither side was usable
  (ours was stale `v2.0`; theirs hardcoded `C:\Users\Siddhant\...`).

(That commit has since been made — see above.)

Cleaned up:
- 13 fabricated `data/plugins/plugin_*.py` deleted; the 3 real ones kept
  (`plugin_system_volume.py`, `plugin_desktop_folder.py`, `plugin_web_scraper.py`).
  Test runs no longer regenerate them — the coder-agent honest-failure path holds.
- `data/action_history.json` and `models/monday_voice_profile.joblib` are now
  gitignored and untracked (files remain on disk).

Nothing is left untracked and undecided. `voice/tts_bridge.py` is committed;
`ui/_monday_ref_22k.wav` is gitignored as a generated artefact of it.

Repo: `https://github.com/sambhav-007/M.O.N.D.A.Y` (private).

---

## 5. Voice cloning (XTTS) — parked, blocked by Smart App Control

Goal: speak replies in the `mondayvoice.mp3` voice (an ~8-sec sample → needs neural
cloning). Got the **entire stack importing** in `C:\Users\sambh\monday-tts` (torch,
torchaudio, torchcodec, transformers, coqui-tts; worked around SAC blocks on `regex`
and matplotlib's DLL).

**Hard wall:** Windows **Smart App Control** blocks **FFmpeg** ("Malicious binary
reputation"). XTTS needs FFmpeg to decode audio (torchcodec + the mp3). Can't bypass
without turning Smart App Control **off**, which is:
- a **system security setting** (out of scope to change here), and
- a **one-way switch** — re-enabling requires resetting/reinstalling Windows.

Even if disabled, the machine had **~4.7 GB RAM free**; XTTS (~2–3 GB, CPU) may be
unusably slow. **Recommendation:** unless the user disables SAC themselves, drop XTTS
and use the **gTTS natural voice** in the app (quick, reliable, far less robotic than
the current browser TTS) — just route UI speech through `POST /agent/voice/speak`.

---

## 6. Known limitations / next steps

- ~~**Intent classifier ~99.8% accuracy**~~ — FIXED 2026-08-03, then **superseded
  2026-08-13**. The 0.929 was real but described a held-out slice of a corpus
  built from 117 templates; on the app's own commands the same model scored
  0.657. The corpus is now half real (Amazon MASSIVE) — SVM 0.919 held-out,
  0.703 on unseen paraphrases. See the 2026-08-13 section above.
- ~~**`common/`** is still orphaned~~ — **WRONG, corrected 2026-08-07.** It is
  imported by `datagen/generate.py:16` (`common.io.save_csv`) and by
  `notebooks/2_1_intent_classifier.ipynb` (`common.preprocessing`,
  `common.metrics`). Do not delete it.
- ~~**Questions misclassify**~~ — FIXED 2026-08-03. Wikipedia first, live web search
  as fallback. See `MasterPlanner._is_knowledge_question`.
- **DuckDuckGo rate-limits this machine** under heavy use — HTTP 202/403 or a refused
  connection. `web_search` reports this as a structured failure (`WEB_SEARCH_HTTP_202`)
  instead of a bogus empty success. The `lite.duckduckgo.com` fallback parser was
  **verified against a live 200 response on 2026-08-06** once the block lifted; that
  check also exposed that lite wraps every result in a `//duckduckgo.com/l/?uddg=`
  redirect, now unwrapped by `BrowserAgent._unwrap_ddg_redirect`.
- **Test suite: 276 passed, 1 failed** (2026-08-08). The failure is
  `test_agent_public_api_fetch_iss_location` — `api.open-notify.org` unreachable.
  Not a code defect: it passed on 2026-08-07 and failed in four of the five runs on
  2026-08-08 without anything touching that path.
- **⚠️ Several tests depend on live third-party APIs** (DuckDuckGo, open-notify,
  CoinGecko), so a red suite does **not** currently mean a regression. This is the
  top outstanding task: mark them `@pytest.mark.network` so
  `pytest -m "not network"` is meaningfully green. Runtime also swings on network
  conditions — 117s to 301s across runs, and one run exceeded a 600s timeout
  entirely. **This is a live demo risk, not just test hygiene.**
- ~~**`data/calendar.json` is tracked but is runtime churn**~~ — FIXED 2026-08-07.
  Untracked and gitignored; both call sites in `agents/comms_agent.py` create it on
  demand. A fresh clone reports an empty calendar until an event is scheduled.
- **No conversational memory** (no LLM) — "show those results you just found" can't
  work. Genuine multi-turn needs an LLM planner (user-provided API key).
- ~~**README** overstates structure/endpoints vs reality~~ — RECONCILED 2026-08-07.
  Two parts of this item were themselves wrong: the README never referenced
  `monday-site/` (only this file did), and the API tables were already accurate —
  all 24 endpoints verified against the live OpenAPI schema. What *was* overstated
  (Google People API / Outlook contacts) is now marked inactive, and the README has
  a **Status & Known Limitations** section that is the authoritative list.
- Voice "listening" and "speaking" need a real mic + audio device to verify end-to-end.
- **`/help` content is width-budgeted to 68 columns** so it fits the CLI's panel on
  an 80-column terminal. Verified in the CLI and as raw text, **not** yet in the
  WebGL console pane — worth a look next time the app is run.
- **2.1 leans on stopwords.** The XAI layer exposed that the top attributions for
  `browser` are `on, my, me, for, to`, because the shared `tfidf = dict(...)`
  config in `ml/intent_classifier.py:352-357` (`build_pipelines`) sets
  `ngram_range`, `max_features`, `sublinear_tf` and `strip_accents` but no
  `stop_words`. Deliberately **not** changed: it would move the published 0.929
  macro-F1, the confusion matrix and the comparison CSVs. The suggested write-up is
  a counterfactual — train a `stop_words='english'` variant, report the delta and
  the cleaner attributions as a 2.6 finding, leave the shipped model alone.

### Suggested order for the remaining work

1. **`@pytest.mark.network`** — cheap, and makes every later result trustworthy.
2. **Offline demo path + rehearsed script** — the largest demo-day risk. DDG
   rate-limits this machine and open-notify has failed repeatedly.
3. ~~**Voice double-speak**~~ — done 2026-08-14; one path, in the UI.
4. **CLO01 report chapter + evidence index** — now backed by a gate that really
   runs, with `tests/test_tier2_gate.py` and the audit log as evidence.
5. The 2.1 stopword counterfactual, if time allows.

---

## 7. Quick verification commands
```bash
# regenerate synthetic datasets (uses datagen/)
py -3.12 -m datagen.generate

# full test suite (~2-4 min, varies with network)
py -3.12 -m pytest tests/ -q

# component 2.6 — writes CLO evidence to reports/ and reports/figures/
py -3.12 -m ml.xai_explainer

# start API only (no GUI)
py -3.12 -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# authoritative endpoint list (do NOT use app.routes - see section 8)
py -3.12 -c "from api.main import app; print(sorted(app.openapi()['paths']))"
```

### Demo-safe commands to type into the app

`/help` · `health` · `battery` · `what time is it` · `history` · `proactive` ·
`remember X is Y` → `recall X` · `kill notepad` (shows the Tier-2 gate) ·
`send mail to a@b.com subject "Hi" body "Hello"` (draft → confirm) ·
`message 9876543210 saying hi` (opens the chat with it typed)

Everything above works offline. Avoid `search …`, `research …`, `weather …`,
`bitcoin price` and `iss location` on an unreliable network — those are the ones
that stall.
