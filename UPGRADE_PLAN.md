# M.O.N.D.A.Y — Upgrade Plan

_Written 2026-08-08, after reading `handoff.md`, `README.md` § Status, and the code._

## 0. What "100× better" actually means here

The project does not have a feature problem. It has ~13.6k lines, 11 agents, 24
endpoints, 6 ML components and 276 tests. Adding a twelfth agent multiplies
nothing.

What it has is a **trust problem in three specific places**, and every one of
them is fixable by adopting a pattern that a mature open-source assistant
already solved:

| Problem | Symptom today | The 100× lever |
|---|---|---|
| The ML is decorative | `predict_intent()` runs on every command, then `_dispatch_to_agent` ignores it for ~350 lines of `if "volume" in cmd_lower` | Make intent + slots the **only** path to a handler |
| Handlers can lie | Three registry tools still fabricate success (§1) | A typed result contract that **cannot express** "success with no evidence" |
| Nothing is reproducible | Suite takes 117–301s, sometimes >600s, and goes red because open-notify is down | Record/replay cassettes; green offline in <20s |

Everything below serves those three. Ordered so each phase makes the next one
cheaper to verify.

---

## 1. Defects found while reading (new — not in `handoff.md`)

These are in addition to the outstanding items the handoff already tracks.

### 1.1 The RL bandit credits the wrong arm — `core/planner.py:488,490`

```python
if tool_result.get("success", False):
    self.rl_bandit.update(ROUTING_ACTIONS.index("direct_dispatch"), 1.0)
else:
    self.rl_bandit.update(ROUTING_ACTIONS.index("direct_dispatch"), -1.0)
```

The arm actually pulled is `action_idx` (line 470). The reward always goes to
`direct_dispatch` regardless. So component 2.5 learns nothing about the arms it
selects — the Q-value of every other action never moves from its initial value,
and `argmax` is decided by initialisation, not by experience. This is a
correctness bug **inside a graded ML component**, and it is a two-line fix:
carry `action_idx` forward and update *that* index.

### 1.2 Intent classification is load-bearing for almost nothing — `core/planner.py:1480+`

`_dispatch_to_agent(command, intent, user_approved)` receives `intent` and then
runs roughly 300 lines of substring tests before `intent` is consulted at all
(first real use is `intent == "chitchat"` at line 1811, then `"document_intel"`,
`"communication"`). By then most commands have already been routed by
`"volume" in cmd_lower`.

Consequence: the published **0.929 macro-F1 describes a model that does not
decide much**. Fixing this is the single highest-value change in the repo, and
it is also the strongest CLO04 story available — it converts an offline
classifier metric into an *end-to-end routing accuracy* you can measure.

### 1.3 A pending Tier-2 confirmation can be silently discarded — `core/planner.py:448`

```python
if any(k in cmd_lower for k in ["screen", "where", "weather", "who", "what",
                               "search", "open", "capabilities", "tell me",
                               "how", "show", "bitcoin", "crypto"]):
    self.pending_clarification = None
```

`require_tier2_approval` stores the armed gate in `pending_clarification`
(line 841). So if the user answers a *"Send it?"* prompt with anything
containing "what" or "show", the gate is dropped **with no message saying so**.
It fails closed — nothing is sent, which is the right direction — but the user
is not told the action was cancelled, and a later "yes" then answers nothing.
`/help` was given an explicit carve-out for exactly this hazard at lines
421–429; this path never got one.

### 1.4 Three registry tools still fabricate success — `core/tool_registry.py`

The handoff records a campaign against fabricated success (coder agent, comms
agent, cognitive `__bool__`, DDG 202). It did not reach `ToolRegistry`:

- **`read_latest_email`** (line 182) — if `data/google_token.json` exists,
  returns a hardcoded `{"subject": "Project Monday Status Update", "sender":
  "team@monday.ai"}` and `"✓ Fetched latest inbox email via Gmail OAuth."` It
  reads no inbox. It checks that a *file exists* and invents the contents.
- **`change_volume`** (line 166) — the f-string `SendKeys([char]174)*50` never
  interpolates `level`, then returns `"✓ System volume adjusted to {level}%."`
  Asking for 20% and asking for 90% do the identical thing.
