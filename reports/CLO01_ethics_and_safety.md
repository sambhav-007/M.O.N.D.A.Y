# CLO01 — Ethical AI, safety guardrails, and agentic design

**Course**: 24CSE0316 — AI & Machine Learning
**Project**: M.O.N.D.A.Y.
**Outcome assessed**: *Explain AI concepts and their evolution, and the ethical
considerations and security guardrails of autonomous agent design.*

> Every claim in this chapter is either a file you can open or a test you can
> run. `reports/EVIDENCE_INDEX.md` maps each one to its artefact and the command
> that regenerates it. Where a claim is about something the system **cannot** do,
> that is stated as plainly as the things it can.

---

## 1. The question this chapter answers

An assistant that can send email, terminate processes and run generated code on a
user's machine is not made safe by intending to be. It is made safe — or not — by
what happens at three specific moments:

1. **Before an irreversible action**: does it stop and ask, every time, or can
   that be skipped?
2. **After any action**: is there a record the user can inspect, and does keeping
   that record cost anything?
3. **When something does not work**: does it say so, or does it report success?

The third is the one this project spent the most effort on, and it is the one
most systems get wrong quietly. A guardrail that stops a dangerous action is
visible in a demo. A handler that claims to have sent a message it did not send
is invisible until it matters.

The rest of this chapter answers those three in order.

---

## 2. Moment one — the Tier-2 approval gate

### 2.1 The policy

Actions carry a risk tier (`core/security.py`, PRD §9):

| Tier | Meaning | Behaviour |
|---|---|---|
| **1** | Reversible, local, observable | Runs immediately, logged |
| **2** | Irreversible or outward-facing | **Stops and asks in its own turn** |

Classification is **default-deny**: `classify_action_risk` returns Tier 2 for any
action it does not recognise. An action added tomorrow is gated until someone
deliberately lists it as Tier 1, rather than ungated until someone remembers to
gate it. This is the direction of the error that matters — a wrongly-gated safe
action is an annoyance, a wrongly-ungated destructive one is an incident.

### 2.2 What is actually gated

`TIER_2_ACTIONS` names eleven policy action types. `TIER_2_IMPLEMENTED` names
the subset with a real implementation behind it, and there are **three**:

```python
TIER_2_IMPLEMENTED = {"delete_folder", "send_email", "terminate_process"}
```

That distinction is deliberate and is itself an ethics claim. Eight policy
actions — including `delete_file`, `overwrite_file`, `send_whatsapp` and
`execute_shell` — **do not exist anywhere in the codebase**.
Reporting a guardrail around a capability the system does not have is not a
safety property, it is a decoration. The list of what is enforced is kept
separate from the list of what the policy would cover.

`send_whatsapp` was removed from the implemented set on 2026-08-13 for the
sharpest version of this reasoning. It gated a simulated Enter keypress that
fired blind into whatever window had focus after a fixed eight-second sleep, so
an *approved* send routinely sent nothing while reporting that it had. **A gate
in front of an action that does not happen is worse than no gate**: it asks the
user to authorise something and then tells them it was done. WhatsApp now
prepares the message and stops, which is Tier 1 — nothing leaves the machine, so
there is nothing to approve.

### 2.3 Why the gate cannot be bypassed

`require_tier2_approval` takes **no `user_approved` parameter**. It used to, and
the failure that removed it is the most instructive one in the project:
`ui/index.html` posted `user_approved: true` on *every* command. A flag the user
had never set was answering a question they had never been asked, and every
Tier-2 action except email auto-approved.

Fixing that by making the UI stop sending the flag would have left the parameter
there for the next caller. Deleting the parameter makes the bypass
**unreintroducible** rather than merely fixed: there is no argument through which
approval can arrive, so approval can only come from an explicit answer to the
question the gate asked.

Two further properties, both load-bearing:

- **A gated action parks its executor's *name*, never a callable.** The pending
  state stays plain data (`core/tier2.py`), so it can be logged and inspected,
  and nothing can smuggle an arbitrary function into the approval path. Only
  names registered in `_tier2_executors` can ever be resumed.
- **An unclear answer is not an answer.** `parse_confirmation` returns
  `yes`, `no` or `unclear`, and `unclear` re-asks. Guessing in an irreversible
  path is the single failure this whole mechanism exists to prevent, so the code
  has no branch that infers approval from anything other than affirmation.

