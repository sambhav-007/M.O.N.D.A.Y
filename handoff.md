# M.O.N.D.A.Y — Session Handoff

_Last updated: 2026-08-18. Machine: Windows 11 Home, user `sambh`._

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

### 2026-08-15 — the keyword chain is gone (Phase 3 complete)

**`_dispatch_to_agent` was ~520 lines and is now four steps**: refuse, help,
route, run. Three tranches migrated — live data, the desktop surface, and email
and WhatsApp last, behind their 74 tests.

| | before | after |
|---|---|---|
| Skills | 20 | **51** |
| Patterns | 818 | **2,271** |
| Routing accuracy | 1.000 (74 commands) | **1.000 (123 commands)** |
| `core/planner.py` | 2,141 lines | **570** |
| Suite | 525 | **687**, offline, ~75s |

That closes UPGRADE_PLAN Phase 3's "done when" in full: planner under 600 lines,
every existing test still passing, routing table in `reports/`.

**Four defects found on the way**, each a branch answering confidently about
something it had not been asked:

- **`"light" in cmd_lower`** matches *f-light*, *de-light*, *high-light*. "i need
  to book a flight" reached the smart-home tool and was answered "✓ Smart Home
  IoT: Turned 'Living Room Light' ON."
- **`calculate 2^3` answered 1.** `^` is XOR in Python and the branch ran `eval`
  on the captured text. `core/arithmetic.py` parses to an AST, reads `^` as
  exponentiation, refuses non-arithmetic and bounds the exponent (`9**9**9`
  cannot hang the process).
- **`my ip` was swallowed by the geolocation branch above it**, so a question
  about an IP address was answered by asking a third party where the user lives.
  `/help` has always called it "local network details"; now it is, and it is
  offline.
- **`schedule …` and `notify me …` are in `/help` and were reachable by nothing**
  — no branch in the chain mentioned either verb, so both fell through to the
  coder agent's honest refusal.

**Five things worth knowing:**

1. **Nothing reaches code execution from a guess any more.** The chain's final
   `else` handed every unrecognised command to `CoderAgent`, which wrote a Python
   script and ran it under `subprocess`. `CoderAgent` is now reachable only from
   `create_desktop_folder`, which needs an explicit pattern match. The
   `web_scraper` domain is deliberately not routed to at all — its template is
   the one that printed `[SUCCESS]` and exited 0 when the fetch raised.
2. **Stage 2 does something for the first time.** `chitchat`, `memory_query` and
   `document_intel` each have exactly one skill that runs sensibly with no slots,
   so a classification alone can route them. The other four families contain
   irreversible or slot-dependent actions and stay on patterns — and
   `Skill.__post_init__` *raises* if a Tier-2 skill declares intents.
3. **Ranking gained a tie-break: literal text first, then typed slots.** It is
   what separates `what is {expression:math}` from `what is {topic}` — identical
   literal text, otherwise decided by registration order, which is the invisible
   ordering this phase existed to remove.
4. **Routing moved; parsing did not.** `_parse_email_command`,
   `_parse_whatsapp_command`, `_resolve_phone_number` and the four contact guards
   are unchanged, moved out as mixins (`core/contacts.py`, `core/email_flow.py`,
   `core/tier2.py`) so every call site and test keeps working against
   `MasterPlanner`. Re-expressing the most safety-critical parsing in the repo as
   patterns, in the same change that rerouted it, was not worth it.
5. **Two tests were reclassified, not deleted.** `test_a_sentence_is_not_an_app_name`
   and `test_start_is_not_a_launch_verb` asserted `== "(fallback)"` while WhatsApp
   and the audio agent were still served by the legacy chain. They now assert
   against the skill each must reach, which checks the same claim in both
   directions.

### 2026-08-15 — the demo runs with the Wi-Fi off, and a test proves it

`DEMO.md` is a rehearsed ten-minute script in six acts.
`tests/test_demo_script.py` (31) **parses `DEMO.md` itself** and runs every
command in it with sockets blocked. Three claims, all checked: the offline
commands route to skills declared `offline=True`, they all succeed with no
network, and the closing act's refusals really refuse.

It caught a real mislabel on the first run: `send_email` was declared
`offline=False`, but drafting is entirely local — the SMTP connection happens in
`_send_confirmed_email`, on the following turn, only after an explicit yes.

**Act 6 is the closer.** `turn on the living room light`, `start meeting
recording`, `read my latest email`, `summarize this`, `xyzzyspoon12345` — all
five fail on purpose, with error codes, and each one used to fabricate a success.
`summarize this` was fixed while writing it: `{path}` captured "this", and
`summarize_document` treats an unreadable path as a raw text snippet, so it
summarised the four-letter word and reported five key points.

### 2026-08-15 — CLO01 chapter and a self-verifying evidence index

- **`reports/CLO01_ethics_and_safety.md`** — the report chapter, structured
  around the three moments that decide whether an agent is safe: before an
  irreversible action, after any action, and when something does not work. §7 is
  a table of what the system deliberately does *not* claim.
- **`reports/EVIDENCE_INDEX.md`** — every claim → artefact → the command that
  regenerates it.
- **`tests/test_evidence_index.py`** (73) checks that every path cited exists and
  every `py -3.12 -m <module>` names a real module. It found five wrong paths in
  the index on the first run, which is exactly the failure it was written for:
  `intent_classifier_report.md` had been stale for three weeks because its
  generator no longer existed and nothing was checking.