- **`toggle_smart_light`** (line 263) — returns `success: True` and
  `"✓ Smart Home IoT: Turned '…' ON."` with no device, no protocol, no I/O. The
  entire "Pillar 5: IoT & Smart Home Automation" is this function.

Under the §2 contract below these three become structurally impossible to write.

---

## 2. The architecture change

### 2.1 Replace the keyword chain with a three-stage router

This is the Mycroft/OpenVoiceOS pipeline shape, which exists precisely because
every assistant grows the same 500-line `if/elif` and then has to escape it.

```
command
  │
  ├─ Stage 1  DETERMINISTIC   padacioso patterns → intent + typed slots
  │            "send mail to {addr} subject {subj} body {body}"
  │            high precision, zero ambiguity, no model needed
  │
  ├─ Stage 2  STATISTICAL     component 2.1 classifier → skill *family*
  │            then family-local patterns, or the family's fallback handler
  │            ← this is where 0.929 macro-F1 finally does work
  │
  └─ Stage 3  GENERATIVE      local LLM (optional) → structured tool call,
               validated against the skill's pydantic schema before it runs.
               Never free text that gets executed.
```

Stage 1 handles the demo-critical commands deterministically (so a live demo
never depends on a model or a network). Stage 2 makes 2.1 load-bearing.
Stage 3 closes the "no conversational memory" gap the README admits to.

**Why `padacioso` and not more regex:** it is pure Python, Apache-2.0, and one
dependency (`simplematch`) — no compiled wheels, so **no Smart App Control
risk**. It gives typed slots (`{count:int}`), optional segments `[please]`, and
alternation `(send|message|text)` in a declarative file, and it is a drop-in for
the neural Padatious if you later want to swap up. It replaces the
`_parse_email_command` / `_parse_whatsapp_command` / `_clean_wa_target` /
`_WA_NAME_VERB_RE` cluster in `planner.py` with data.

### 2.2 A skill contract that cannot fabricate

Every handler returns a pydantic model, not a bare dict:

```python
class AgentResult(BaseModel):
    ok: bool
    message: str
    evidence: Evidence | None = None   # required when ok is True
    error_code: str | None = None      # required when ok is False
    data: dict = {}

    @model_validator(mode="after")
    def _no_unwitnessed_success(self):
        if self.ok and self.evidence is None:
            raise ValueError("ok=True requires evidence")
        ...
```

`Evidence` is a small union: `ProcessExit(returncode, stdout)`,
`HttpResponse(status, url)`, `FileWritten(path, bytes)`, `SmtpAccepted(server,
response)`, `KeypressSent(window_title)`. Note the last one — it lets WhatsApp
keep saying honestly *"Enter was pressed"*, which the handoff correctly insists
must never drift into *"delivered"*.

Then one test enforces it across the whole surface:

```python
@pytest.mark.parametrize("skill", all_skills())
def test_no_skill_can_claim_success_without_evidence(skill): ...
```

The three fabrications in §1.4 fail this test on day one. So does any future
one. This is the mechanism that stops the pattern rather than fixing instances
of it — and it is worth noting the pattern has recurred at least six times in
this repo's history.

### 2.3 Typed memory, not similarity search over everything

The handoff's §9 note is the important one: `memory_agent.recall` is TF-IDF
*similarity*, so it once addressed a WhatsApp message to a phone number lifted
from an unrelated saved transcript. The four guard conditions added afterwards
are correct and must stay — but they are a filter bolted onto the wrong data
model.

The fix is a schema: `contacts(name, phone, email, source, created_at)` as its
own table, queried exactly, separate from `conversation_turns`. A contact
lookup then cannot return a transcript, because it does not read that table.
Semantic search stays for what it is good at ("what did I say about the demo"),
over conversation turns only.

Vector search (`sqlite-vec` + `fastembed`) is a *later, optional* upgrade to the
semantic half. It is not the fix for the misdirection bug and should not be sold
as one.

---

## 3. Open-source projects to draw on

Assessed against this machine's real constraints: Smart App Control blocks
freshly-published binaries, FFmpeg is blocked outright, 16.4 GB RAM with ~3.4 GB
free right now.

