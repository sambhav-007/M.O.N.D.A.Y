# Task success

**20 of 20 tasks completed — 100%.**
Generated 2026-08-22 21:46 by `py -3.12 -m reports.task_success`.

Every other report stops at the routing decision. This one runs the
command and checks the outcome: the success flag, the evidence kind, and
something specific a broken implementation could not fake.

Every task is safe to run repeatedly — reads, writes to a temporary
directory, or state this file creates and removes. Tier-2 skills are
measured by their **gate**, not their effect: the right outcome for
"kill notepad" is the approval prompt, and whether the kill then works
is not measurable without killing something.

| Task | Outcome | What "worked" means |
|---|---|---|
| `what time is it` | passed | reads the system clock and reports a time |
| `battery` | passed | reads the battery through psutil |
| `health` | passed | reports CPU, memory and disk |
| `my ip` | passed | reads local adapters, not a public lookup |
| `what processes are running` | passed | enumerates real processes |
| `calculate 2^3` | passed | evaluates rather than eval()s — 2^3 is 8, not 1 |
| `what windows are open` | passed | enumerates real windows through user32 |
| `remember the report deadline is november 30` | passed | writes to memories.db and says where |
| `recall the report deadline` | passed | reads back what the previous task wrote |
| `set a timer for 10 minutes` | passed | schedules a real timer on the tick thread |
| `what timers do i have` | passed | sees the timer the previous task created |
| `cancel my timers` | passed | removes it again, leaving no state behind |
| `summarize C:\Users\sambh\AppData\Local\Temp\monday_task_succ` | passed | reads the file and summarises what is in it |
| `what does C:\Users\sambh\AppData\Local\Temp\monday_task_succ` | passed | retrieves the passage that answers the question |
| `search C:\Users\sambh\AppData\Local\Temp\monday_task_success` | passed | finds the right document in a folder |
| `summarize no_such_file_xyzzy.pdf` | passed | refuses a file that does not exist instead of summarising its name |
| `book me a flight to delhi on tuesday` | passed | refuses rather than writing a junk calendar entry |
| `xyzzy plugh nothing matches this` | passed | says it does not know |
| `kill notepad` | passed | asks before an irreversible action — the effect is deliberately not exercised |
| `what time is it and then tell me the date` | passed | runs both steps and reports both |
| `latest news` | skipped | needs the network |
| `ifci share price` | skipped | needs the network |

## Deliberately not measured

Listed rather than omitted, so the gaps are visible:

- **send an email** — would deliver mail to a real recipient on every run
- **message a contact on whatsapp** — opens a chat window and needs a keypress
- **terminate a process** — closes a real program; the gate is measured instead
- **take a screenshot** — writes an image per run; the skill is exercised in tests
- **speak out loud** — makes noise on the machine measuring it
- **organize a folder** — moves real files; exercised against tmp_path in tests
