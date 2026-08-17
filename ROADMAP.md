# M.O.N.D.A.Y. — parity roadmap

_Written 2026-08-16, after surveying what Siri, Google Assistant, ChatGPT's live
chat and Gemini Live actually do, and what the open-source ecosystem already
provides for each piece._

`UPGRADE_PLAN.md` is the record of Phases 1–3, which are done. This is the plan
for what is left, and it is written to one rule:

> **Every capability below is bought from a library, not written here.** Where
> the answer is "write it", that is stated and justified. Where a library exists
> but is the wrong fit for *this machine*, the reason is measured, not guessed.

---

## 0. What this machine can actually do

Measured 2026-08-16, not assumed. This is the section that decides most of the
plan, because the last three attempts at ambitious dependencies here (`shap`,
XTTS, FFmpeg) all died on the same wall.

| | |
|---|---|
| Python | 3.12.10 (MSIX; `py -3.12`) — the MSI installer is broken, see `handoff.md` §1 |
| CPU | 8 physical / 16 logical cores |
| RAM | **15.3 GB total, 4.2 GB free** ← the binding constraint |
| SQLite | 3.49.1, `enable_load_extension()` **works** |
| `onnxruntime` | **not installed** — the single highest Smart App Control risk below |
| `ollama` | not installed |
| `ffmpeg` | not installed, and **SAC blocks it outright** — never pick anything that needs it |
| `node` | installed (already used by `tests/test_voice_ui.py`) |

**4.2 GB free is the number that matters.** A 3B model at Q4 is ~2.0 GB of
weights plus context; that fits, with MONDAY's own sklearn pipelines alongside
it, but not comfortably. An 8B model does not fit at all. Plan for 3B, keep 1B
as the fallback, and do not let anyone talk this up to 7B later.

---

## 1. The honest gap

What the four reference assistants do, and where MONDAY stands after Phase 3.

| Capability | Siri / Assistant / ChatGPT / Gemini | MONDAY today | Gap |
|---|---|---|---|
| Understands phrasing nobody anticipated | LLM | 51 pattern skills + a 7-class classifier | **"I'm not sure how to do that yet"** |
| Multi-turn context ("do that again", "the second one") | core to all four | none — every command is independent | **the biggest single gap** |
| Replies appear as they are generated | token streaming | one blob, after the whole turn | feels slow even when it is not |
| Speech in, offline | on-device | Google Web Speech, over the network | contradicts the offline-first claim |
| Speech out, natural | neural TTS | browser `speechSynthesis` | robotic |
| Remembers across sessions, by meaning | vector recall | TF-IDF over *every* row | the root of the WhatsApp misdirection bug |
| Wake word | on-device | **already works** — browser-native, verified on the real machine 2026-08-14 | **none** |

That last row is why the plan does not start with voice. The obvious move —
"add a wake word engine like Porcupine" — would rebuild something that already
works, needs an access key and online activation, and would make an offline-first
project depend on a vendor console.

---

## 2. What the ecosystem already solved

Surveyed rather than assumed. Two columns matter: **what to take**, and whether
taking it means a dependency or just a design.