### 2.4 The failure mode that was found by using it

An armed gate could be **silently discarded**. `pending_clarification` was
cleared whenever the next turn contained "what", "show", "where" and so on, so a
user who answered *"Send it?"* with "yes, show me" had their gate dropped with
nothing said. It failed closed — nothing was sent, which is the right direction —
but the user was never told, and a later "yes" then answered a question that no
longer existed.

Two changes: a clear yes/no resolves the gate *before* the new-topic test runs,
and abandoning a gate is announced (`cancelled_pending_approval`) and logged.
Low-stakes clarifications — *which contact did you mean?* — still clear quietly,
because the asymmetry is the point: dropping a question is fine, dropping an
authorisation is not.

**Evidence**: `tests/test_tier2_gate.py` — 37 tests, including that `/help`
during a pending gate neither answers it nor drops it, that an unclear reply
re-arms, and that a cancelled gate is announced.

### 2.5 Convergence with prior art

This design was arrived at independently and then checked against
[Open Interpreter's safe mode](https://github.com/OpenInterpreter/open-interpreter/blob/main/docs/SAFE_MODE.md),
which is the closest widely-used analogue: confirm-before-execute by default,
with an explicit `auto_run` opt-out that the user has to set themselves. The
convergence is worth stating because it is the honest form of the claim — this is
not a novel safety mechanism, it is the established one, implemented properly.
MONDAY has no `auto_run` equivalent at all, which is a narrower position than
Open Interpreter takes.

---

## 3. Moment two — the audit log

### 3.1 What is recorded

`core.security.log_action` writes one record per action: timestamp, action,
target, tier, status, agent, and a details dict. Tier-2 actions record their
whole lifecycle — `awaiting_approval`, then `success`, `cancelled_by_user`, or
`cancelled_new_command`. A user can therefore see not just what ran, but what was
*proposed* and declined, which is the part that matters for accountability.

Show it in the app with `history`.

### 3.2 The ethics claim hidden in the performance fix

The log was a single JSON array: read the whole file, append one entry, write the
whole file back — on **every action**. Measured on the real log (19,837 entries /
6.5 MB):

| | per action |
|---|---|
| old: read 85 ms + write 255 ms | **340 ms** |
| new: append one line | **0.39 ms** |

**872× faster**, and no longer dependent on how much history exists.

This belongs in an ethics chapter rather than a performance one, because of what
the old cost did to behaviour. When keeping a complete record makes the system
progressively slower for the user, the record becomes something to prune. Every
command a user issued paid to re-serialise their entire history, so the incentive
was to delete the audit trail — and an audit trail with an incentive to delete it
is not an audit trail. Append-only JSON Lines removes the incentive rather than
managing it.

Three further properties came with the format:

- **Cross-process loss is fixed.** The old code's own comment said this "would
  need a file lock or an append-only format". Writers append whole lines instead
  of overwriting each other's copy of the array.
- **Corruption is confined to one line.** A single bad byte used to make the
  entire array unreadable; the reader skips the line and continues. The
  `action_history.corrupt-*.json` salvage path was deleted because the failure it
  handled can no longer occur.
- **Nothing was discarded.** The legacy array is still read, so no history was
  lost in the migration.

**Evidence**: `tests/test_audit_log.py` — 11 tests, including one asserting that
write cost stops growing with the log.

---

## 4. Moment three — the result contract, and refusing to fabricate

### 4.1 The problem

The recurring defect in this codebase, across at least six separate occasions in
its history, was a handler reporting success for something it had not done:

- A meeting recorder printing "🎙️ Capturing meeting audio streams…" while
  capturing nothing. There is no audio capture anywhere in the repository. A user
  could leave it running through an hour-long meeting and discover afterwards
  that there had never been anything to summarise.
- An inbox reader that checked whether a *token file existed* and returned a
  hardcoded subject and sender ("Project Monday Status Update" from
  `team@monday.ai`) as though fetched.
- A geolocation fallback that returned central Delhi coordinates as "Local
  Geolocation Fallback Active" — and `get_weather` read its latitude and
  longitude, so a failed lookup became a confident forecast for a city the user
  was not in.
- A screen-capture failure that built a blank dark rectangle, reported
  "✓ Screen captured (1920x1080)", and fed it to the analyser.
- A habit miner that returned a hardcoded habit on *any* exception — "git commit
  after running tests", 0.85 confidence, 3.2 lift — phrased as "🤖 Habit
  Detected: I noticed you frequently…". Component 2.4's failure dressed as its
  output.
- A smart-light toggle that performed no I/O of any kind and returned
  "✓ Smart Home IoT: Turned 'Living Room Light' ON." It was the entirety of
  "Pillar 5: IoT & Smart Home Automation".

Each was fixed when found. Fixing instances of a recurring pattern is not a
safety property; the pattern recurred anyway.

### 4.2 The mechanism

`core/contracts.py` makes the class of bug unwritable rather than fixed.
`AgentResult(success=True)` **requires** `Evidence`, and `Evidence` is a closed
union of things that can actually be observed:

| Variant | Witnesses |
|---|---|
| `ProcessExit` | a subprocess ran and returned a code |
| `HttpResponse` | a server answered, with a status |
| `FileRead` / `FileWritten` | bytes moved to or from a path |
| `SystemQuery` | the local machine was interrogated and answered |
| `SmtpAccepted` | a mail server accepted a message **for delivery** |
| `KeypressSent` | a synthetic keypress reached the focused window |
| `TaskQueued` | a background worker was genuinely started |
| `RecordStored` | a row was committed to the local database |

There is no variant meaning "trust me". A failure must carry an `error` code, so
callers branch on a reason rather than parse a message.

Two of these are precise in a way that is the whole point:

- **`SmtpAccepted` says accepted, not delivered.** That distinction belongs to
  the server, and overstating it is exactly the failure this module exists to
  prevent.
- **`KeypressSent` says nothing about what the receiving application did.** It
  exists so a keypress-based integration reports at exactly its real strength.

**Thirteen fabricated successes were removed** when the contract landed, and the
migration is enforced: `test_all_agent_modules_import_the_contract` fails the
moment a twelfth agent module appears without it.

### 4.3 The limit, stated

The contract governs **this process**. A generated script running under
`subprocess` can print `[SUCCESS]`, exit 0, and be believed — which is exactly
what the `web_scraper` template did: it printed `[SUCCESS]` and exited 0 when the
fetch raised, so the parent read a zero exit code and reported a scrape that
never happened. A fabricated success laundered through a process boundary, where
the validator cannot see it.

Two responses, and the second is the structural one:

1. The generated templates were fixed by hand to report failure to stderr and
   exit non-zero.
2. **The generated-code path is no longer reachable from a guess.** Until
   2026-08-15, the router's final `else` handed every unrecognised command to the
   code generator. "search current AI news" — classified `desktop_automation` at
   **0.33 confidence** — reached it and produced a live web fetch. `CoderAgent` is
   now reachable only from one skill with an explicit pattern, so a
   low-confidence classification cannot cause code execution.

**Evidence**: `tests/test_result_contract.py` — 23 tests.

---

## 5. Agentic design: how autonomy is bounded

The routing architecture is a safety property, not only an engineering one, and
this is the part that changed most recently.

Routing used to be ~520 lines of substring tests evaluated in a fixed order, with
the intent classifier's output computed on every command and then ignored for the
first 350 of them. Three consequences, all of which are safety-relevant:

- **Substrings collide.** `"light" in cmd_lower` matches *f-light*, so "i need to
  book a flight" reached the smart-home tool. `"eth"` matches *m-eth-od*, so a
  question about a method was answered with the price of Ethereum. `"charge"`
  matches "how much do you charge", answered with the laptop's battery level.
  These are funny until the colliding branch is the one that sends something.
- **Order was load-bearing and invisible.** `"gmail" in cmd_lower` sat ~70 lines
  above the app launcher, so "open gmail" started composing a message to a
  placeholder address. Nobody chose that; it was an artefact of which `elif` came
  first.
- **The classifier decided almost nothing**, so a published 0.929 macro-F1
  described a model that was not in the decision path.

The three-stage router (`core/router.py`) replaces it: deterministic patterns,
then the classifier choosing a skill *family*, then an honest refusal. Two
choices in it are ethical rather than architectural:

1. **A confidence floor of 0.50 on stage 2.** Below it the classifier is guessing,
   and a guess does not get to pick a handler.
2. **Tier-2 skills may not be reachable from the classifier at all.** This is
   enforced in `Skill.__post_init__`, which raises if a Tier-2 skill declares
   intents: *irreversible actions need the exactness of a pattern, not a family
   guess*. Only three families — `chitchat`, `memory_query`, `document_intel` —
   are reachable from a classification, and each has exactly one skill that does
   something sensible with no arguments.

**Evidence**: `reports/routing_evidence.md` — end-to-end routing accuracy of
**1.000 over 123 labelled commands**, with the negatives (commands that must
*not* be captured) counted separately, and asserted per command by
`tests/test_router.py` so a regression names the command it broke.

---

## 6. Privacy

- **Nothing leaves the machine unless the command is about leaving the machine.**
  The offline demo script (`DEMO.md`) is 21 commands long and executed with
  sockets blocked by `tests/test_demo_script.py`.
- **Memory is local.** SQLite in `data/`, gitignored, never uploaded.
- **Secrets cannot be committed.** A pre-commit hook in `.githooks/` blocks
  staging `.env` or a literal secret value. Verified: no credential appears in
  any blob on any ref.
- **The test suite scrubs the machine's identity.** The first recorded HTTP
  cassette carried the user's real IP, city, postcode, ISP, coordinates and
  ground elevation into a file destined for git. `tests/conftest.py` rewrites
  responses before they are written, and `tests/test_cassette_hygiene.py`
  (21 tests) checks the committed cassettes — verified against a deliberately
  leaky decoy, so the guard is known to be able to fail.
- **The suite does not write to the user's real memory or audit log.** Both are
  redirected to throwaway files for the session. Before that fixture existed the
  suite had written 2,196 rows into the user's assistant memory.

---

## 7. What this system deliberately does not claim

An ethics chapter that lists only successes is the same genre of document as a
handler that reports only successes.

| Not done | Why it is stated rather than omitted |
|---|---|
| No smart-home control | "Pillar 5: IoT" appears in the PRD. The implementation was a function that performed no I/O and returned success. It now answers `NOT_IMPLEMENTED` and names the missing piece |
| No audio capture, so no meeting summaries | The recorder claimed to be capturing. Answering `NOT_IMPLEMENTED` up front is the only version of this that does not waste an hour of someone's meeting |
| No WhatsApp *sending* | The deep link pre-fills and declines to send, by anti-spam design. Messages are prepared and the user presses Enter. It reports that the message was **typed**, never that it was delivered |
| No screen reading without a Gemini key | The analyser used to head its answer "✓ Screen Vision Analysis" and end "Visual Inspection: Onscreen content identified", having identified none — it reports mean pixel brightness |
| No conversational memory across turns | There is no LLM planner. "Show me those results you just found" cannot work, and the README says so |
| No voice cloning | XTTS needs FFmpeg, which Windows Smart App Control blocks outright. Disabling SAC is a one-way switch on a system security control and was out of scope. `voice/tts_bridge.py` is committed as the record of how far it got |

---

## 8. Summary of evidence

| Claim | Artefact | Tests |
|---|---|---|
| Irreversible actions stop and ask | `core/tier2.py`, `core/security.py` | `tests/test_tier2_gate.py` (37) |
| Approval cannot arrive as a flag | `require_tier2_approval` has no such parameter | `tests/test_tier2_gate.py` |
| Every action is recorded, cheaply | `data/action_history.jsonl` | `tests/test_audit_log.py` (11) |
| Success requires evidence | `core/contracts.py` | `tests/test_result_contract.py` (23) |
| A guess cannot execute code | `core/router.py`, `core/skills_system.py` | `tests/test_router.py` (137) |
| Routing is measured end to end | `reports/routing_evidence.md` | `tests/test_router.py` |
| The demo runs with no network | `DEMO.md` | `tests/test_demo_script.py` (31) |
| No machine identity in committed test data | `tests/conftest.py` | `tests/test_cassette_hygiene.py` (21) |

Full suite: **1,105 passing, 0 failing, 7 opt-in tests deselected, offline, ~66s** (2026-10-19).

See `reports/EVIDENCE_INDEX.md` for the regeneration command behind each
artefact.
