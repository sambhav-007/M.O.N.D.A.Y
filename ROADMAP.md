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
| `ollama` | not installed *(installed since — `%LOCALAPPDATA%\Ollama\ollama.exe`)* |
| GPU | **NVIDIA RTX 4050 Laptop, 6.0 GiB VRAM** — not measured on 2026-08-16, and it changes the ceiling below |
| `ffmpeg` | not installed, and **SAC blocks it outright** — never pick anything that needs it |
| `node` | installed (already used by `tests/test_voice_ui.py`) |

~~**4.2 GB free is the number that matters.** A 3B model at Q4 is ~2.0 GB of
weights plus context; that fits, with MONDAY's own sklearn pipelines alongside
it, but not comfortably. An 8B model does not fit at all. Plan for 3B, keep 1B
as the fallback, and do not let anyone talk this up to 7B later.~~

**CORRECTED 2026-08-18 — this measured the wrong memory.** The binding
constraint for a local model is VRAM, and this machine has a **6.0 GiB RTX
4050** that the 08-16 probe did not look for. Ollama finds it without being
asked (`library=CUDA compute=8.9 ... available="5.0 GiB"`), and an 8B at Q4_K_M
is ~4.9 GB, so it fits with a 4k context. The 3B stays the *fallback*, not the
ceiling — see Phase 8. The rest of this section stands; RAM is still what
constrains everything that is not on the GPU.

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

**The second half of this phase's clean-up landed 2026-08-18.** Phase 7 recorded
that `TriModelCognitiveEngine` was "still there, still inert" and that unifying
the two LLM paths belonged here. It is done: the hosted Gemini call that sat
below the dispatch in `process_command` — firing after any failed *or* merely
low-confidence dispatch, and rewriting the result as `success: True` with no
evidence — is deleted, and stage 3 is the only language model in the routing
path. The stored memories that call used to receive moved across to
`LlmStage.choose`, so short-term context (the last six turns) and long-term
context (`memories.db`) now reach the same model. See `handoff.md`, 2026-08-18.

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

### Phase 7 — Voice, offline and not robotic ✅ **DONE 2026-08-17**

Two seams, `voice/tts.py` and `voice/stt.py`, each obliged to report **which
engine** did the work. Verified end to end: MONDAY synthesises a sentence and
transcribes it back, exactly, in 2.3 s, with nothing leaving the machine.

```
said : 'what is the battery level'
heard: 'what is the battery level'    (vosk, offline=True)
```

- **TTS**: Piper if `MONDAY_PIPER_VOICE` points at a voice → `pyttsx3` (SAPI5)
  → `TTS_UNAVAILABLE`, which names what to install. Piper is deliberately not in
  `requirements.txt`: GPL-3.0 is a licence decision, not a dependency choice.
- **STT**: Vosk on the raw PCM already in memory — no WAV round-trip, so no
  decoder and no FFmpeg — falling back to the Google recogniser *and saying so*
  in `data["offline"]`.
- **`speak` waits now.** It used to start a thread and return `TaskQueued` —
  "a thread exists", true and nearly useless. There is a file to witness, so it
  witnesses one: `FileWritten`, plus the engine's name.

**The correction to this document:** it claimed "`voice/tts_bridge.py` already
exists as the seam". It does not — that file is a standalone CLI script for the
abandoned XTTS venv, and is the record of that attempt rather than a hook the
app can call. The seam had to be written.

**Two things this broke, both instructive:**

1. **The suite went from 68 s to 482 s and became audible.** `speak` waiting
   plus `pyttsx3` now installed meant real SAPI5 synthesis and `pygame`
   playback on every speaking test. `no_audio_output` in `conftest.py` fakes
   synthesis into `tmp_path` — with real bytes, so `FileWritten` evidence is
   still exercised rather than bypassed.
2. **Installing `pyttsx3` woke a dormant code path.** It pulls `pywin32`, which
   made `scan_outlook_com_contacts` importable — and it used
   `win32com.client.Dispatch`, which **starts Outlook** when it is not running,
   then walks every item in the Contacts folder. One test took **181 seconds**.
   Now `GetActiveObject`, which attaches to a running instance and raises
   otherwise. "This code never runs here" was a statement about the
   environment, not about the code.