### 2026-08-15 — the 2.1 stopword counterfactual

`py -3.12 -m reports.stopword_counterfactual` →
`reports/2_1_stopword_counterfactual.md`.

| | shipped | `stop_words="english"` |
|---|---|---|
| held-out macro-F1 | 0.9101 | 0.8945 (**−0.0157**) |
| coverage accuracy | 1.000 | 0.970 |
| **paraphrase accuracy** | **0.703** | **0.703 (±0.000)** |
| function words in top-8 attributions | **71%** | **0%** |

**The explanation improves enormously and the generalisation figure does not
move.** That points at the corpus rather than the vectoriser: if the function
words carried real signal about intent, removing them would cost something on
unseen phrasings. It costs nothing there, and a little on the two sets that share
vocabulary with the generator — which is what you would expect if what the
stopwords predict is the *template* (`please`, `asap`, `thanks`), not the intent.

**Two things worth knowing:**

1. **Coefficients and mean |SHAP| disagree, and the disagreement is the
   finding.** The top `browser` *coefficients* are `news`, `weather`, `research`
   — perfectly healthy. The top *attributions* are `my`, `you`, `please`, `is`.
   Ranking on coefficients alone would have made this study look like a
   refutation of the 2.6 finding. The report carries both tables.
2. **The shipped model is unchanged, and that is now enforced.**
   `PRODUCTION_TFIDF` is named in `ml/intent_classifier.py` and imported by the
   study, and `tests/test_stopword_counterfactual.py` fails if it ever gains a
   `stop_words` key. Adopting the variant means regenerating every 2.1 and 2.6
   artefact and deleting that test in the same commit.

`reports/2_6_xai_intent_top_features.csv` was regenerated on the way: it was last
written 2026-08-07, before the corpus was rebuilt on 2026-08-13, so it described
a model trained on data that no longer existed. The finding survived the
regeneration — the top attributions are still function words.

### 2026-08-16 — stage 3: the local LLM (ROADMAP Phase 4)

The router's third stage has been an empty slot since Phase 3. It is filled:
`core/llm.py`, wired into `core/router.py`, 27 tests + 3 live ones.

**What it changes.** A command no pattern and no classifier can place used to get
"I'm not sure how to do that yet". Now it goes to a local model, which either
picks one of the 49 skills it is offered — with arguments — or answers directly.
Nothing typed leaves the machine: Ollama is local, which is most of why it was
chosen over an API key.

**The schema is generated from the registry.** `core/skills.py` already declared
a name, description, tier and `offline` flag for every skill; `Skill.slots` now
derives the *arguments* from the patterns (`core.intent_patterns.slot_spec`). So
the tool manifest is computed, and a pattern gaining a slot gains an argument in
the same commit. Hand-writing a second schema beside the patterns is the exact
shape of the stale-artefact problem this repo keeps finding in its own reports.

**Containment, which is most of the code.** The model is offered
`registry.llm_reachable_skills()` and nothing else, and the name it returns is
validated against that same set — so a name it invents is refused rather than
run. Two skills are excluded:

- **`terminate_process`** — Tier 2. `Skill.__post_init__` forces
  `llm_reachable=False` for Tier 2 rather than raising, so a skill that declares
  nothing gets the safe answer instead of an error someone silences.
- **`create_desktop_folder`** — Tier *1*, and excluded by hand, because it
  reaches `CoderAgent`, which writes Python and runs it under `subprocess`. Tier
  is about reversibility; this is about what the implementation does. Two
  different questions, so it needs its own flag.

**A generated answer says it is generated.** New evidence variant
`ModelAnswered` — it witnesses that a named model replied, and explicitly
nothing more: not that the answer is true, not that anything was looked up.
Replies are prefixed 💭. `CognitiveResponseDict.__bool__` is why: it returned
`True` unconditionally and overwrote every failed dispatch with a fabricated
"🤖 Cognitive Response" success.

**Four things worth knowing:**

1. **The Ollama GUI installer does not work here.** `OllamaSetup.exe
   /VERYSILENT` exits **1**, writes no log, logs no CodeIntegrity event, and
   installs nothing — with a valid EV signature and SAC not objecting. **Use the
   standalone ZIP**: extract to `%LOCALAPPDATA%\Ollama`, run
   `ollama.exe serve`. No installer, no service, no admin, and uninstalling is
   deleting a folder. `ollama.exe` itself runs unimpeded.
2. **Stage 3 is off in the test suite, and had to be.** `pytest.ini` allows
   `127.0.0.1` through `--block-network` because the API tests need it — and
   Ollama listens there. On a machine with a model running, the suite would have
   consulted it, and `xyzzyspoon12345` (in `DEMO.md`'s honest-failure act, which
   must fail) gets answered cheerfully by a language model. The suite would then
   pass or fail depending on whether a developer had a server up. `conftest.py`
   sets `MONDAY_LLM=off` for every test that is not marked `@pytest.mark.llm`.
3. **`reports/routing_evidence.py` sets `router.llm = None`, deliberately.** The
   published 1.000 is a claim about the *deterministic* stages. Leaving stage 3
   in would make it depend on whether a server was running when the report was
   generated — and the negatives would stop meaning anything, because a model
   will happily find a plausible skill for "determination is important".
4. **`Client.list()` changed shape and the bug was silent.** ollama-python 0.6
   returns a pydantic `ListResponse`; reading it as a dict raises
   `AttributeError`, which `available()` catches as "no server". The stage would
   have reported itself permanently unavailable on every machine, blaming Ollama.
   `_model_names` handles both shapes and a test asserts both.

