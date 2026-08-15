# M.O.N.D.A.Y. — the rehearsed demo

_Ten minutes, no network required, in this order._

> **The whole script runs with the Wi-Fi off.** That is not a precaution, it is
> the design: every command below reaches a skill declared `offline=True` and is
> executed with sockets blocked by `tests/test_demo_script.py`, which parses
> *this file* for the commands it runs. If a command here stops working, a test
> fails and names it. A demo script that is not executed is a wish list.

## Before you start

```bash
py -3.12 app.py
```

The engine comes up on `127.0.0.1:8000` and the WebGL window opens. If pywebview
is missing it falls back to a tkinter window; `http://localhost:8000/app` is the
same UI in a browser, and `/docs` is the Swagger page for the API.

Two things to check in the first ten seconds, because both have failed silently
before:

1. **The console answers.** Type `health`. If nothing happens, an exception in
   the inline script aborted everything after it — that is what a missing CDN
   used to do (§10 of `handoff.md`), and why all eight libraries are vendored.
2. **The engine is actually up.** `app.py` refuses to open the window if the
   server thread died, so a window at all means the health check passed.

---

## Act 1 — it knows this machine (90 seconds)

Nothing here leaves the laptop. Start here because it is the fastest way to show
that the assistant is reading a real machine rather than reciting a script.

```demo-offline
what time is it
health
battery
my ip
list processes
how many files are on my desktop
```

**What to say while it runs.** `my ip` is worth a sentence: it used to be
answered by asking a third-party geolocation service where the user lived,
because the branch that handled `where am i` sat above it in a chain of
substring tests and swallowed the command. It reads the local adapters now, so
it works with the network off — and it is *more* correct, not merely faster.

`health` and `battery` are `psutil` readings. `list processes` is the same. If
someone asks whether these are canned, run them twice.

---

## Act 2 — memory that is actually a memory (90 seconds)

```demo-offline
my name is Sambhav
what is my name
remember my exam is on friday
recall exam
papa's number is 9876543210
what is papa's number
```

**The story worth telling here** is the one in `core/skills_builtin.py` above
`set_user_name`. Reading and writing the user's name used to be one branch that
fired on `"my name" in cmd_lower`, called a TF-IDF *similarity* search for
"name", and read the top row as the answer. Every reply was then stored as the
next conversation turn, so each retelling nested the previous one:

```
> whats my name
✓ Your name is Agent: MasterPlanner | User: is my name | Assistant:
  ✓ Your name is Agent: MasterPlanner | User: name is sambhag | Assistant: …
```

It grew without bound. Reading and writing are separate skills now, the name has
one canonical key, and machine-written rows are refused outright.

`papa's number is …` is the same guard in its original setting: a contact lookup
that accepted a similarity hit once addressed a WhatsApp message to a phone
number lifted from an unrelated saved transcript.

---

## Act 3 — arithmetic, and why it is not `eval` (30 seconds)

```demo-offline
calculate 12 * 8
what is 2^10
```

Small, and worth the thirty seconds. `what is 2^10` answered **1** until this
week: the branch ran `eval` on the captured text, and `^` is XOR in Python.
Nobody typing `2^10` into an assistant means bitwise exclusive-or.
`core/arithmetic.py` parses to an AST, reads `^` as exponentiation, refuses
anything that is not arithmetic, and bounds the exponent so `9**9**9` cannot
hang the process.

---

## Act 4 — the safety gate (2 minutes, the centrepiece)

```demo-offline
kill notepad
no
```

This is CLO01, and it is the one act to slow down for.

- Terminating a process is **Tier 2**: irreversible, so it stops and asks in its
  own turn. The prompt carries an ETA from **component 2.2**, which is the
  production job the regression model does.
- Answer `no` and nothing runs. Answer with anything that is neither yes nor no
  and it **re-asks** — it never infers approval, because guessing in an
  irreversible path is the single failure this mechanism exists to prevent.
- Then show `history`: the gate is in the audit log, both the request and the
  cancellation.

```demo-offline
history
```

