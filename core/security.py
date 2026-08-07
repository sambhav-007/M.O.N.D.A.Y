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
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.config import ACTION_LOG_PATH, AUTO_EXECUTE_TIER_1

# AutonomyDaemon logs from a background thread while the planner logs from the
# main thread. Without this lock the read-modify-write below interleaves, one
# writer clobbers the other, and a reader can observe a half-written file.
#
# Scope: this makes logging lossless within one interpreter (verified: 480
# entries across 8 threads, none lost), which is how the app runs. Several
# interpreters writing the same log concurrently — e.g. a test suite alongside a
# live app — still lose entries to last-writer-wins, though the file stays valid
# JSON. Cross-process safety would need a file lock or an append-only format.
_LOG_LOCK = threading.Lock()
_LOG_WRITE_RETRIES = 5
_LOG_WRITE_BACKOFF_S = 0.02

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
TIER_2_IMPLEMENTED = {
    "send_email",
    "send_whatsapp",
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

    # Append to JSON log file. Serialised and written atomically so a crash or a
    # concurrent reader never truncates the audit trail.
    with _LOG_LOCK:
        history: List[Dict[str, Any]] = []
        if ACTION_LOG_PATH.exists():
            try:
                with open(ACTION_LOG_PATH, "r", encoding="utf-8") as f:
                    history = json.load(f)
                if not isinstance(history, list):
                    raise ValueError("audit log is not a JSON array")
            except Exception:
                # Do NOT silently start over — that discards the whole audit
                # trail. Preserve the unreadable file for inspection first.
                salvage = ACTION_LOG_PATH.with_suffix(
                    f".corrupt-{datetime.now():%Y%m%d-%H%M%S}.json"
                )
                try:
                    os.replace(ACTION_LOG_PATH, salvage)
                except Exception:
                    pass
                history = []

        history.append(entry)

        # The temp name must be unique per process: the lock above is per-process,
        # so two interpreters sharing one temp path would interleave their writes
        # into it and then replace that mixture into place.
        tmp_path = ACTION_LOG_PATH.with_suffix(f".{os.getpid()}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

            # On Windows os.replace raises PermissionError while another process
            # holds the destination open, so retry briefly. Auditing must never
            # take down the action it is recording, hence the swallow at the end.
            for attempt in range(_LOG_WRITE_RETRIES):
                try:
                    os.replace(tmp_path, ACTION_LOG_PATH)
                    break
                except PermissionError:
                    if attempt == _LOG_WRITE_RETRIES - 1:
                        break
                    time.sleep(_LOG_WRITE_BACKOFF_S * (attempt + 1))
        except Exception:
            pass
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    return entry


def get_action_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns the recent action audit logs."""
    if not ACTION_LOG_PATH.exists():
        return []
    try:
        with open(ACTION_LOG_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history[-limit:]
    except Exception:
        return []
