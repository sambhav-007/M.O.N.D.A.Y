# M.O.N.D.A.Y — Session Handoff

_Last updated: 2026-08-07. Machine: Windows 11 Home, user `sambh`._

> **Read this first.** `README.md` § *Status & Known Limitations* is the
> authoritative statement of what works and what does not. This file is a running
> log and parts of it age badly — several items below are struck through because
> they turned out to be stale or simply wrong.

## 0. Changes 2026-08-07

| Area | Change |
|------|--------|
| Secrets | Pre-commit guard in `.githooks/` blocks staging `.env` or a real secret value. Enable per clone: `git config core.hooksPath .githooks`. **Verified: no credential was ever committed** — `.env` is untracked and the password appears in no blob on any ref. |
| Ignores | `logs/`, `*.log`, `.env.*` (keeping `.env.example`), and `data/calendar.json` (untracked). |
| **2.6 XAI** | Rewritten to compute **exact Shapley values in closed form** — `shap` is uninstallable here (§8). Verified bit-for-bit identical to `shap.LinearExplainer`. Emits 2 CSVs + 3 figures. Fixed a fabricated `explain_command_intent()` that was live on an API endpoint. |
| **Tier-2 gate** | Now genuinely enforced (PRD §9). See the resolved note in §2c. |
| Docs | README / PRD / MONDAY_ACADEMIC / PROJECT_PLAN reconciled against the code. |
| Tests | 169 passing (28 new for the Tier-2 gate). |

## 8. Environment constraints discovered 2026-08-07

- **`shap` cannot be installed.** It hard-imports `numba`. numba 0.66 (the only
  build supporting `numpy>=2.3.5`, which `mlxtend`/2.4 requires) is blocked by
  Smart App Control; numba 0.61.2 loads but pins `numpy<2.2` and breaks `mlxtend`.
  No version satisfies both. Do not retry — see `reports/2_6_shap_equivalence.md`.
- **Known-good env:** numpy 2.5.1, pandas 2.3.3, sklearn 1.9.0, scipy 1.18.0,
  mlxtend 0.25.0, starlette 1.3.1. Check with `py -3.12 -m pip check`.
- **SAC blocks lift over time.** pandas 3.0.5 was blocked on 2026-08-06 and
  imported fine on 2026-08-07. Reputation-based blocks are not permanent.
- **`app.routes` is unreliable for introspection** in FastAPI 0.140.13 — routes
  added via `include_router` do not appear there but *do* serve. Use
  `app.openapi()['paths']`, or the endpoint will look missing when it is not.

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
> Tier-2 surface was `send_email` and `terminate_process`. See PRD §3.

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

Recent history:

```
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

Still untracked, verify before committing: `voice/`, `ui/_monday_ref_22k.wav`, `handoff.md`.

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
- **Test suite: 169 passed, 0 failed** (2026-08-07). The previously-failing
  `test_agent_public_api_fetch_iss_location` now passes — that network recovered on
  its own; nothing was changed to fix it. It will fail again whenever
  `api.open-notify.org` is unreachable, which is the point of the marker item below.
- **Several tests depend on live third-party APIs** (DuckDuckGo, open-notify,
  CoinGecko) and so fail whenever those are down or rate-limiting. Worth marking them
  `@pytest.mark.network` so a red suite means a real regression.
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

---

## 7. Quick verification commands
```bash
# regenerate synthetic datasets (uses datagen/)
py -3.12 -m datagen.generate

# run the ML test suite
py -3.12 tests/test_ml.py -v

# start API only (no GUI)
py -3.12 -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```