### 2026-08-16 (later) — what the live model actually did

The stage was written against a stub and then run against `llama3.2:3b` for the
first time. Four results, and the third changed the design.

| Typed | Reached | Verdict |
|---|---|---|
| `could you check how much charge is left please` | stage 3 → `battery_status`, **1.7 s** | the win — no pattern covers that phrasing |
| `I need to know what programs are eating my memory` | **stage 2** → `recall_memory` | wrong, and not stage 3's fault — see below |
| `shut down chrome for me right now` | stage 3 → `open_app_or_website` → **launched Chrome** | the opposite of the request, performed without asking |
| `make me a python script that deletes my temp files` | stage 3 → `organize_folder` | wrong, harmless, and it returned an empty message |

**A guess may answer, but it may not act.** The Tier-2 gate was never violated —
nothing irreversible was reached, and `create_desktop_folder` was never selected
— and that was not enough. *Reversible* and *wanted* are different properties.
Closing a browser is reversible; opening one you asked to close is still wrong.

So `Skill.read_only` was added, defaulting to **False**, and a stage-3 selection
of anything not marked read-only is now **proposed rather than performed**:

```
> shut down chrome for me right now
💭 I think you mean: Open an application or a website (target=chrome)
  I worked that out rather than recognising it, so — shall I? Reply 'yes' or 'no'.
> no
Alright — I haven't run open app or website.
```

26 skills are annotated read-only and run straight away; the other 25 ask. A
**pattern** match is unaffected — patterns are exact, and this only ever
qualifies a guess. It is deliberately *not* routed through
`require_tier2_approval`: that gate's executor table is a closed list of names
on purpose, and widening it to "any skill" to reuse the prompt would dissolve
the property that makes it trustworthy. This asks a different question — *did I
understand you?* rather than *may I do something you cannot undo?*

**Two other things the live run exposed, neither of them stage 3's doing:**

1. **Stage 2 is greedier than it looks.** "what programs are eating my memory"
   was classified `memory_query` — on the word *memory*, meaning RAM — at above
   the 0.50 floor, so stage 2 claimed it and stage 3 was never consulted. The
   classifier is doing exactly what it was trained to do; the corpus has no
   sense that "memory" is ambiguous. A candidate fix is to let stage 3 see
   stage-2 selections it disagrees with, but that inverts the cascade and needs
   its own thought.
2. **The first call pays for loading 2 GB of weights.** `CHOOSE_TIMEOUT = 30 s`
   was applied to every call, so the *first* command after startup was the only
   one that failed — the worst shape a defect can have, because it reads as
   flakiness. `FIRST_CALL_TIMEOUT = 180 s` covers the cold start and drops to 30 s
   once a call has returned. Warm, the model picks a skill from the 49-tool
   schema in **0.8 s**.

**Installing it, for the record.** The GUI installer is a dead end here (above).
The ZIP works and needs no install:

```bash
%LOCALAPPDATA%\Ollama\ollama.exe serve      # then, once:
%LOCALAPPDATA%\Ollama\ollama.exe pull llama3.2:3b
```

The pull failed twice at ~88% with `no such host` on Cloudflare R2 — transient,
DNS resolved fine when tested directly, and a re-run resumes from the partial.

### 2026-08-16 (later still) — streaming (ROADMAP Phase 5)

`POST /agent/stream` reports the pipeline as it runs: `classified` →
`consulting_model` → `token`* → `result`, with a `heartbeat` every 10 s.

**It is the same pipeline, observed.** `process_command` took an optional
`on_event` sink and is otherwise unchanged; the endpoint runs it on a thread and
drains a queue. A parallel streaming implementation would have had to agree with
this one about the Tier-2 gate, the clarification state machine and the RL
credit — and two implementations that must agree is the defect this repo has
found in its own code repeatedly. `test_streaming.py` asserts the streamed and
executed results are identical, and that the Tier-2 gate still arms through the
stream.

**The planned benefit did not materialise; a better one did.** The premise was
"first token in ~1 s beats a complete answer in ~8 s". Measured: with a 49-tool
schema, `llama3.2:3b` picks a tool for essentially every command and writes free
text almost never, and a warm selection takes 0.8–1.7 s regardless. The token
path is built and tested but rarely fires.

What mattered instead: **`ui/index.html` aborted every request after 15
seconds.** A cold model load is a minute or more, so the first LLM-routed
command a user ever typed was cancelled before it could answer — they saw
"Execution request timed out" and no explanation. There is no fixed deadline
now; the UI gives up only after 45 s of *silence*, and the heartbeat keeps
"slow" distinguishable from "dead".

**Two things worth knowing:**

1. **A test double drifted and it was worth catching loudly.** `StubLlm.choose`
   did not accept the new `on_token`, so seven tests failed with `unexpected
   keyword argument`. That is the useful failure — a stub swallowing `**kwargs`
   would have kept passing while testing a call the router no longer makes.
   `test_the_stub_still_matches_the_thing_it_stands_in_for` now compares the
   signatures directly.
2. **Two of my own tests were wrong before the code was.** A command that
   reaches stage 3 has to clear *both* earlier stages: "say something about
   mondays" matches the `say {phrase}` voice pattern, and "determination is
   important" clears the 0.50 floor as `memory_query`. Only the third attempt —
   "i need to book a flight" — actually reached the model.