| Project | What it solves | How MONDAY should use it |
|---|---|---|
| [Home Assistant Assist / Wyoming](https://www.home-assistant.io/integrations/wyoming/) | The four-stage voice pipeline: wake → STT → agent → TTS, each swappable | **Design only.** MONDAY's router is already the "agent" stage. Adopt the *staging*, not the protocol — a socket protocol between processes buys nothing in a single-process desktop app |
| [Rhasspy](https://community.rhasspy.org/) / OVOS | The same, monolithic | Already borrowed: `core/intent_patterns.py` reimplements padacioso's expansion. Nothing further to take |
| [Ollama](https://docs.ollama.com/capabilities/tool-calling) | Local LLM serving **with native tool calling** since 0.3, structured outputs since 0.5 | **Dependency.** Installs per-user with no admin rights |
| [ollama-python](https://deepwiki.com/ollama/ollama-python/4.4-structured-outputs) | Typed client; pass a pydantic model to `format=` and the model's *inference* is constrained by the schema | **Dependency.** Pure Python over httpx — no binaries, so no SAC risk |
| [Open Interpreter](https://github.com/OpenInterpreter/open-interpreter/blob/main/docs/SAFE_MODE.md) | Confirm-before-execute | **Design only**, and already converged on — cited in `reports/CLO01_ethics_and_safety.md` §2.5 |
| [Pipecat](https://docs.pipecat.ai/) / [LiveKit Agents](https://docs.livekit.io/agents/) | Realtime voice pipelines with barge-in and turn detection | **Neither.** Both assume a WebRTC transport and a server; MONDAY's barge-in already works in-browser. Read Pipecat's turn-detection design, take no code |
| [piper1-gpl](https://pypi.org/project/piper-tts/) | Offline neural TTS, Windows wheel, embedded espeak-ng | **Dependency, second choice** — clean tree, but GPL-3.0. See §4 |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | Offline neural TTS, 82M params, MIT wrapper / Apache weights | **Rejected on its dependency tree** — 22 packages, one of them SAC-blocked here before. See §4 |
| `pyttsx3` (SAPI5) | Windows' own voices over COM | **Dependency, first choice** — four packages, no ML binaries at all. See §4 |
| [Vosk](https://alphacephei.com/vosk/) | Offline STT, ~50 MB model, CPU, accepts raw PCM | **Dependency**, and the recommended STT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Offline STT, better accuracy | **Rejected on RAM** — see §4 |
| [openWakeWord](https://github.com/dscripka/openWakeWord) | Wake word, Apache-2.0 | **Not needed** — the browser already does this |
| [sqlite-vec](https://alexgarcia.xyz/sqlite-vec/python.html) | Vector search inside SQLite | **Deferred** — see §4; `numpy` already does this well enough at this scale |

---

## 3. The plan, in the order that shows value earliest

Each phase is independently shippable, ends with the suite green offline, and
is useful on its own if the next one never happens.

### Phase 4 — Stage 3: the local LLM ✅ **DONE 2026-08-16**

Implemented in `core/llm.py`, wired as the router's third stage, 28 tests.
Details below are the plan as written; what shipped matched it, with one
environment surprise worth recording:

> **The Ollama GUI installer does not work in this environment.**
> `OllamaSetup.exe /VERYSILENT` exits **1** with no log written, no
> CodeIntegrity event, and nothing installed — despite a valid EV signature from
> Ollama Inc. and Smart App Control being in enforce mode without objecting.
> Do not spend time on it.
>
> **Use the standalone ZIP instead**, which needs no installation at all:
>
> ```bash
> curl -L -o ollama.zip https://ollama.com/download/ollama-windows-amd64.zip
> # extract to %LOCALAPPDATA%\Ollama, then:
> %LOCALAPPDATA%\Ollama\ollama.exe serve
> ```
>
> Strictly better here anyway: no installer, no service, no admin, and removing
> it is deleting a folder. `ollama.exe` runs unimpeded — SAC does not block it.

**One thing the plan did not anticipate.** `pytest.ini` allows `127.0.0.1`
through `--block-network`, because the API tests need it — and Ollama listens on
exactly that address. So a machine with a model running would have pulled stage 3
into the test suite, and `xyzzyspoon12345` (in `DEMO.md`'s honest-failure act,
which must fail) would have been answered cheerfully by the model. The suite
would then pass or fail depending on whether a developer happened to have a
server up, which is precisely the property Phase 1 was fought for. Stage 3 is now
off for the whole suite unless a test asks for it with `@pytest.mark.llm`.

### Phase 4 — as planned

The router was built with a Stage 3 slot and it has been empty since Phase 3.
This fills it, and it is the highest-value day of work available: it converts
every "I'm not sure how to do that yet" into an answer.

**The insight that makes this cheap.** `core/skills.py` already declares, for all
51 skills: a `name`, a `description`, a `tier`, the slots its patterns capture,
and whether it is `offline`. **That is a function-calling manifest.** Generate the
tool schema from the registry; do not hand-write one, and do not let the two
drift.

```
command
  ├─ Stage 1  patterns          ← unchanged, still first, still offline
  ├─ Stage 2  classifier        ← unchanged
  └─ Stage 3  LLM tool call     ← new: model picks a skill + fills its slots
                                   validated against the skill's schema
                                   before anything runs
```

- **Library**: `ollama` (Python, pure). Model `llama3.2:3b` at Q4 (~2 GB).
- **Written here**: the registry→schema generator (~40 lines) and the validation
  gate. Nothing else.
- **Safety, non-negotiable**: the LLM emits a *validated tool call*, never free
  text that is executed. **Tier-2 skills stay unreachable from Stage 3**, exactly
  as they are from Stage 2 — `Skill.__post_init__` already raises on that, so the
  rule is inherited rather than re-implemented. The result contract still applies
  to whatever the skill returns.
- **Offline story preserved**: Stage 1 still answers the whole demo script with
  the network off. Stage 3 is a local server; when Ollama is absent the router
  falls through to today's honest refusal.
- **Testing**: stub the client for the default suite; a `@pytest.mark.llm` marker
  for the handful that need a live model, deselected like `network` is.

**Done when**: `book me a flight to Delhi next Tuesday` reaches a skill or an
honest refusal — not a pattern miss — and `reports/routing_evidence.md` gains a
Stage-3 column.

### Phase 5 — Streaming replies ✅ **DONE 2026-08-16**

`POST /agent/stream` emits `classified` → `consulting_model` → `token`* →
`result`, plus a `heartbeat` every 10 s. `process_command` gained an optional
`on_event` sink and is otherwise untouched, so **streaming observes the same
pipeline that answers `/agent/execute`** — including the Tier-2 gate, the
clarification state machine and the RL credit. Verified in a real browser.

**The plan's stated benefit did not materialise, and something better did.**
The premise was "first token in ~1 s beats a complete answer in ~8 s". Measured:
with a 49-tool schema, `llama3.2:3b` selects a tool for essentially *every*
command and writes free text almost never — so there are usually no tokens to
stream, and a warm tool selection takes **0.8–1.7 s** anyway. The token plumbing
is built, correct and tested; it just rarely fires.

What actually mattered was the **progress events**, for a reason the plan did
not anticipate: `ui/index.html` aborted every request after **15 seconds**. A
cold model load takes a minute or more, so the first LLM-routed command a user
ever typed was cancelled before it could answer, and they saw "Execution request
timed out". The UI now has no fixed deadline — it abandons the stream only after
45 s of *silence*, and the server heartbeats every 10 s so that "slow" and
"dead" stay distinguishable.

One thing folded in on the way: the pywebview bridge and the HTTP path each
built the result markup themselves, ~40 lines apart. They share `renderResult`
now, which is also where the 💭 "written by a local model" note lives.

### Phase 5 — as planned

Makes MONDAY feel like ChatGPT rather than a form submission, and it is
*required* to make a 3B model on a CPU tolerable: first token in ~1 s beats a
complete answer in ~8 s, even though the second is the same work.

- **Library**: none. FastAPI's `StreamingResponse` with `text/event-stream`, and
  `EventSource` in `ui/index.html`. Both are already present.
- **Written here**: one endpoint and one UI handler.
- **Bonus it unlocks**: the UI's existing barge-in can stop *generation*, not
  just speech — which is the Gemini Live interaction, on a local model.

### Phase 6 — Conversation memory ✅ **DONE 2026-08-17** (with one honest caveat)

Both halves landed, and the "done when" is **half met** — stated plainly because
the gap is the interesting part.

**The `contacts` table.** Contacts are a typed table now, queried exactly and
case-insensitively. `_resolve_phone_number` reads, in descending order of trust:
the number the user typed → the contacts table → the legacy similarity search
behind its four guards. The guards stay, because a user's contacts taught before
this change live in `memories` and deleting that path would lose them. What
changed is that they are no longer the *only* defence: a lookup that reads the
contacts table cannot return a conversation transcript, because transcripts are
not in it.

**Short-term context.** The last six messages go to stage 3 and to nothing else.
Stages 1 and 2 stay stateless: a pattern that matched yesterday must match today,
and a classifier whose answer depended on the previous command would make the
published routing figure unreproducible.

**The caveat, measured against the live model:**

```
> message papa saying I'll be late     → pattern → message_contact ✓
> and tell mum too                     → stage 3 → message_contact, slots={'rest': 'I'}
```

It reaches the **right skill** from a follow-up that names no action — which only
works because it saw the previous turn, so the context is doing real work. It
fills the **wrong argument**. A 3B model resolving an elliptical reference into
structured arguments is evidently past what it does reliably.

Adding a follow-up rule to the system prompt was tried and **made it worse** —
the model then selected no tool at all. Left as it was.

This fails safely and visibly: the proposal gate from Phase 4 shows `rest=I` and
the user declines. That is the design working, not a workaround for it.

### Phase 6 — as planned

The gap that makes MONDAY feel like a command line rather than an assistant.
Two parts, and the first is a bug fix that has been outstanding since the router
work.

1. **A typed `contacts` table** (`UPGRADE_PLAN.md` §2.3). The four guards in
   `_resolve_phone_number` are correct and must stay, but they are a filter
   bolted onto the wrong data model. A contact lookup that reads a `contacts`
   table *cannot* return a conversation transcript, because it does not read that
   table. **Library: none — this is a schema, and writing it is the point.**
2. **Semantic recall over conversation turns only**, with the last N turns fed
   to Stage 3 as context.
   - **Library: none, and this is the important call.** With Ollama already
     present from Phase 4, `nomic-embed-text` (~270 MB) gives embeddings with no
     new Python dependency, and cosine similarity over a few thousand rows is a
     `numpy` dot product taking single-digit milliseconds. `sqlite-vec` solves a
     problem this project does not have at this scale, and its Windows wheel
     availability is unconfirmed. Revisit at ~100k rows; MONDAY has ~2k.

**Done when**: "message papa saying I'll be late" → "and tell mum too" works.

### Phase 7 — Voice, offline and not robotic (≈1 day)

The honest resolution of the parked XTTS work. Take it in three steps and stop
as soon as the quality is good enough — the first step needs no ML binaries at
all and is thirty minutes of work.

1. **TTS: `piper-tts`.** Five packages, embedded espeak-ng, and `onnxruntime` is
   confirmed to load here (§5). GPL-3.0, so adopting it is a licence decision to
   make deliberately rather than a `pip install` — but it is the only candidate
   that is both installable here and actually pleasant to listen to.
2. **TTS fallback: `pyttsx3`.** Four packages, no ML runtime, always available.
   Measured on this machine it offers only *David* and *Zira* — the legacy SAPI5
   voices, not Windows 11's Natural ones — so treat it as the guaranteed-offline
   floor, not as the quality answer. `§4.1` originally had this the other way
   round; the probe corrected it.
3. **STT: `vosk`.** ~50 MB model, CPU-only, two packages, accepts raw PCM from
   the `sounddevice` already installed — **no FFmpeg**, which is what killed
   XTTS. Removes the Google Web Speech round-trip, so "voice works offline"
   stops being an overstatement.

**Written here**: nothing new. `voice/tts_bridge.py` already exists as the seam,
and `core/speech.py` already makes the one spoken-form decision for every
surface — keep both, or the double-speak comes back.

**Only step 2 is gated on `onnxruntime`.** Steps 1 and 3 have no SAC exposure at
all, which is why this phase is worth attempting even if the probe in §5 fails.

---

## 4. Rejected, with reasons

Recording these matters as much as the choices — this repo has lost days to
options that looked obvious.

### 4.1 The TTS decision, measured

This is the one place where reading the READMEs gave the wrong answer, so the
working is shown. `pip install --dry-run` on 2026-08-16, against this
interpreter:

| Candidate | Packages it would install | Licence | Verdict |
|---|---|---|---|
| `pyttsx3` | **4** — `comtypes`, `pypiwin32`, `pywin32`, `pyttsx3` | MPL-2.0 | **First choice.** No ML runtime, no model file, uses Windows' own voices |
| `piper-tts` | **5** — `flatbuffers`, `onnxruntime`, `pathvalidate`, `protobuf`, `piper-tts` (espeak-ng embedded in the wheel) | **GPL-3.0** | Second choice, on a deliberate licence decision |
| `kokoro-onnx` | **22** — including `phonemizer-fork`, `espeakng-loader`, `rdflib`, `csvw`, `segments`, **`regex`** | MIT + Apache-2.0 weights | **Rejected** |

Kokoro looked like the obvious pick on licence alone, and the dependency tree
reversed it. Twenty-two packages to say a sentence is a poor trade on a machine
with 4.2 GB free — and one of them is **`regex`**, which Smart App Control
blocked here during the XTTS attempt (`handoff.md` §5). Choosing the option that
reintroduces a package already known to be blocked on this machine, to avoid a
licence question on a private coursework repo, is the wrong way round.

### 4.2 Everything else rejected

| Rejected | Why |
|---|---|
| **faster-whisper** | Needs CTranslate2 binaries and materially more RAM than Vosk. With 4.2 GB free and a 3B model already claiming 2 GB of it, Vosk's 50 MB is the right trade. Accuracy is the thing given up, and it is worth saying so |
| **Porcupine / pvporcupine** | Needs an access key and **online activation**. An offline-first assistant should not require a vendor console to hear its own name |
| **openWakeWord** | Good and Apache-2.0, but the browser already does this, verified on the real machine. Adding it would replace working code with equivalent code plus an ONNX dependency |
| **Pipecat / LiveKit Agents** | Both assume WebRTC transport and a server process. MONDAY is a single-process desktop app whose barge-in already works. Take the turn-detection *design*, not the framework |
| **sqlite-vec** | Deferred, not rejected. `enable_load_extension()` works here, but the Windows wheel is unconfirmed and numpy is sufficient at 2k rows. Revisit at 100k |
| **qwen3:8b or any 7B+** | ~5 GB at Q4 against 4.2 GB free. It will not run, and finding that out after wiring it is a wasted day |
| **LangChain / LlamaIndex** | Large dependency trees to wrap an HTTP call MONDAY makes directly. The tool schema comes from the skill registry, which is the part these frameworks would otherwise provide — and MONDAY's version is 40 lines and already typed |

---

## 5. Step 0 — the probe, before any of this

**Do this first, and do not skip it.** Every dependency above is judged on this
machine, not on its README, because Smart App Control has blocked
freshly-published binaries here three times: `numba` (killed `shap` permanently),
FFmpeg (killed XTTS), and pandas 3.0.5 (killed the engine at import for a day).

**The resolve step is already done** — run 2026-08-16, and it is what produced
§4.1. Every candidate has a Python 3.12 `win_amd64` wheel:

| | resolves to |
|---|---|
| `ollama` | `ollama-0.6.2` — **one package, no binaries** |
| `vosk` | `vosk-0.3.45`, `srt-3.5.3` |
| `onnxruntime` | `onnxruntime-1.28.0`, `flatbuffers`, `protobuf` |
| `pyttsx3` | `pyttsx3-2.99`, `comtypes`, `pywin32`, `pypiwin32` |

Resolving is not loading. **The load test was run on 2026-08-16, in a throwaway
venv, and everything passed:**

| | result |
|---|---|
| `onnxruntime` 1.28.0 | **loads** — Smart App Control does not block it |
| `vosk` 0.3.45 | **loads** |
| `pyttsx3` 2.99 | **loads**, SAPI5 initialises |

So the SAC risk that has killed three dependencies in this repo does not apply
to any of them. Phase 7 is unblocked in full, including Piper.

**One finding reverses part of §4.1.** `pyttsx3` enumerates exactly **two**
voices on this machine — *Microsoft David Desktop* and *Microsoft Zira
Desktop*. Those are the legacy SAPI5 voices, not Windows 11's newer *Natural*
ones, and they are the definition of robotic. `pyttsx3` therefore is **not** the
quality win §4.1 assumed; it is a dependable offline fallback and nothing more.
Since `onnxruntime` loads, **Piper moves back to first choice for Phase 7** and
the GPL-3.0 decision has to be made on its merits rather than avoided. Kokoro
stays rejected — the 22-package tree is unchanged by any of this.

SAC blocks lift with reputation. A block observed once is worth re-testing in a
week rather than treated as permanent — pandas 3.0.5 was blocked on 2026-08-06
and imported fine on 2026-08-07.

---

## 6. Order of work, and what each day buys

| | Phase | Buys | Risk |
|---|---|---|---|
| 0 | Probe (§5) | An hour that prevents a lost day | — |
| 1 | **4 — Stage 3 LLM** | Understands anything, not only what was anticipated | Low: no binaries |
| 2 | **5 — Streaming** | Feels like ChatGPT; makes a CPU model usable | None: no new dependency |
| 3 | **6 — Memory** | Multi-turn, plus the contacts bug fixed properly | Low: no new dependency |
| 4 | **7 — Voice** | Offline STT, non-robotic TTS | Low for `pyttsx3` + `vosk`; medium only if Piper is needed |

Phases 4 and 5 together are two days and change what the project *is* to a
person using it. If time runs out after them, that is a defensible stopping
point — which is the same property Phases 1–2 had, and the reason the earlier
plan survived contact with a deadline.

---

## 7. What must not change

The four properties that make this project worth extending, listed because every
phase above is a chance to break one:

1. **Stage 1 answers the demo with the network off.** `DEMO.md` and
   `tests/test_demo_script.py` enforce it. An LLM is a fallback, never a
   dependency of the happy path.
2. **A success requires evidence.** `core/contracts.py`. An LLM-generated answer
   is not evidence that anything happened, and must not be reported as though it
   were — this is the exact failure `CognitiveResponseDict.__bool__` already had
   once, when it returned `True` unconditionally and overwrote every genuine
   failure with a fabricated "🤖 Cognitive Response".
3. **Tier-2 actions are reachable only by exact pattern.** Not from the
   classifier, and not from the LLM.
4. **Nothing leaves the machine unless the command is about leaving the
   machine.** Ollama is local; that is most of why it was chosen over an API key.
