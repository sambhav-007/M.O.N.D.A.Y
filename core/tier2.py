"""
M.O.N.D.A.Y. — the Tier-2 approval gate (PRD §9).

Irreversible actions stop and ask, in their own turn, every time. The
generic form of the draft → confirm → send sequence the email path proved
out.

Two design decisions are load-bearing and must survive any refactor:

1. **`require_tier2_approval` takes no `user_approved` parameter.** It used
   to, and `ui/index.html` posted `user_approved: true` on every command —
   so a flag the user never set was answering a question they were never
   asked. Removing the parameter is what makes the bypass unreintroducible
   rather than merely fixed.
2. **A gated action parks its executor's *name*, never a callable.** The
   pending state has to stay plain data so it can be logged and inspected,
   and so nothing can smuggle an arbitrary function into the approval path.
   Only names in `_tier2_executors` can ever be resumed.

`parse_confirmation` is here because it is the vocabulary the gate is
defined in: an answer that is neither affirmative nor negative is never
read as either — the gate re-asks. Guessing in an irreversible path is the
single failure mode this whole mechanism exists to prevent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.security import evaluate_action_permission, log_action


# ── Tier-2 confirmation vocabulary (PRD §9) ──────────────────────────────────
# Shared by every gated action so "yes" means the same thing everywhere. An
# answer that is neither affirmative nor negative is deliberately NOT treated as
# either: the gate re-asks. Guessing in an irreversible path is the one failure
# mode this whole mechanism exists to prevent.
_AFFIRMATIVE = {
    "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "confirm",
    "confirmed", "approve", "approved", "go", "go ahead", "do it", "proceed",
    "send", "send it", "send the mail", "send the email", "send mail",
    "send email",
}
_NEGATIVE = {
    "no", "n", "nope", "cancel", "stop", "abort", "don't", "dont", "not now",
    "later", "discard", "nevermind", "never mind", "reject", "deny",
}


def parse_confirmation(answer: str) -> str:
    """
    Classifies a reply to a Tier-2 confirmation prompt.

    Returns "yes", "no", or "unclear". Anything not clearly affirmative or
    clearly negative is "unclear" — the caller must re-ask rather than assume.
    """
    a = (answer or "").lower().strip().strip(" .!?")
    if a in _AFFIRMATIVE:
        return "yes"
    if a in _NEGATIVE:
        return "no"
    # A comma after the answer is punctuation, not meaning: "no, cancel that" is
    # as clear a decline as "no cancel that", but the prefix test below is
    # whitespace-delimited and "no," failed it. Such a reply then fell through to
    # "unclear" and, if it also contained a new-topic word, the gate was released
    # as an abandonment instead of recorded as a decision. Commas only — the
    # apostrophe in "don't" is load-bearing.
    a = a.replace(",", " ")
    # Allow natural prefixes ("yes please", "cancel that") but never a bare
    # substring match, so "don't send it" cannot read as affirmative.
    if a.startswith(("yes ", "yeah ", "confirm", "approve", "go ahead", "do it", "proceed")):
        return "yes"
    if a.startswith(("no ", "cancel", "stop", "abort", "don't", "dont", "never")):
        return "no"
    return "unclear"


class Tier2Mixin:
    """The approval gate, and the executors it is allowed to resume."""

    # ── Tier-2 approval gate (PRD §9) ────────────────────────────────────────
    def require_tier2_approval(
        self,
        action_name: str,
        target: str,
        executor: str,
        executor_kwargs: Dict[str, Any],
        original_command: str,
        task_type: str = "desktop_automation",
        agent: str = "computer",
        step_count: int = 1,
        detail_lines: Optional[List[str]] = None,
        question: str = "Approve? Reply 'yes' to proceed, or 'no' to cancel.",
    ) -> Dict[str, Any]:
        """
        Blocks an irreversible action and asks the user first.

        This is the generic form of the draft → confirm → send sequence that the
        email path proved out. It deliberately takes no `user_approved`
        parameter: approval for a Tier-2 action can only come from an explicit
        confirming turn, never from a flag on the original request. `ui/index.html`
        used to post `user_approved: true` on *every* command, which meant a flag
        the user never set was answering a question they were never asked.

        Component 2.2's ETA regression supplies the "Est. Ns" in the prompt,
        which is the production role the PRD assigns it.
        """
        if executor not in self._tier2_executors:
            return {
                "success": False,
                "error": "UNKNOWN_TIER2_EXECUTOR",
                "message": f"Refusing to gate an unregistered action '{executor}'.",
            }

        perm = evaluate_action_permission(
            action_name,
            target,
            task_type=task_type,
            agent=agent,
            step_count=step_count,
            user_approved=False,
        )
        eta = perm.get("predicted_eta_seconds", 3.0)

        self.pending_clarification = {
            "type": "tier2_approval",
            "step": "confirm_action",
            "action_name": action_name,
            "target": target,
            "executor": executor,
            "executor_kwargs": executor_kwargs,
            "predicted_eta_seconds": eta,
            "original_command": original_command,
        }

        log_action(action_name, target, 2, "awaiting_approval", "planner",
                   {"predicted_eta_seconds": eta})

        details = "\n".join(f"  {line}" for line in (detail_lines or []))
        if details:
            details = "\n" + details
        return {
            "success": True,
            "pending_clarification": True,
            "awaiting_tier2_approval": True,
            "risk_tier": 2,
            "action_name": action_name,
            "target": target,
            "predicted_eta_seconds": eta,
            "message": (
                f"⚠️ {action_name} → {target} · can't be undone · est. {int(eta)}s"
                f"{details}\n{question}"
            ),
            # The voice gets the decision, not the form. Reading out the action
            # name, target, ETA and instructions took longer than the action.
            "speech": f"{action_name.replace('_', ' ')} to {target}. Shall I?",
        }

    def _resolve_tier2_approval(
        self, clarification: Dict[str, Any], user_response: str
    ) -> Dict[str, Any]:
        """Runs, cancels, or re-asks a pending Tier-2 action."""
        action_name = clarification.get("action_name", "unknown_action")
        target = clarification.get("target", "")
        verdict = parse_confirmation(user_response)

        if verdict == "yes":
            executor = self._tier2_executors.get(clarification.get("executor", ""))
            if executor is None:
                result = {
                    "success": False,
                    "error": "UNKNOWN_TIER2_EXECUTOR",
                    "message": f"Cannot execute '{action_name}' — no registered handler.",
                }
            else:
                result = executor(**clarification.get("executor_kwargs", {}))
                result.setdefault("approved_by_user", True)
                result.setdefault("risk_tier", 2)
        elif verdict == "no":
            log_action(action_name, target, 2, "cancelled_by_user", "planner")
            result = {
                "success": True,
                "executed": False,
                "cancelled": True,
                "risk_tier": 2,
                "action_name": action_name,
                "message": f"Cancelled — {action_name} was not performed on {target}.",
            }
        else:
            # Neither yes nor no. Re-arm and ask again; never infer approval.
            self.pending_clarification = clarification
            result = {
                "success": False,
                "pending_clarification": True,
                "awaiting_tier2_approval": True,
                "risk_tier": 2,
                "message": (
                    f"I didn't catch that. Reply 'yes' to approve {action_name} "
                    f"on {target}, or 'no' to cancel."
                ),
            }

        return {
            "user_command": user_response,
            "clarification_resumed": True,
            "intent_classification": {
                "predicted_intent": "tier2_confirmation",
                "confidence": 1.0,
                "llm_fallback": False,
                "clo": "CLO04",
            },
            "rl_routing": {"strategy": "tier2_approval", "clo": "CLO05"},
            "execution_result": result,
        }

    def _exec_terminate_process(self, process: str) -> Dict[str, Any]:
        """Approved executor for terminate_process. Only reachable post-approval."""
        return self.computer_agent.terminate_process(process, user_approved=True)