Verified in a real browser at `/app`: the status line shows "asking the local
model (llama3.2:3b)… first run loads it, which is slow", is replaced by the
result, and the proposal flow (`shut down chrome` → decline) works end to end
with no console errors.

### 2026-08-17 — the suite was opening browser tabs on the user's machine

**Reported by the user: "when you test, I could only see mail tabs opening."**
They were right, and it had been happening on every run for as long as the email
tests existed.

`CommunicationAgent.draft_email` calls `webbrowser.open(gmail_url)` for every
draft it writes — *"also launch browser tab for visual inspection"*.
`test_email_and_whatsapp_ux.py` drafts seven times, `DEMO.md`'s Act 5 once more,
and several other tests besides, so a full run stacked up Gmail compose tabs on
their desktop.

Why *mail* specifically, and nothing else? Because email was the one thing
escaping the process. Everything else was already intercepted — that is the
whole reason the leak was invisible to me and obvious to them.

This is the **third** time this class of bug has been found here, so it now has
its own file (`tests/test_no_side_effects.py`):

1. The volume tests drove the real speakers and left the machine muted →
   `fake_powershell`.
2. The suite wrote 2,196 rows into the user's real assistant memory, and got
   slower every run as a result → `_isolate_memory_db`.
3. This.

**Three ways out, not one.** The first fix intercepted `webbrowser.open` only —
which would have left WhatsApp still launching, because a `whatsapp://` deep
link goes through `os.startfile` on Windows. Writing the fixture against the
reported symptom is how a bug survives its own fix.

**And the obvious fix was too broad.** Patching `subprocess.Popen`
unconditionally broke nine `test_voice_ui.py` tests, because `subprocess.run` is
*implemented on top of* `Popen` and those tests run the shipped `Voice` object
under node. Only the PowerShell `MessageBox` — the one command that puts a
window on screen — is intercepted; everything else is delegated to the real
`Popen`.

**Left alone deliberately:** whether `draft_email` should open a tab at all.
Doing it the instant a draft is written, before the user has confirmed anything,
is arguably too eager given the UI already offers an explicit "Open Pre-Filled
Gmail Web Composer" button. That is a product decision and wants its own change.

### 2026-08-17 — conversation memory (ROADMAP Phase 6)

**Contacts are a typed table.** `memories.db` gained a `contacts` table (name
unique, case-insensitive, plus phone, email, source). `_resolve_phone_number`
now reads: the number the user typed → the contacts table → the legacy
similarity search behind its four guards. The guards stay, because contacts
taught before this change live in `memories` and dropping that path would lose
them; they are simply no longer the only defence. A lookup that reads the
contacts table **cannot** return a conversation transcript, because transcripts
are not in that table — structural rather than careful, and structural answers
do not have to be remembered by the next person.

**Short-term context.** The last six messages go to stage 3 and nowhere else.
Replies are truncated to 300 characters first: a `history` listing is thousands
of characters, and spending a 3B model's context on an answer it already gave
crowds out the 12 KB tool schema it actually needs.

**The result, measured:**

```
> message papa saying I'll be late   → pattern → message_contact ✓
> and tell mum too                   → stage 3 → message_contact, slots={'rest': 'I'}
```

Right skill, wrong argument. The follow-up reaching `message_contact` at all is
the context doing real work — it names no action and no recipient, and stages 1
and 2 are stateless by design. Resolving the ellipsis into *arguments* is past
what a 3B does reliably. Adding a follow-up rule to the system prompt was tried
and **made it worse** (the model then chose no tool at all), so it was left
alone. It fails safely: the Phase 4 proposal gate shows `rest=I` and the user
declines.

**Two isolation bugs I caused and fixed:**

1. `save_contact` bypassed the `no_memory_writes` stub in `test_whatsapp.py`,
   which only covered `remember`/`recall`. The contacts table is session-scoped,
   so "papa" taught by one test was still known in the next, and the test
   asserting an *unknown* contact prompts for a number found one saved.
2. My own `test_conversation_memory.py` saved a contact named "Bhumi" to
   demonstrate case-insensitive lookup, which broke two `test_whatsapp.py` tests
   that assert a negative about that name. Those tests are about the *legacy*
   guards, so they now stub the contacts table out via `no_saved_contacts` —
   more honest than renaming the fixture data, because it says what they are
   actually testing.

### 2026-08-17 — voice, offline both ways (ROADMAP Phase 7)

Two seams: `voice/tts.py` and `voice/stt.py`. Both report **which engine** did
the work, because "MONDAY has a voice" says nothing useful when there are three
possible sources and two are usually absent.

**Verified end to end, offline:**

```
said : 'what is the battery level'
heard: 'what is the battery level'      vosk, offline=True, 2.3s
```

- **TTS**: Piper (if `MONDAY_PIPER_VOICE` is set) → `pyttsx3` → `TTS_UNAVAILABLE`
  naming what to install. Piper is **not** in `requirements.txt`: GPL-3.0 is a
  licence decision, not a dependency choice. Set the env var and it is used.
- **STT**: Vosk against the raw PCM already in memory — no WAV round-trip, so no
  decoder and no FFmpeg (the wall XTTS died on). Falls back to Google Web Speech
  and records `offline: False` when it does. Model is ~40 MB, **gitignored**,
  from https://alphacephei.com/vosk/models into `models/vosk-model-small-en-us`.