### Phase 7 — as planned

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

---

## 3b. Phases 8–14 — from "answers what it was taught" to "handles what you ask"

**Written 2026-08-18, after the corpus measurement.** Phases 4–7 gave MONDAY a
local model, streaming, memory and a voice. It is still, in an important sense,
a lookup table with a model bolted to the end. This is the plan for the rest,
and it starts with what is honest about the target.

### What "GPT / Claude / Gemini level" can and cannot mean here

It cannot mean matching a frontier model's raw reasoning. Those are hundreds of
billions of parameters in a datacentre; this is a laptop with **6 GB of VRAM**.
Any plan whose first line is "be as smart as GPT-5" is a plan that fails.

But almost nothing a person means by "smart assistant" is raw reasoning. Pulling
apart what MONDAY actually lacks, measured rather than felt:

| | What it looks like | Where MONDAY is | Fixable by |
|---|---|---|---|
| **Hearing** | understands it however you say it | **35.3%** of real utterances route (`reports/massive_coverage.md`) | patterns + a better model — Phases 8, 11 |
| **Precision** | doesn't do the wrong thing confidently | `book me a flight to delhi on tuesday` → creates a **calendar event titled "me a flight to delhi"** | Phase 9 |
| **Hands** | can actually do many things | 49 skills; whole categories (alarms, music, files, maps) have no route at all | Phase 11 |
| **Depth** | chains steps to reach a goal | **one** skill per turn, always | Phase 10 |
| **Memory** | remembers across days and documents | last 6 turns + a key/value table | Phase 12 |
| **Reasoning** | genuinely hard questions | a 3B model | Phase 13 (optional key) |

Five of those six are **architecture, not parameters**. That is the good news,
and it is why this plan spends only one phase on the model itself.

### Phase 8 — Use the GPU that is already in this machine ⚠️ **PARTLY DONE 2026-08-18**

> **Done:** the eval (`reports/stage3_selection.py`), the 8B pulled and
> confirmed resident on the GPU (`offloaded 29/29 layers`), and the default
> changed to a *preference order* — `PREFERRED_MODELS` in `core/llm.py`, best
> first, resolved against what the server actually has, so a machine that only
> pulled the 3B keeps working instead of going quiet.
>
> **Not established:** that the 8B is more accurate. Two runs disagreed (67.3%
> vs 62.0%), and the cause was a flaw in the eval's own sampling — one RNG
> walked across intents, so excluding three utterances from one intent
> reshuffled every intent sorted after it. Fixed (per-intent seed, sample built
> once and shared, 6 → 12 per intent), and the clean comparison is what decides
> this. What *is* established: the 8B costs about double the latency
> (p50 1.3 s → 2.3 s), consistently, across every run.
>
> **The result worth keeping from this phase** is that the eval found something
> the model swap could not: five of six share questions were going to
> `crypto_price`, because "Live cryptocurrency prices" and "Live share price for
> a listed company" are both true and neither says *not the other one*. Sixteen
> descriptions now say what their skill excludes. Same model, same sample:
> **59.1% → 64.3%**, for a text edit.

### Phase 8 — Use the GPU that is already in this machine

**The ROADMAP said a 3B at Q4 was the ceiling. That was computed from system RAM
and it is wrong.** Measured 2026-08-18:

```
NVIDIA GeForce RTX 4050 Laptop GPU — 6141 MiB total, 5920 MiB free
ollama:  library=CUDA compute=8.9 ... total="6.0 GiB" available="5.0 GiB"
```

Ollama is installed (`%LOCALAPPDATA%\Ollama\ollama.exe`), CUDA is detected, and
`llama3.2:3b` answers a routing decision in **1.3 s warm**. An 8B at Q4_K_M is
~4.9 GB and fits, with room for a 4k context.

It matters because the 3B is visibly the weak link. Same probe, same day:

