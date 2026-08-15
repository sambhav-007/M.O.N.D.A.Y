"""
M.O.N.D.A.Y. — Risk-Tiered Security & Safety Engine
=====================================================
PRD §9 Implementation:
  • Tier 1 (Reversible/Low-Risk): Open app, read file, take screenshot, search web,
    move file to staging, query memory. Executes autonomously.
  • Tier 2 (Irreversible/High-Risk): Delete file, overwrite document, send email/msg,
    execute terminal shell, submit form, payment/checkout.
    Gated behind explicit 1-click user confirmation with ETA estimate (CLO03 Component 2.2).
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.config import ACTION_LOG_PATH, AUTO_EXECUTE_TIER_1, LEGACY_ACTION_LOG_PATH

# The audit log is append-only JSON Lines. Each `log_action` opens the file in
# append mode and writes exactly one line, which is O(1) regardless of how much
# history exists.
#
# It used to be a single JSON array: read the whole file, append one entry, write
# the whole file back. That cost grew with the log, and the log only grows — by
# 2026-08-10 it held 19,837 entries / 6.5 MB and every action in the assistant
# paid to re-serialise all of it. The test suite made the same shape of problem
# visible (38s → 209s as the file filled), but the user's own log degrades their
# session in exactly the same way.
#
# Two other properties come out of the change rather than being bolted on:
#
# * **Cross-process writes no longer clobber each other.** The old note here said
#   several interpreters sharing the log "still lose entries to last-writer-wins…
#   cross-process safety would need a file lock or an append-only format". This
#   is that append-only format. Writes go through O_APPEND, so concurrent writers
#   interleave whole lines rather than overwriting one another's copy of the
#   file. Two processes can still produce lines in an unhelpful *order*, and a
#   torn line remains theoretically possible for very large records, but no
#   writer can now discard another's entries.
# * **Corruption is contained to a line.** Previously a single parse failure
#   meant the entire array was unreadable, and the recovery path moved the whole
#   file aside to `action_history.corrupt-*.json`. Now an unparseable line is
#   skipped by the reader and the rest of the log is unaffected.
#
# The lock is kept: it costs nothing and keeps ordering tidy within a process.
_LOG_LOCK = threading.Lock()

# ── Defined Risk Tiers ─────────────────────────────────────────────────────────
TIER_1_ACTIONS = {
    "open_app",
    "read_file",
    "take_screenshot",
    "web_search",
    "read_webpage",
    "summarize_document",
    "query_memory",
    "store_memory",
    "stage_files",
    "organize_directory",
    "get_system_health",
}

# The risk policy. This is deliberately broader than what the agents can
# currently do: classification is a default-deny list, so naming an action here
# before it exists means a future implementation is gated from its first commit
# rather than shipping unguarded.
#
# Of these, only the following are actually implemented and reachable today:
#   • send_email       — agents/comms_agent.py, gated via planner confirm_send
#   • terminate_process— agents/computer_agent.py, gated via require_tier2_approval
# The rest (delete_file, overwrite_file, execute_shell, submit_form,
# modify_system_settings, kill_process) have no implementation anywhere in the
# codebase. Do not cite them as working safety features.
TIER_2_ACTIONS = {
    "delete_file",
    "overwrite_file",
    "send_email",
    "send_notification",
    "send_whatsapp",
    "execute_shell",
    "submit_form",
    "modify_system_settings",
    "terminate_process",
    "kill_process",
}

# Subset of TIER_2_ACTIONS that has a real implementation behind it. Kept
# explicit so the report and the demo can state exactly what is enforced.
# `send_whatsapp` was here until 2026-08-13. It gated a `pyautogui.press("enter")`
# that fired blind into whatever window held focus after a fixed sleep, so an
# approved send routinely sent nothing while reporting "pressed Enter". A gate in
# front of an action that does not happen is worse than no gate: it asks the user
# to authorise something and then tells them it was done. WhatsApp now prepares
# the message and stops (Tier 1 — nothing leaves the machine), so there is
# nothing left to approve. `send_whatsapp` stays in TIER_2_ACTIONS above, where
# the default-deny policy keeps it gated if it is ever implemented for real.
TIER_2_IMPLEMENTED = {
    "send_email",
    "terminate_process",
}


def classify_action_risk(action_name: str) -> Tuple[int, str]:
    """
    Classifies an action name into Tier 1 or Tier 2.

    Returns
    -------
    (tier_number, description)
    """
    clean_action = action_name.lower().strip()
    if clean_action in TIER_2_ACTIONS or "delete" in clean_action or "send" in clean_action or "execute" in clean_action:
        return 2, "High-Risk / Irreversible — User Approval Required"
    return 1, "Low-Risk / Reversible — Autonomous Execution Permitted"


def evaluate_action_permission(
    action_name: str,
    target: str,
    task_type: str = "desktop_automation",
    agent: str = "computer",
    step_count: int = 1,
    user_approved: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates permission for a proposed action.
    If Tier 2, calls Component 2.2 (ETA Regression) to predict execution time
    for the confirmation prompt.
    """
    tier, reasoning = classify_action_risk(action_name)

    # Predict ETA using Component 2.2 regressor
    predicted_eta = 3.0  # default fallback
    try:
        from ml.task_eta_regression import get_trained_regressor, engineer_features, HISTORICAL_AVG
        import pandas as pd

        regressor = get_trained_regressor()
        rec = {
            "task_type": task_type if task_type in HISTORICAL_AVG else "desktop_automation",
            "agent_involved": agent,
            "step_count": float(step_count),
            "time_of_day_h": datetime.now().hour + datetime.now().minute / 60.0,
            "historical_avg_s": HISTORICAL_AVG.get(task_type, 15.0),
            "eta_seconds": 0.0,
        }
        X, _ = engineer_features(pd.DataFrame([rec]))
        predicted_eta = max(1.0, float(regressor.predict(X)[0]))
    except Exception:
        pass

    requires_approval = (tier == 2) and not user_approved

    return {
        "action_name": action_name,
        "target": target,
        "risk_tier": tier,
        "reasoning": reasoning,
        "requires_approval": requires_approval,
        "predicted_eta_seconds": round(predicted_eta, 1),
        "confirmation_prompt": (
            f"⚠️ Tier-2 Action Gated: Action [{action_name}] on [{target}] "
            f"is irreversible. Est. {int(predicted_eta)}s — Approve execution?"
        ) if requires_approval else f"✓ Tier-1 Action [{action_name}] permitted (Est. {int(predicted_eta)}s).",
    }


