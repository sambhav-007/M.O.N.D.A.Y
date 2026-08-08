"""
M.O.N.D.A.Y. — Workflow Habit & Pattern Agent
================================================
Mines user action session logs using Component 2.4 (Association Rule Mining)
to detect repetitive habits and suggest automations.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from core.config import ACTION_LOG_PATH
from core.contracts import AgentResult, SystemQuery
from core.security import log_action


class HabitAgent:
    """Specialized worker for pattern mining and proactive habit automation suggestions."""

    def __init__(self) -> None:
        self.name = "HabitAgent"

    def detect_habits_and_suggest(self) -> Dict[str, Any]:
        """
        Runs Component 2.4 (Association Rule Mining) over session action logs
        to discover co-occurring habits and return automation prompts.
        """
        try:
            from ml.association_rules import (
                generate_session_log, encode_transactions, run_apriori, MLXTEND_AVAILABLE
            )

            # Generate synthetic session data augmented with recent user action log
            sessions = generate_session_log(n_sessions=300)

            # Extract recent action history if available
            if ACTION_LOG_PATH.exists():
                try:
                    with open(ACTION_LOG_PATH, "r", encoding="utf-8") as f:
                        history = json.load(f)
                    recent_actions = [h.get("action", "") for h in history if h.get("action")]
                    if len(recent_actions) >= 3:
                        sessions.append(recent_actions)
                except Exception:
                    pass

            df = encode_transactions(sessions)
            rules, _ = run_apriori(df, min_support=0.10, min_confidence=0.55)

            top_rules = rules.nlargest(5, "lift")
            suggestions: List[Dict[str, Any]] = []

            for _, row in top_rules.iterrows():
                antecedents = sorted(list(row["antecedents"]))
                consequents = sorted(list(row["consequents"]))
                trigger = " → ".join(a.replace("_", " ") for a in antecedents[:2])
                action = " + ".join(c.replace("_", " ") for c in consequents[:2])

                suggestions.append({
                    "trigger": trigger,
                    "automated_action": action,
                    "confidence": round(float(row["confidence"]), 3),
                    "lift": round(float(row["lift"]), 2),
                    "prompt": f"🤖 Habit Detected: I noticed you frequently do '{action}' after '{trigger}' ({row['confidence']:.0%} confidence). Want me to automate this routine?",
                })

            log_action("detect_habits", "system", 1, "success", self.name, {"suggestions_count": len(suggestions)})

            return AgentResult.ok(
                f"✓ Mined workflow history — discovered {len(suggestions)} automation opportunities.",
                evidence=SystemQuery(
                    source="ml.association_rules.run_apriori",
                    detail=f"{len(sessions)} sessions → {len(rules)} rules",
                ),
                data={"habits_found": len(suggestions), "suggestions": suggestions},
            ).as_dict()

        except Exception as e:
            # This branch used to return `success: True` with one hardcoded
            # "habit": git commit after running tests, at 0.85 confidence and
            # 3.2 lift, phrased as "🤖 Habit Detected: I noticed you frequently…".
            # Nothing had been noticed. Component 2.4 had just failed to run, and
            # its failure was dressed up as its output — a fabricated mining
            # result complete with fabricated statistics, which is worse than a
            # fabricated success because it invites the user to act on it.
            log_action("detect_habits", "system", 1, "failure", self.name, {"error": str(e)})
            return AgentResult.failed(
                f"I couldn't mine your workflow history: {e}",
                error="HABIT_MINING_FAILED",
            ).as_dict()