```
'dim the lights a bit'   -> llm chose volume_down      (wrong skill entirely)
'put on some music'      -> llm chose chitchat         (gave up)
'set an alarm for 7am'   -> llm chose schedule_event   (right instinct, no alarm skill exists)
```

**Do:** pull `qwen2.5:7b-instruct` and `llama3.1:8b`, set `MONDAY_LLM_MODEL`, and
measure both against the 3B on a labelled selection set. Keep whichever wins;
keep the 3B as the fallback for machines without the VRAM (the env var already
allows that, and `LlmStage.available()` already degrades honestly).

**The real deliverable is the measurement, not the model.** `reports/stage3_selection.py`:
~150 commands with the skill each should reach, scored as selection accuracy and
warm latency. Without it, "smarter" is a vibe and the next model swap is a
coin toss. **Exit criterion:** selection accuracy on that set beats the 3B by a
stated margin, and p95 warm latency stays under 3 s.

**Half a day. No new dependency, no new code path — one env var and a report.**

### Phase 9 — Stop the confident wrong answer ✅ **DONE 2026-08-18**

> `core/slot_sanity.py`, four rules, wired into stage 1 in `core/router.py`: a
> pattern that matches but produces a parse the skill cannot believe is
> **declined**, and the cascade continues to stages 2 and 3. Not an error and
> not a refusal — it means stage 1 has no confident reading, which is what the
> later stages are for.
>
> Measured over all 10,631 corpus utterances, it rejects **25** parses, of which
> 9 reached a skill that *acts*. The ones worth naming:
>
> ```
> 'please organize a meeting with my company workers' -> organize_folder
> 'remember me to meet reveca today at six p. m.'     -> remember_fact
> 'book me a flight to delhi on tuesday'              -> schedule_event
> ```
>
> The first would have sorted a folder's files because the user said "organize".
>
> **Rule 2 was scoped after measuring it.** Its first version rejected 73 parses,
> and reading them showed every one of its own rejections went to
> `answer_question` — read-only, and a search. A clumsy query still answers the
> question; refusing it gives the user nothing. So rule 2 applies only to skills
> that act. Rules 3 and 4 stay universal because they predict a *guaranteed*
> failure rather than a worse result.
>
> **The price, stated:** coverage 35.3% → 35.1%. Precision costs coverage, and a
> coverage number without a negative set can always be raised by matching more —
> `tests/test_slot_sanity.py` carries both halves, the commands that must reach
> nothing and the ones that must keep working.

### Phase 9 — Stop the confident wrong answer

A greedy pattern is worse than no pattern when the skill it reaches *acts*:

```
'book me a flight to delhi on tuesday'
    -> schedule_event {'title': 'me a flight to delhi', 'when': 'tuesday'}
'summarise my last email and reply to it'
    -> summarize_document {'path': 'my last email and reply to it'}
```

The first writes a junk event into a real calendar. `(schedule|add|create|book)
{title} (at|on|for) {when}` is doing what it was told; the fault is that a
free-text slot in front of an acting skill has no plausibility check at all.

**Do:** (a) a slot sanity layer — a `{path}` that names no file, a `{title}`
starting with a pronoun, a `{symbol}` of four words are all *signals the parse is
wrong*, and the honest response is the clarification MONDAY already knows how to
ask; (b) reuse the Phase 4 proposal gate for pattern matches that trip it, so the
answer becomes "did you mean…?" rather than a silent wrong action; (c) a negative
set in the routing report — commands that must reach **nothing** — because
coverage alone can always be gamed by matching more.

**Exit criterion:** the negative set passes at 100%, and no acting skill can be
reached with a slot that failed its sanity check.

### Phase 10 — More than one step

This is the phase that changes what MONDAY *is*. Today stage 3 picks exactly one
skill and stops. "Summarise my last email and reply to it" is two steps, so it
cannot be done at all — not because either half is missing, but because nothing
composes them.

**Do:** a bounded tool loop. The model gets the result of each call and may make
another, up to a hard budget (start at 5 calls / 60 s), then must answer. Every
step carries its own evidence and its own audit row.

**Containment does not move, and this is the part to get right:**
- Tier 2 stays unreachable from the model — the loop makes *more* calls, not
  more privileged ones.
