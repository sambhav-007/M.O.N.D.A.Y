# M.O.N.D.A.Y — Session Handoff

_Last updated: 2026-08-08. Machine: Windows 11 Home, user `sambh`._

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

## 9. WhatsApp (added 2026-08-08)

WhatsApp has **no API a desktop script may send through**. The deep link
(`whatsapp://send?phone=…&text=…`) opens a chat with the message pre-typed but
deliberately will not send it. Simulating the Enter keypress is the only route,
so that is what the approved path does.

- **Any message with text is Tier-2 gated**, then sent for real: it shows the
  message, asks *"Send it?"*, and on `yes` opens the chat and presses Enter.
- A command with no text just opens the chat (Tier 1 — nothing to send).
- Numbers default to **+91** (`DEFAULT_COUNTRY_CODE` in `.env`). Lengths are
  validated, not merely bounded.
- Unknown name → asks for the number, saves it as `<name>'s number`, and resumes
  the message that was originally asked for.
- Needs optional `pyautogui`; without it the chat still opens pre-filled and it
  says which part it could not do.

**Two things that must not drift:**

1. It reports that **Enter was pressed**, never that the message was delivered.
   Nothing here can read WhatsApp back, and the keypress goes to whatever window
   has focus.
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
- **Speaking (current)**: UI uses the browser's robotic `speechSynthesis`; backend
  `speak()` uses gTTS. Neither uses the `ui/mondayvoice.mp3` voice.
- **Replies are still spoken twice** — once by the UI's `speechSynthesis` and once by
  the backend's gTTS through pygame, in two different voices. Collapsing to one is a
  behaviour choice: backend-only keeps `cli.py` talking but needs network; UI-only is
  instant and offline but silences the CLI.
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

Still untracked and undecided: `voice/` and `ui/_monday_ref_22k.wav`. The `.wav`
is a resampled copy of the voice reference made for the abandoned XTTS work and
is probably deletable.

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

Still untracked and undecided: `voice/` (contains `tts_bridge.py`) and
`ui/_monday_ref_22k.wav`. The `.wav` is a resampled copy of the voice reference
made for the abandoned XTTS work (§5) and is probably deletable.

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

- ~~**Intent classifier ~99.8% accuracy**~~ — FIXED 2026-08-03. Now sourced from
  `datagen/`; LR/SVM 0.929, RF 0.920, KNN 0.919, DT 0.761 macro-F1.
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
3. **Voice double-speak** — collapse to one path (UI-only is offline and instant
   but silences `cli.py`; backend-only keeps the CLI talking but needs network).
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
`message 9876543210 saying hi` (Tier-2 → sends)

Everything above works offline. Avoid `search …`, `research …`, `weather …`,
`bitcoin price` and `iss location` on an unreliable network — those are the ones
that stall.