**The detail that makes it a story.** `require_tier2_approval` takes no
`user_approved` parameter at all. It used to, and `ui/index.html` posted
`user_approved: true` on *every* command — so a flag the user never set was
answering a question they were never asked. Deleting the parameter is what makes
the bypass unreintroducible rather than merely fixed.

Ask the audience to try `/help` in the middle of the prompt. The gate survives:
asking what the options are must not silently drop a confirmation.

---

## Act 5 — email, drafted and never sent by accident (2 minutes)

```demo-offline
send mail to a@b.com subject "Demo" body "Hello from MONDAY"
cancel
```

Draft → show → ask → send, and the send only happens on an explicit `send`. The
draft is written to `data/staging/` first, so a composed message survives an
unconfigured or failing transport. With no SMTP credentials it says plainly that
sending is not configured — it does not fake a delivery.

If you want to show the correction path, answer the confirmation with
`subject: New subject body: New body` instead of `cancel`. It updates the draft
and asks again; an edit is not an approval.

---

## Act 6 — what it refuses to pretend (90 seconds, the closer)

This is the act that distinguishes the project, so end on it.

```demo-honest
turn on the living room light
start meeting recording
read my latest email
summarize this
xyzzyspoon12345
```

Every one of these **fails**, on purpose, with a machine-readable error code and
a reason:

| Command | Answer | Was |
|---|---|---|
| `turn on the living room light` | `NOT_IMPLEMENTED` — no hub is configured | "✓ Smart Home IoT: Turned 'Living Room Light' ON." with no device, no protocol and no I/O. The entirety of "Pillar 5" |
| `start meeting recording` | `NOT_IMPLEMENTED` — there is no audio capture | "🎙️ Capturing meeting audio streams…" while capturing nothing. A user could leave it running through an hour-long meeting and find there had never been anything to summarise |
| `read my latest email` | `NOT_CONFIGURED` — needs Google OAuth | A hardcoded subject and sender ("Project Monday Status Update" from `team@monday.ai`) returned as though fetched, on the strength of a token file existing |
| `summarize this` | `NO_DOCUMENT` — which file? | Summarised the four-letter word "this" as a text snippet and reported five key points |
| `xyzzyspoon12345` | `NO_SKILL_MATCHED` | Handed to a code generator that wrote a Python script and ran it in a subprocess |

**The mechanism, not the manners.** `core/contracts.py` makes this structural:
`AgentResult(success=True)` requires `Evidence` — a process exit, an HTTP
response, a file read, a system query, an SMTP acceptance, a keypress, a stored
record. There is no variant meaning "trust me". Thirteen fabricated successes
were removed when it landed, and a fourteenth cannot be written.

---

## If the network happens to be up

These are the only commands in the demo that need it, and they are the only ones
that can stall. DuckDuckGo rate-limits this machine under heavy use and
`open-notify.org` has been down for whole afternoons. **Do not open the demo
with them.**

```demo-network
weather in Delhi
bitcoin price
search web for python tutorials
what is the capital of france
iss location
```

If one hangs, say what it is: a live third-party API with no SLA, reported as a
structured failure rather than an empty success — which is itself the point
being made in Act 6.

---

## The questions that get asked

**"Is the ML doing anything, or is it a keyword matcher?"**
Both, in a stated order, and the order is the interesting part. Stage 1 is
deterministic patterns; stage 2 is component 2.1 choosing a skill *family*;
stage 3 is an honest refusal. Show `reports/routing_evidence.md`: 1.000 over 123
labelled commands, with the negatives — commands that must **not** be captured —
counted separately. Until this phase the published 0.929 macro-F1 described a
model whose output was computed on every command and then ignored for 350 lines.

**"What happens if it is wrong?"**
`kill notepad` again, and answer `maybe`.

**"How do you know it doesn't lie?"**
Act 6, then `core/contracts.py`, then `tests/test_result_contract.py`.

**"How much of this is tested?"**
`py -3.12 -m pytest tests/ -q` — 687 passing, offline, in about 75 seconds. Run it
live if there is time; it needs no network by design, and that is a claim this
script is itself part of proving.