def log_action(
    action_name: str,
    target: str,
    tier: int,
    status: str,
    agent: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Persists an action execution record to the system audit log.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action_name,
        "target": target,
        "tier": tier,
        "status": status,
        "agent": agent,
        "details": details or {},
    }

    # One line, appended. No read, no rewrite — the cost does not depend on how
    # much history is already there.
    #
    # `ensure_ascii=True` is deliberate: the record must not contain a raw
    # newline that would split it across two lines and corrupt both.
    line = json.dumps(entry, ensure_ascii=True) + "\n"
    with _LOG_LOCK:
        try:
            ACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(ACTION_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            # Auditing must never take down the action it is recording.
            pass

    return entry


def _read_jsonl_tail(path, limit: int) -> List[Dict[str, Any]]:
    """Returns the last `limit` parseable records from a JSON Lines file.

    A `deque(maxlen=…)` over the file keeps only the lines that can still make
    the cut, so a large log costs a scan but never a full parse. Unparseable
    lines are skipped rather than aborting the read — with one record per line,
    damage cannot spread past the line it is on.
    """
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            tail = deque(f, maxlen=max(1, limit))
    except Exception:
        return []

    records: List[Dict[str, Any]] = []
    for raw in tail:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except Exception:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _read_legacy_array(path) -> List[Dict[str, Any]]:
    """Reads the pre-2026-08-10 array-format log, if it is still around."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history if isinstance(history, list) else []
    except Exception:
        return []


def get_action_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns the most recent audit records, newest last.

    Reads the append-only log first. The legacy array file is only opened when
    the new log cannot fill the request on its own — every legacy record predates
    every new one, so once there are `limit` new entries the old file is
    irrelevant and a 6.5 MB parse is skipped entirely.
    """
    recent = _read_jsonl_tail(ACTION_LOG_PATH, limit)
    if len(recent) >= limit:
        return recent[-limit:]

    legacy = _read_legacy_array(LEGACY_ACTION_LOG_PATH)
    return (legacy + recent)[-limit:]
