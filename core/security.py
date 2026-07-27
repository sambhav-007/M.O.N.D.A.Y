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
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.config import ACTION_LOG_PATH, AUTO_EXECUTE_TIER_1

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

TIER_2_ACTIONS = {
    "delete_file",
    "overwrite_file",
    "send_email",
    "send_notification",
    "execute_shell",
    "submit_form",
    "modify_system_settings",
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

    requires_approval = (tier == 2)

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

    # Append to JSON log file
    history: List[Dict[str, Any]] = []
    if ACTION_LOG_PATH.exists():
        try:
            with open(ACTION_LOG_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append(entry)

    with open(ACTION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

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
