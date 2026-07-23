"""Shared vocabulary for all synthetic-data generators.

Everything downstream (classifier, regression, association mining, RL) draws
from these constants so the simulated world stays internally consistent:
a command labeled ``desktop_automation`` maps to the ``computer`` agent, its
action names appear in the session logs, and its timing distribution feeds the
ETA regressor. Keep this file as the single source of truth.
"""

from __future__ import annotations

# The 6 intent categories the router classifies commands into (component 2.1).
INTENTS = [
    "document_intel",
    "communication",
    "browser",
    "desktop_automation",
    "memory_query",
    "llm_fallback",
]

# Which agent handles each intent. `llm_fallback` has no direct agent — it is
# the low-confidence bucket that goes to the Planner (LLM).
INTENT_TO_AGENT = {
    "document_intel": "document_agent",
    "communication": "comms_agent",
    "browser": "browser_agent",
    "desktop_automation": "computer_agent",
    "memory_query": "memory_agent",
    "llm_fallback": "planner_agent",
}

AGENTS = sorted(set(INTENT_TO_AGENT.values()))

# Task "types" used by the ETA regressor (2.2). Each has a rough base duration
# (seconds) and per-step cost; the generator adds noise on top. These numbers
# are documented ASSUMPTIONS of the simulation, not measured values.
TASK_PROFILES = {
    # task_type:        (base_seconds, seconds_per_step, tier)
    "summarize_pdf":    (6.0, 1.8, 2),
    "extract_tables":   (5.0, 2.2, 2),
    "send_email":       (3.0, 1.0, 2),
    "draft_message":    (2.0, 0.8, 1),
    "web_search":       (4.0, 1.5, 1),
    "fill_web_form":    (7.0, 2.5, 2),
    "open_app":         (1.5, 0.5, 1),
    "run_script":       (8.0, 3.0, 2),
    "save_memory":      (1.0, 0.3, 1),
    "recall_memory":    (1.2, 0.4, 1),
}

# Which agent a task type routes to (used to build coherent logs).
TASK_TO_AGENT = {
    "summarize_pdf": "document_agent",
    "extract_tables": "document_agent",
    "send_email": "comms_agent",
    "draft_message": "comms_agent",
    "web_search": "browser_agent",
    "fill_web_form": "browser_agent",
    "open_app": "computer_agent",
    "run_script": "computer_agent",
    "save_memory": "memory_agent",
    "recall_memory": "memory_agent",
}

TASK_TYPES = list(TASK_PROFILES.keys())

RANDOM_SEED = 42