| Project | Solves | How to use it | SAC risk |
|---|---|---|---|
| [OpenVoiceOS/padacioso](https://github.com/OpenVoiceOS/padacioso) (Apache-2.0) | §1.2 the keyword chain | **pip dependency.** Intent files under `skills/*/intents.yaml` | **None** — pure Python |
| [OpenVoiceOS/ovos-padatious-pipeline-plugin](https://github.com/OpenVoiceOS/ovos-padatious-pipeline-plugin) | Fuzzier phrasing later | **Pattern only** — copy the cascade design, not the code (it needs `fann`) | n/a |
| [kiwicom/pytest-recording](https://github.com/kiwicom/pytest-recording) + [vcrpy](https://vcrpy.readthedocs.io/) | The #1 item in the handoff — flaky live-API tests | **pip + `@pytest.mark.vcr`.** Cassettes committed; `--block-network` in CI | Low, pure Python |
| [rhasspy/piper](https://github.com/topics/piper-tts) (`pip install piper-tts`) | Kills the gTTS network dependency **and** the double-speak | Backend TTS behind `voice/tts_bridge.py` | **Medium** — ships ONNX binaries. Test before committing |
| `pyttsx3` (SAPI5 via COM) | Guaranteed-offline TTS fallback | Fallback when Piper is unavailable/blocked | **Very low** — uses Windows' own COM voices |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Offline STT; removes the Google Web Speech round-trip | Feed `sounddevice` PCM **as a numpy array** — this is the path that needs no FFmpeg | **Medium** — CTranslate2 binaries |
| [Leon](https://github.com/leon-ai/leon) (MIT) | Skill packaging | **Design reference.** Its skill folder layout (`skill.json` + handler + intents) is the shape to copy | n/a — do not vendor, it's Node/Python hybrid |
| [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter) — [SAFE_MODE.md](https://github.com/OpenInterpreter/open-interpreter/blob/main/docs/SAFE_MODE.md) | Validating the Tier-2 gate | **Design reference.** Confirm-before-execute, `auto_run` as the explicit opt-out. Your gate is already close; cite the convergence in the CLO01 write-up | n/a |
| [Ollama](https://ollama.com/blog/tool-support) + `llama3.2:3b` / `qwen3` | "No conversational memory (no LLM)" | Stage 3 only. Local, no API key, no data leaves the box | Installer is signed; verify once |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) + `fastembed` | Better semantic recall (optional) | Phase 5, over conversation turns only | Medium — loadable extension |

**Do not vendor source files from any of these.** Everything above is either a
pip dependency or a design to copy. Vendoring Leon's or Open Interpreter's code
into an academic submission creates a licensing and authorship problem that is
not worth the small amount of code it would save.

---

## 4. Phases

Each phase is independently shippable and ends green.

### Phase 1 — Make the suite tell the truth ✅ **DONE 2026-08-08**

Result: **308 passing, 0 failing, offline, ~70s**, green on three consecutive
runs (was 276 + 1 network-dependent failure, 117–301s). Both §1.1 and §1.3 are
fixed and covered. Two deviations from what was written below, both recorded in
`handoff.md`: the target was "under 20 seconds" and the honest number is ~70s,
and 4 tests are marked `network` rather than cassetted — 3 because the upstream
service was down or rate-limiting when recording (a cassette taken from an outage
pins the outage), and 1 because it reaches the network through a **subprocess**,
which `--block-network` cannot see.



The handoff already names this as the top task; it is also a prerequisite for
trusting any later phase.

1. `pytest-recording` + cassettes for DuckDuckGo, open-notify, CoinGecko,
   Open-Meteo, Wikipedia, IP-API.
2. `pytest.ini`: `addopts = --block-network`; live tests get
   `@pytest.mark.network` and are opt-in.
3. Fix §1.1 (bandit arm) and §1.3 (silent gate drop) — both small, both with a
   regression test.

**Done when:** `pytest -m "not network"` is green **with the Wi-Fi off**, in
under 20 seconds, on three consecutive runs.

### Phase 2 — The result contract ✅ **DONE 2026-08-08**

`core/contracts.py` exists and is enforced. **All 11 agent modules** plus
`core/tool_registry.py` route through it, checked by a test that fails the moment
a twelfth appears without it. **Thirteen fabrications removed** — the three named
in §1.4 and ten more found while migrating. Suite: **331 passing**, offline, ~92s.

The full list is in `handoff.md`. The two worst were not in `§1.4` at all:

- **`AudioSummarizerAgent`** claimed to be "capturing meeting audio streams"
  while capturing nothing. There is no audio capture anywhere in the repo —
  `recorded_transcripts` is only ever assigned `[]` and no caller appends to it.
  A user could leave it running through a meeting, take no notes, and find
  afterwards there had never been anything to summarise.
- **A generated `web_scraper` script** printed `[SUCCESS]` and exited 0 when the
  fetch raised. The parent read a zero exit code and reported the scrape as done
  — a fabricated success laundered through a **subprocess**, where the contract
  in the parent process could not see it. Worth remembering as a general limit:
  the contract governs this process only.

Two more found beyond §1.4, in the same class as the originals:

- **`ComputerAgent.get_system_volume`** returned a hardcoded `volume: 50` as
  though it were a reading — and that fallback was the *only* path that ever
  ran, because `Win32_AudioDevice` exposes no `Volume` property. Every caller
  since has been told the volume is 50%.
- **`CommunicationAgent.read_latest_email`** returned "✓ Inbox check complete:
  0 unread messages" whenever credentials were missing, the optional
  `googleapiclient` was absent, or the API raised — every case in which the
  inbox is *unknown*, reported as *empty*.

One deviation from the design below: the field is `success`, not `ok`, so
`as_dict()` stays a drop-in for the dicts the API, UI and 300-odd tests already
read. The contract is the validator, not the vocabulary.



1. `core/contracts.py` — `AgentResult`, `Evidence` union.
2. Migrate agents one file at a time; `AgentResult.model_dump()` keeps the API
   response shape byte-identical so the UI needs no change.
3. Add `test_no_unwitnessed_success`.
4. Fix the three fabrications in §1.4: `read_latest_email` returns
   `NOT_CONFIGURED`, `change_volume` uses a real endpoint or reports honestly,
   `toggle_smart_light` is deleted (with Pillar 5 marked "not implemented" in
   the PRD, matching how the README already handles Google People API).

**Done when:** every agent returns `AgentResult`; the contract test passes; no
handler can report success it cannot witness.

### Phase 3 — The router ✅ **DONE 2026-08-15**

**The legacy chain is gone.** `_dispatch_to_agent` was ~520 lines of substring
tests and is now four steps: refuse, help, route, run.

| "Done when" | Target | Actual |
|---|---|---|
| `planner.py` under 600 lines | < 600 | **570** (was 2,141) |
| Every existing test still passes | — | **687 passing**, 0 failing, ~75s |
| `reports/` has a routing-accuracy table | — | `reports/routing_evidence.md`, **1.000 over 123 commands** |

51 skills, 2,271 patterns, migrated in six tranches — utilities, memory and
identity, the browser surface, live data, the desktop, and email/WhatsApp last
behind their 74 tests. Full write-up in `handoff.md` under 2026-08-15.

Three things that were not in the original design and turned out to matter:

1. **§1.2 is closed completely.** The chain's final `else` handed every
   unrecognised command to `CoderAgent`. Nothing reaches code execution from a
   classification any more — `CoderAgent` is reachable only from
   `create_desktop_folder`, behind an explicit pattern.
2. **Stage 2 is live, and narrow on purpose.** Three families (`chitchat`,
   `memory_query`, `document_intel`) have exactly one skill that runs sensibly
   with no slots. `Skill.__post_init__` *raises* if a Tier-2 skill declares
   intents: irreversible actions need the exactness of a pattern, not a family
   guess.
3. **Ranking needed a tie-break** — literal text first, then typed slots.
   `what is {expression:math}` and `what is {topic}` carry identical literal
   text and were otherwise decided by registration order, which is the invisible
   ordering dependency this phase existed to remove.

Routing moved; parsing did not. `_parse_email_command`,
`_parse_whatsapp_command`, `_resolve_phone_number` and the four contact guards
are unchanged, moved out as mixins so every call site and test keeps working.

**Do not use the padacioso package.** Its `calc_intent` dispatches every match
through a `ProcessPoolExecutor` — measured at **~200 ms per command** against
**0.01 ms** for a direct `simplematch` call, and on Windows it needs an
`if __name__ == "__main__"` guard the planner cannot provide (it is imported by
uvicorn, pytest and `cli.py`), so it raises outright. `core/intent_patterns.py`
reimplements the ~40 lines of alternation/optional expansion that were the only
part worth having, on top of the same underlying matcher.

### Phase 3 — original design (≈2 days, the main event)

1. `core/skills/` — one folder per skill: `intents.yaml`, `handler.py`,
   `manifest.py` (declaring `tier`, `slots`, `offline: bool`).
2. `core/router.py` — the three-stage cascade; Stage 3 disabled by default.
3. Migrate skills in dependency order: **system/time/battery → memory →
   document → whatsapp → email**. Email and WhatsApp last: they are Tier-2 and
   the best-tested, so they are the ones you least want to disturb early.
4. Delete `_dispatch_to_agent`'s keyword chain as each skill lands. Keep a
   `LEGACY_FALLBACK` skill until the chain is empty, then remove it.
5. New evidence artefact: **end-to-end routing accuracy** over the `datagen/`
   corpus — the number that replaces "0.929 on a classifier nobody consults".

**Done when:** `planner.py` is under 600 lines; every existing test still
passes; `reports/` has a routing-accuracy table.

### Phase 4 — One voice, offline (≈1 day)

1. Pick **one** speech path — recommend backend-only, so `cli.py` keeps
   talking. Remove the UI's `speechSynthesis` call.
2. Piper behind `voice/tts_bridge.py`, `pyttsx3` fallback, gTTS last.
3. `faster-whisper` for STT, fed numpy PCM from `sounddevice` — no FFmpeg, which
   is what killed XTTS.

**Done when:** a reply is spoken exactly once, offline, in a non-robotic voice.

This is also the honest resolution of the parked XTTS work: Piper is not the
`mondayvoice.mp3` clone, but it is offline neural TTS that runs *here*, and
"blocked by an unbypassable system security control, replaced with X" is a
better engineering narrative than a `.wav` sitting untracked in the repo.

### Phase 5 — Optional intelligence (≈1 day, only if 1–4 are done)

1. Typed `contacts` table (§2.3) — genuinely a Phase 2 candidate if there is
   appetite; it is the fix for the worst bug this project has had.
2. Ollama Stage 3, off by default, emitting validated tool calls only.
3. `sqlite-vec` semantic recall over conversation turns.

---

## 5. Explicitly not recommended

- **Do not retry `shap`, XTTS, or the Python MSI.** All three are settled; the
  reasons are environmental, not fixable in code.
- **Do not chase a bigger local model.** ~3.4 GB free rules out `qwen3:8b`. A 3B
  at Q4 is the ceiling and is sufficient for Stage 3's job.
- **Do not add agents.** Eleven agents that route through a keyword chain are
  worth less than six that route through a real one.
- **Do not retrain 2.1 for the stopword finding.** The handoff's counterfactual
  framing is right: report the delta, leave the published model alone.

---

## 6. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| SAC blocks Piper/CTranslate2/sqlite-vec binaries | Medium | Each is behind a fallback; verify with a throwaway import **before** adding to `requirements.txt`. SAC blocks lift with reputation — retest, don't assume permanent |
| Router migration breaks a working Tier-2 path | Medium | Migrate email/WhatsApp last, behind their existing 74 tests; keep `LEGACY_FALLBACK` until empty |
| Cassettes drift from real APIs | Low | Keep the live tests under `-m network` and run them weekly |
| Scope creep past the deadline | **High** | Phases 1–2 alone are defensible deliverables. Phase 3 is the one worth protecting time for |

---

## 7. Where to start

Phase 1, item 3 — the two-line bandit fix at `core/planner.py:488`. It is the
smallest change in this document and it repairs a graded component.