- **`speak` waits now** and returns `FileWritten` plus the engine name. It used
  to start a thread and return `TaskQueued` — "a thread exists" — which is true
  and nearly useless.

**The double-speak rule is finally explicit.** `MasterPlanner.enable_voice`
defaults to **False**; `cli.py` sets it True. The desktop UI speaks in the
browser and has barge-in, echo suppression and a wake word that were verified on
the real machine — if the backend also spoke, every reply would be said twice.
That defect was "fixed" last time by the accident of no engine being installed.
Phase 7 ends the accident, so the rule had to be written down and tested.

**Three things this broke, and all three are the same lesson:**

1. **The suite went 68 s → 482 s and became audible.** `speak` waiting, plus
   `pyttsx3` newly installed, meant real SAPI5 synthesis and `pygame` playback
   on every speaking test. `no_audio_output` fakes synthesis into `tmp_path`
   with real bytes, so `FileWritten` is still exercised rather than bypassed.
   Tests *about* `voice/tts.py` opt out with `@pytest.mark.real_audio`.
2. **`pyttsx3` pulls `pywin32`, which woke a dormant path.**
   `scan_outlook_com_contacts` became importable, and it used
   `win32com.client.Dispatch` — which **starts Outlook** when it is not running,
   then enumerates the whole Contacts folder. One test: **181 seconds**. Now
   `GetActiveObject`, which attaches to a running instance and raises otherwise.
   Starting a mail client to answer "what is bob's email" is not something an
   assistant should do unasked. **This is very likely part of what the user saw
   as "mail tabs opening".**
3. **"This code never runs here" is a claim about the environment, not the
   code.** Both of the above were inert for weeks purely because a package was
   missing.

**A correction to ROADMAP.md:** it said `voice/tts_bridge.py` "already exists as
the seam". It does not — that is a standalone CLI script for the abandoned XTTS
venv, and is the record of that attempt. The seam had to be written.

**Still there, still inert:** `TriModelCognitiveEngine` is a second LLM path,
reached after a failed dispatch. Without `GEMINI_API_KEY` it is falsy and
changes nothing, so it was left alone — but two LLM paths is one too many, and
unifying them belongs with ROADMAP Phase 6.

### 2026-08-18 — one language model in the routing path

The last entry ended with "two LLM paths is one too many". There is one now.

`MasterPlanner.process_command` had a hosted Gemini call **directly below the
dispatch**, and it fired when the classifier had fallen back *or* the dispatch
had failed for any reason short of a refusal:

```python
if fallback or (not tool_result.get("success") and not tool_result.get("refusal")):
    llm_response = self.cognitive_engine.generate_cognitive_response(cmd, context_memories)
    if llm_response:
        tool_result = {"success": True, "cognitive_llm": True, "message": "🤖 …"}
```

**Four defects in six lines**, and only the absence of an API key kept every one
of them theoretical:

1. **Generated text reported as work done.** `success: True`, no evidence, no
   `generated` flag. `CognitiveResponseDict.__bool__` was fixed for exactly this
   once; the caller reintroduced it one level up.
2. **`fallback or …`, not `and`.** A command that matched a *pattern* and did
   real work had its evidenced result discarded whenever 2.1 happened to be
   unsure — which is precisely when the pattern, not the classifier, was
   carrying the routing.
3. **It swallowed the stage-3 proposal gate.** `_propose_llm_skill` returns
   `success=False` by design, so "💭 I think you mean… shall I?" was replaced by
   an unrelated answer while `pending_clarification` stayed armed. The user's
   next "yes" would have answered a question they were never shown.
4. **It left the machine.** Stage 3 is local; this was not.

Stage 3 (`core/llm.py`) is now the only language model in the routing path.
`self.cognitive_engine` is gone from the planner — structurally, not by comment
— and `TriModelCognitiveEngine` survives as a re-export for the two *generation*
call sites that still use it: code synthesis in `agents/coder_agent.py` and
document Q&A in `agents/document_agent.py`.

**A capability moved rather than being deleted with the path.** The removed call
was handed `get_contextual_memories(cmd)`; stage 3 was not. So `LlmStage.choose`
now takes `memories` and renders them with `memory_context()` as their **own**
system message — the containment instructions and the user's data are never one
editable string — placed before the conversation turns. Rows whose topic is
`conversation_history` are excluded: `recall` reads one table that holds both
kinds of row, and offering a transcript as a remembered fact is the same error
the contacts lookup made before it got its own table.

**Two credential defects found in the same corner**, both live in the paths that
remain (`tests/test_gemini_credentials.py`, 6 tests):

- `load_gemini_api_key` accepted **`OPENAI_API_KEY`** as its third choice, and
  every caller sends the result to `generativelanguage.googleapis.com`. A
  machine with an OpenAI key and no Gemini key handed that key to Google.
- The key was authenticated as **`?key=…` in the URL**, which is the part of a
  request that lands in access logs, proxy history and pasted tracebacks. It is
  an `x-goog-api-key` header now, and the endpoint is defined once
  (`vision_agent.GEMINI_ENDPOINT`) and imported by `core/cognitive.py`.

**The regression tests were mutation-checked**, because a test that passes
against the code it was written for proves nothing and this defect was inert
here. Restoring the override — in the shape a machine *with* a key would run it
— fails four of the new tests independently; restoring `?key=` and the OpenAI
fallback fails two more; dropping the `memories=` argument fails one.