- A non-read-only skill still proposes rather than performs; approving once
  approves **that step**, not the rest of the plan.
- The budget is a hard stop, and hitting it is a reported failure, not a
  silent truncation.

**Look at `core/task_dag_engine.py` first.** It already claims multi-step, and
two implementations that must agree about the Tier-2 gate is the exact defect
this repository has found in its own code five times. Either the DAG engine
becomes this loop's substrate or it is deleted — not both.

**Two days, and the highest-value two days on this list.**

### Phase 11 — Give it more hands

`reports/massive_coverage.md` is a measured backlog of things people say to an
assistant that MONDAY has no route for at all. In descending order of how often
they were said:

| Missing capability | Evidence |
|---|---|
| alarms and timers | `alarm_set/query/remove`, dropped in `datagen/massive.py` for having no route |
| music and playback | `play_music`, `music_query` + friends — 5 intents, all dropped |
| a real dimmer | `iot_hue_lightdim` 114 rows, **0.0%** — the tool only knows on/off |
| transport and maps | `transport_*` — 4 intents dropped |
| recipes and cooking | `cooking_*` — 2 intents dropped |
| file operations by name | not in MASSIVE, but it is a desktop assistant |
| clipboard, windows, media keys | same |

Each is small on its own. The rule from `datagen/massive.py` applies in reverse:
a capability is only worth adding if it can be done **honestly** — media keys via
`pyautogui` are real; "book me a taxi" is not, and should keep refusing.

**Ship them in tranches of five, re-running the coverage report each time.** The
number moves or the tranche did not work.

### Phase 12 — Memory that compounds

Six turns of context and a key/value table is not memory; it is a scratchpad.
**Do:** summarise finished conversations into durable notes, and put the user's
own documents behind retrieval — `DocumentAgent.rag_search` already exists and
already does the hard part. The goal is "what did we decide about the report last
week" answering correctly, from evidence, with the document named.

### Phase 13 — A fourth stage, for the questions that need one

The honest way to reach frontier-level *answers* is to let the user plug in a
frontier model, not to pretend a 3B is one. Stage 4: an API key in `.env`, off by
default, reached only when stage 3 declines or flags low confidence.

**The rules that make this safe are already written and must be reused, not
re-derived:** nothing leaves the machine unless the user configured a key
(§7.4); an answer carries `ModelAnswered` evidence and never claims work was
done (§7.2); Tier 2 stays unreachable (§7.3); and the offline path still answers
the demo with the network off (§7.1). One provider, one code path — the last
thing this repository needs is a second `TriModelCognitiveEngine`, which is
exactly what was deleted on 2026-08-18.

### Phase 14 — Make "smarter" a number

Five phases of work with no scoreboard is five phases of opinion. One command
that prints one table:

```
coverage        % of MASSIVE utterances reaching a skill        reports/massive_coverage.py
precision       % of the negative set correctly refused         Phase 9
selection       % of labelled commands reaching the right skill Phase 8
task success    % of scripted multi-step tasks completed        Phase 10
latency         p50 / p95, warm                                 Phase 8
```

Run it before and after every phase above. A phase that does not move a number
is a phase to reconsider.

### Order, and what each buys

| | Phase | Buys | Cost | Risk |
|---|---|---|---|---|
| 1 | **8 — the GPU** | a model that picks the right skill | half a day | none: one env var |
| 2 | **9 — precision** | stops confident wrong actions | 1 day | none: it only adds refusals |
| 3 | **10 — the tool loop** | multi-step tasks; the biggest change | 2 days | medium: must not widen the gate |
| 4 | **11 — more hands** | the tasks it simply cannot do | 1 day per tranche | low, if each is honest |
| 5 | **12 — memory** | continuity across days | 1–2 days | low |
| 6 | **13 — optional frontier key** | genuinely hard reasoning | 1 day | low, if §7 is reused |
| 7 | **14 — the scoreboard** | knowing any of it worked | half a day | none |

Phases 8 and 9 together are one day and are worth doing before anything else:
one makes the model choose better, the other stops it acting on a bad choice.

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
