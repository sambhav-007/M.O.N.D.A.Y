"""
M.O.N.D.A.Y. — ROADMAP Phase 10. More than one step, honestly reported.

What this replaces
------------------
`core/task_dag_engine.py`, deleted in the same commit. It was a second routing
implementation — substring tests over the sub-command, `if "search" in
sub_lower`, which is the shape Phase 3 removed 350 lines of — and measured on
2026-08-18 it did three things wrong at once:

```
> summarize nonexistent_file_xyzzy.pdf and then email it to nobody@example.invalid
  success: True      evidence: None
  "✓ Dynamic Task DAG Executed Successfully (2 Steps Completed)"

> kill notepad and then tell me the time
  Step 1: ⚠️ terminate_process → notepad · Approve? Reply 'yes'…
  Step 2: ↩️ Cancelled the pending approval — you asked for something else
  success: True
```

The first reports two failed steps as a success with no evidence. The second is
worse: it **arms the Tier-2 gate, then cancels it with the next step**, kills
nothing, and calls the whole thing a success. A user who asked MONDAY to close a
program was told it had happened. That is the exact failure this repository has
spent every commit removing, in the one place where it touches an irreversible
action.

The design, and why it is this shape
------------------------------------
**One implementation.** Each step is executed by re-entering
`MasterPlanner.process_command`, which means every property already fought for
applies to a step without being restated: the moral firewall, `/help`, the
classifier, stage 1's slot sanity, stage 2, stage 3's proposal gate, the Tier-2
gate, the audit log, memory, and the spoken form. A second executor would have
to agree with that list forever, and the repository's own history says it would
not — the email wizard existed twice, ~130 lines apart, with different
behaviour in each copy.

**Splitting is deliberate and narrow.** Only explicit sequencing connectives
("and then", ", then", "after that") split a command, and never inside quotes.
Splitting on a bare "and" would break `remember milk and eggs` and
`send mail … subject "hi" body "hello and thanks"`, which are single commands
containing the word.

**A failed step stops the plan.** Step 2 usually depends on step 1 having
happened; running it anyway is how the old engine summarised a search that
returned nothing. The result names the step that stopped it.

**A step that needs approval stops the plan too, and says so.** Resuming a plan
across a Tier-2 confirmation is genuinely useful and is *not* built here: the
pending state would have to carry the remaining steps, and a "yes" arriving an
hour later would run something the user has forgotten the context of. Until that
is designed, the honest behaviour is to stop and say which step needs approving
— never to arm a gate and cancel it, which is what the old engine did.

**Success means every step succeeded.** Not "the loop completed".
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

#: Explicit sequencing only. `and then` and `, then` are unambiguous; a bare
#: `and` is a conjunction people use inside single commands and must not split.
#: Ordered longest-first so `and then` wins over `then`.
_CONNECTIVES = (
    " and then ",
    ", and then ",
    ", then ",
    " after that ",
    ", after that ",
    " and after that ",
    " then ",
)

#: A connective inside quotes belongs to a message body, not to the plan:
#: `message bob saying "call me and then text me"` is one step.
_QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')

#: More than this and the "plan" is almost certainly a misread sentence rather
#: than a request. The budget is a hard stop, and hitting it is reported.
MAX_STEPS = 5


def split_compound(command: str) -> List[str]:
    """Splits a command into ordered steps, or returns `[command]` if it is one.

    Quoted spans are masked before the search so a connective inside a message
    body cannot split the command that carries it.
    """
    text = (command or "").strip()
    if not text:
        return []

    # Mask quoted spans with a placeholder of identical length, so every offset
    # found in the masked string is valid in the original.
    masked = _QUOTED.sub(lambda m: "\x00" * len(m.group(0)), text)
    lowered = masked.lower()

    cuts: List[tuple] = []
    position = 0
    while position < len(lowered):
        best = None
        for connective in _CONNECTIVES:
            found = lowered.find(connective, position)
            if found != -1 and (best is None or found < best[0]):
                best = (found, connective)
        if best is None:
            break
        start, connective = best
        cuts.append((start, start + len(connective)))
        position = start + len(connective)

    if not cuts:
        return [text]

    steps: List[str] = []
    previous_end = 0
    for start, end in cuts:
        steps.append(text[previous_end:start].strip())
        previous_end = end
    steps.append(text[previous_end:].strip())

    steps = [s for s in steps if s]
    # A split that produced a fragment too short to be a command is a bad split
    # ("what then" should not become ["what", ""]). Treat it as one command.
    if len(steps) < 2 or any(len(s.split()) < 2 for s in steps):
        return [text]
    return steps


def run_steps(
    steps: List[str],
    execute: Callable[[str], Dict[str, Any]],
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    """Runs each step in order, stopping at the first that does not succeed.

    `execute` runs exactly one command and returns its result dict — in practice
    `MasterPlanner.process_command`, so a step is subject to every rule a
    single command is. Nothing here inspects a skill, a tier or a pattern; that
    knowledge stays in one place.
    """
    trace: List[Dict[str, Any]] = []
    over_budget = len(steps) > max_steps
    planned = steps[:max_steps]

    for number, step in enumerate(planned, start=1):
        result = execute(step) or {}
        message = str(result.get("message", ""))
        succeeded = bool(result.get("success"))
        awaiting = bool(
            result.get("pending_clarification")
            or result.get("awaiting_approval")
            or result.get("awaiting_llm_confirmation")
        )

        trace.append({
            "step": number,
            "command": step,
            "success": succeeded,
            "error": result.get("error", ""),
            "evidence": result.get("evidence"),
            "message": message,
        })

        if awaiting:
            # The gate stays armed — `pending_clarification` is set on the
            # planner — so "yes" runs this step. What the plan cannot do is
            # carry the *rest* across that answer, so the user is told which
            # steps were not run rather than being left to assume they were.
            remaining = planned[number:]
            return _stopped(
                trace, step, number, len(planned), over_budget,
                reason=(
                    f"step {number} needs your approval. Reply 'yes' to run it"
                    + (
                        f"; I did not run the {len(remaining)} step(s) after it, "
                        f"so ask for those separately."
                        if remaining else "."
                    )
                ),
                error="MULTI_STEP_NEEDS_APPROVAL",
            )

        if not succeeded:
            return _stopped(
                trace, step, number, len(planned), over_budget,
                reason=f"step {number} did not succeed, so the rest was not run.",
                error=str(result.get("error") or "MULTI_STEP_FAILED"),
            )

    lines = [f"  {row['step']}. {row['command']}" for row in trace]
    message = (
        f"✓ {len(trace)} steps, all completed:\n" + "\n".join(lines)
        + "\n\n" + "\n\n".join(str(row["message"]) for row in trace if row["message"])
    )
    result = {
        "success": True,
        "multi_step": True,
        "steps_completed": len(trace),
        "steps_planned": len(planned),
        "trace": trace,
        "message": message,
        # Each step carried its own evidence; the plan claims nothing beyond the
        # sum of them, and the aggregate is not itself an evidence kind.
        "step_evidence": [row["evidence"] for row in trace],
        "speech": f"Done — {len(trace)} steps.",
    }
    if over_budget:
        result["success"] = False
        result["error"] = "MULTI_STEP_OVER_BUDGET"
        result["message"] = (
            f"That is more than {max_steps} steps, which is further ahead than I "
            f"plan. I ran the first {len(planned)} — ask for the rest separately.\n\n"
            + result["message"]
        )
    return result


def _stopped(
    trace: List[Dict[str, Any]],
    step: str,
    number: int,
    planned: int,
    over_budget: bool,
    reason: str,
    error: str,
) -> Dict[str, Any]:
    """A plan that stopped part-way, reported as exactly that.

    The completed steps are still reported as completed — they happened, and
    hiding them would leave the user unsure what state the machine is in.
    """
    # Everything before the stop. Not "every row that succeeded": a Tier-2
    # prompt reports success — it succeeded at asking — and would otherwise be
    # listed as both completed and failed, which is how this was found.
    done = trace[:-1]
    lines = [f"  {row['step']}. {row['command']} ✓" for row in done]
    lines.append(f"  {number}. {step} ✗")
    return {
        "success": False,
        "multi_step": True,
        "error": error,
        "steps_completed": len(done),
        "steps_planned": planned,
        "trace": trace,
        "message": (
            f"Stopped after {len(done)} of {planned} steps — {reason}\n"
            + "\n".join(lines)
            + "\n\n" + str(trace[-1]["message"])
        ),
        "step_evidence": [row["evidence"] for row in trace],
        "speech": f"Stopped at step {number}.",
    }