**Three stage-3 doubles had drifted** and only the suite caught them:
`_Streaming` in `test_streaming.py` and `_Recorder` in
`test_conversation_memory.py` did not accept `memories`, and
`test_100_ruthless.py` reached the engine through `planner.cognitive_engine`.
`test_the_stub_still_matches_the_thing_it_stands_in_for` guards *one* stub
mechanically; the other three are hand-written in their own files and are guarded
by nothing but a red suite. Worth generalising if a fourth appears.

**773 → 789 passing, 0 failing, offline, ~105 s.** (The 773 baseline was measured before this change, not quoted from the last entry.)

### 2026-08-18 (later) — /help still said speech needed the network

`/help` ended with *"Spoken replies use gTTS, which needs the network."* That
stopped being true on 08-17: `voice/tts.py` tries Piper, then `pyttsx3` over
Windows SAPI5, and gTTS is in neither path. The menu now names the one setting
that is real — `MONDAY_PIPER_VOICE` for a better voice, SAPI5 otherwise, offline
either way — and `speak` is listed as offline. Still inside the 68-column budget.

The same sentence had spread to three other places, all corrected:
`README.md`'s voice-cloning bullet, the `voice/tts.py` docstring (which claimed
`TTS_UNAVAILABLE` was "the current state of this machine" — `pyttsx3` has been
installed since it was written), and `tests/test_help_command.py`'s own
docstring. gTTS now survives only in `ml/voice_cloner.py`, which the `speak`
skill does not call — checked, not assumed.

**Two tests so it cannot rot back**: the menu may not say `gtts` or "needs the
network" and must name `MONDAY_PIPER_VOICE`; and the two switches the menu
advertises must be the two `voice/tts.py` actually reads. The lesson is the
menu's own history — it once advertised a `mondayvoice.mp3` clone that had been
abandoned. A capability menu that ages badly is worse than no menu, because it
is believed.

**One thing worth knowing for next time.** The first commit of this work was
**refused by `.githooks/pre-commit`**: `tests/test_gemini_credentials.py` used
`sk-proj-…` as a fake OpenAI key, which matches the vendor-token pattern. The
guard was right — a scanner that reads the shape of a token cannot read the
intent behind it, and one that could be argued out of a match would be worth
nothing. The fixture is now `not-a-real-openai-key-…`. Do not reach for
`--no-verify`.

**791 passing, 0 failing, offline, ~87 s.**

### 2026-08-18 (later still) — the corpus was asked what MONDAY cannot hear

Reported: `fetch me latest news` and `tell me price of ifci stock` both came
back "I'm not sure how to do that yet", and — separately — `Set the system
volume to 50%.` did too. **Checked first, before changing anything:** the volume
command was routed identically at `bb388d5`, before this session's commits, so
nothing here had made the app weaker. `set volume to 50` worked then and works
now; the failure was always one word ("system") away.

**The classifier was never the problem.** It called both of the first two
`browser` at 0.92 and 0.94 — confidently and correctly. There is simply nothing
behind that class: `registry.by_intent("browser")` returns **[]**, and only 3 of
49 skills declare an intent class at all, so for four of MONDAY's seven classes
stage 2 is a dead end by construction. Everything depends on stage 1 patterns.

**So the corpus was asked how bad that is.** `reports/massive_coverage.py` puts
all 10,631 real utterances of `data/external/massive_en_us.csv` through the
router — stages 1 and 2 only, because a local model may not be running — and
reports per MASSIVE intent rather than one average:

    OVERALL              30.6%  →  35.3%   (+505 utterances)
    news_query    707     32.0% →  52.9%
    qa_stock      200     42.0% →  57.5%
    audio_volume_mute 156  6.4% →  23.7%
    audio_volume_up   134  9.0% →  27.6%
    audio_volume_down  71 12.7% →  40.8%
    weather_query 848     26.3% →  35.8%
    datetime_query 493    29.4% →  36.7%
    email_sendemail 530   26.6% →  33.4%

Three changes got that:

1. **Two capabilities that did not exist.** `latest_news` (Google News RSS —
   top stories or any topic, publisher named, no summarising of articles it has
   not read) and `stock_price` (Yahoo: search resolves "ifci" → `IFCI.NS`, then
   the chart endpoint gives price and move). Both probed live from this machine
   before a line was written against them; `IFCI.NS` came back ₹80.33. Both are
   read-only, Tier 1, `offline=False`, and fail structurally when the network is
   not there.
2. **Stage 1 retries once with the civilities stripped.** The largest single
   class of miss was "please", "can you", "could you please" and a trailing
   "please" around a command MONDAY already served. The retry runs **only when
   the command as typed matched nothing**, so no existing match or captured slot
   can move — which matters because slots carry email bodies and WhatsApp
   messages. `tests/test_civilities.py` asserts exactly that property.
3. **Patterns widened from the real phrasings**, not from imagination. The
   biggest single lesson: every volume pattern read "turn the volume up" and
   almost nobody says that — they say "turn **up the** volume". Same for
   "what day of the week is it", "is it raining", "do i need an umbrella".

**What the number is not.** Routing is not correctness: an utterance that
reaches `answer_question` counts as routed, and for "tell me the latest news"
that was a Wikipedia lookup of the word "news". The report keeps a `top skills`
column per intent so that stays visible instead of being averaged away.

**Deliberately not done, and why:**

- **`calendar_set` (1,147 rows, 17.8%) and `calendar_query` (793, 27.7%) are the
  biggest pools left** and were left alone on purpose. `schedule_event` is not
  read-only and its patterns capture a title *and* a time; widening them
  carelessly writes junk events into a real calendar. This one wants care, not
  volume.
- **`iot_hue_lightdim` / `lightup` / `lightchange` are still at 0–2%.**
  `toggle_smart_light` only knows on and off, and it reports NOT_IMPLEMENTED
  besides. Reaching an honest refusal is worth something, but not enough to
  write "dim the lights" patterns for a tool that has no dimmer.
- **`olly` is not stripped as a wake word** even though ~1 in 20 MASSIVE
  utterances open with it. It is that corpus's assistant name, not MONDAY's, and
  stripping it would flatter the measurement rather than the app. The measured
  lift is therefore slightly understated, which is the right direction.

### 2026-08-18 (evening) — the 8B, and a pattern that matched but was wrong

**Phase 8, and a correction to my own measurement.** The eval came first on
purpose, and it earned that order twice.

`reports/stage3_selection.py` scores stage 3 on real MASSIVE utterances,
restricted to the ones stages 1 and 2 miss — stage 3 never sees a command a
pattern caught, so including those would measure the patterns and call it the
model. It found, on `llama3.2:3b`, that **five of six share questions went to
`crypto_price`**. "Live cryptocurrency prices" and "Live share price for a
listed company" are both true and neither says *not the other one*, and that
string is the model's whole view of the capability. Sixteen descriptions now name
what they exclude: **59.1% → 64.3%**, same model, same sample, for a text edit.

**Then I got the model comparison wrong and had to withdraw it.** The first run
said the 8B won (67.3% vs 64.9%); the next said it lost (62.0% vs 63.7%). The
cause was mine: `build_set` used **one** RNG walked across intents in sorted
order, so excluding three `datetime_query` utterances reshuffled the sample for
every intent alphabetically after it. The tell was both models moving ±3–4 on
intents whose descriptions had not been touched. Within a run the comparison was
always sound; across runs it was not, which is the entire job of that file. Fixed:
per-intent seed, sample built once and shared by every model, 6 → 12 per intent.

**The 8B is the default now, as a preference order rather than a name.**
`PREFERRED_MODELS = ("llama3.1:8b", "llama3.2:3b", "llama3.2:1b")`, resolved
against what the server reports. Hard-coding the 8B would have taken stage 3
away from any machine that only pulled the 3B — `available()` would say "not
pulled" and go quiet where it used to work. An explicit `MONDAY_LLM_MODEL` still
wins outright, including when it names something absent, because "that model is
not pulled" is more useful than quietly running a different one.

It is resident on the GPU: `offloaded 29/29 layers`, 4.1 GiB VRAM, and the
6.0 GiB RTX 4050 that ROADMAP §0 never looked for. Latency roughly doubles
(p50 1.3 s → 2.3 s) and that figure has been stable across every run.

**Phase 9 — a pattern may match and still be wrong.** `core/slot_sanity.py`:

```
'please organize a meeting with my company workers' -> organize_folder
'book me a flight to delhi on tuesday'              -> schedule_event {'title': 'me a flight to delhi'}
'summarise my last email and reply to it'           -> summarize_document {'path': 'my last email and reply to it'}
```

The first sorts a folder's files because the user said "organize". A parse that
fails its check is declined at stage 1 and the cascade continues — 25 rejections
across the whole corpus, 9 of them to skills that act.

**Rule 2 was scoped by measuring it, not by taste.** Its first version rejected
73, and every one of *its* rejections went to `answer_question`: read-only, a
search, where a clumsy query still answers the question and refusing gives the
user nothing. It now applies only to skills that act. Rules 3 and 4 stay
universal because they predict a guaranteed failure — a file that does not exist
cannot be summarised.

**The price, stated rather than buried:** coverage 35.3% → 35.1%. Precision costs
coverage. A coverage number without a negative set can always be raised by
matching more, so `tests/test_slot_sanity.py` carries both halves.

**864 → 899 passing.**

### 2026-08-18 (late) — the 8B was measured properly, and lost

`PREFERRED_MODELS` is `("llama3.2:3b", "llama3.1:8b", "llama3.2:1b")` again.

The clean run of `reports/stage3_selection.py` — per-intent seed, one sample
shared by both models, 12 per intent — on 339 real utterances that stages 1 and
2 miss:

```
llama3.2:3b   224/339   66.1%   p50 0.7s   p95 0.9s
llama3.1:8b   218/339   64.3%   p50 1.8s   p95 2.2s
```

**1.8 points worse and 2.6× slower.** I had reported the opposite earlier in the
day and withdrew it twice; both earlier runs were unsound for the same reason,
which is worth writing down because it is easy to repeat: `build_set` drew its
sample with **one** `random.Random` walked across intents in sorted order, so
excluding three `datetime_query` utterances reshuffled the draw for every intent
alphabetically after it. Two models then differed on intents whose descriptions
nobody had touched, which is the tell. The seed is per intent now and the sample
is built once and shared.

**Keep two claims apart.** An 8B *fits* on this machine — `offloaded 29/29
layers`, 4.1 GiB of a 6.0 GiB RTX 4050 — and ROADMAP §0's "an 8B model does not
fit at all" was wrong because it measured system RAM instead of VRAM. That
finding stands. Whether it *helps* is a different question with a different
answer: it does not. Conflating the two is how the 8B briefly became the default.

**What actually moved the number in Phase 8 was free.** Sixteen skill
descriptions rewritten to say what they *exclude* took the same 3B from 59.1% to
64.3% — more than the model swap, at no latency cost. The tool schema is
generated from those strings and nothing supplements them, so they are the
model's entire view of what MONDAY can do. That is where the next gain is, not
in a bigger model.

The 8B stays second in the list rather than being removed: a machine that pulled
only the 8B should get stage 3 rather than silence.

### 2026-08-18 (later) — timers, alarms, media keys (Phase 11, tranche 1)

`core/timers.py` and `core/skills_timers.py`. Both categories were dropped from
the corpus for not existing: `datagen/massive.py` refuses an intent MONDAY
cannot serve, and three of its entries read "no alarm or timer exists". The way
to recover those rows was to build the thing, so this tranche did, and moved the
mapping in the same commit — a corpus entry ahead of a capability trains 2.1 on
a promise.

```
alarm_set     254 rows   39.8%   (previously not in the corpus at all)
alarm_query   182 rows   26.4%
alarm_remove  113 rows   23.0%
```

**What is honest about a timer here:** it is a thread in this process. It rings
while MONDAY runs and not otherwise, the confirmation says so, and one that came
due while the app was closed is reported as **missed** rather than fired late or
dropped. `data/timers.json` is what makes that possible across a restart.

**Media keys are keystrokes, not a music player.** `KeypressSent` is the whole
claim: a key was sent, and nothing here can see which app received it or whether
anything was playing. "Play some jazz" therefore still refuses — `play_music`
stays in `MASSIVE_DROPPED` with a reason rewritten to say precisely that.

**Two defects found on the way, both on the critical path for this work:**

1. **`send_desktop_notification` built a PowerShell command by f-string.** A
   body containing `"); …; ("` broke out and executed — demonstrated before
   fixing. `notify me <text>` is user-facing and a timer label flows there too.
   The strings travel as environment variables now and never enter the script.
   The same function also returned `success: True` on non-Windows having shown
   nothing, and carried no evidence.
2. **The cached classifier never noticed the corpus had changed.**
   `get_trained_classifier` retrained only when `intent_classifier.joblib` was
   *missing*, so regenerating the corpus (which this tranche did) left a model
   trained on the old one loaded silently — the new capability would be in the
   patterns and invisible to 2.1. It stores a content fingerprint now and
   retrains on a mismatch. Same shape as the stale
   `intent_classifier_comparison.csv` that `tests/test_evidence_index.py` exists
   for.

**Corpus regenerated:** MASSIVE re-derived (11,180 rows, up from 10,631),
`datagen.generate` re-run (17,488 rows), 2.1 retrained automatically by the
fingerprint check. **Coverage 35.1%** — the same figure as before the tranche,
but not the same measurement: 549 rows entered the denominator, so the honest
comparison is per intent, and the alarm rows went from absent to routed.

**921 → 973 passing.**

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
- ~~**Test suite: 276 passed, 1 failed**~~ and ~~**several tests depend on live
  third-party APIs**~~ — **both FIXED 2026-08-08 in UPGRADE_PLAN Phase 1**, and
  these two bullets sat here stale for a week afterwards, which cost a later
  session real time. The suite is **687 passing, 0 failing, offline, ~75s**;
  cassettes replay the HTTP, `--block-network` is on by default, and the four
  genuinely-live tests are `@pytest.mark.network` and deselected. A red suite
  now means a regression.
- ~~**Offline demo path + rehearsed script**~~ — DONE 2026-08-15. `DEMO.md`, and
  `tests/test_demo_script.py` executes it with sockets blocked.
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
- ~~**2.1 leans on stopwords**~~ — MEASURED 2026-08-15, and the finding holds:
  71% of the top-8 attributions are function words, 0% with `stop_words="english"`,
  at **no cost** to the paraphrase (generalisation) figure. Still deliberately
  **not** adopted — see the 2026-08-15 entry above and
  `reports/2_1_stopword_counterfactual.md`. The recommendation for anyone
  continuing it: **the corpus is the thing to change, not the vectoriser.**

### Suggested order for the remaining work

**Rewritten 2026-08-18.** The first two items on the previous version of this
list had both been done for a day — voice by ROADMAP Phase 7 on 08-17, the typed
`contacts` table by `15c6f6d` on the same day — and this file's own header warns
that stale items here cost a later session real time. They did. What is actually
left, roughly by value:

1. **The corpus, per the stopword finding above.** `document_intel` gets nothing
   from MASSIVE and `chitchat` almost nothing, so those two classes are still
   effectively synthetic-only and are the least well evidenced of the seven.
   This is the largest remaining piece of work and the one with a number
   attached to it.
2. **The two Gemini paths that are left.** `agents/coder_agent.py` (code
   synthesis) and `agents/document_agent.py` (document Q&A) still call
   `TriModelCognitiveEngine` — hosted, and duplicating a local model that is now
   wired and tested. Both are inert without a key, which is exactly what made
   the third one survive as long as it did. Point them at `core/llm.py` or
   delete them; do not leave them as they are on the grounds that they do not
   run here.
3. **`/help` in the WebGL console pane** — the width-budget item above; still
   never actually looked at in the app.
4. **A mechanical guard for the stage-3 doubles.** `StubLlm` is checked against
   `LlmStage.choose` by signature; `_Streaming` and `_Recorder` are not, and both
   broke silently when the signature grew a `memories` argument.

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
