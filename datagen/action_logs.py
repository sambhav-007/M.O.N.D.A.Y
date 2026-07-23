"""Synthetic action-log generator — the shared substrate for components
2.2 (ETA regression), 2.4 (association mining), and 2.5 (RL router).

We simulate USER SESSIONS. Each session is an ordered basket of task executions.
Two products come out of the same simulation so the components stay consistent:

  * a flat TASK-LEVEL table (one row per executed task) -> features + duration
    for the regressor, and reward/outcome signal for the RL router;
  * a SESSION table (space-separated task types per session) -> baskets for
    Apriori / FP-Growth.

Baked-in structure the miners are *meant* to rediscover (documented ground truth):
  - open_app -> run_script -> send_email  (a "ship it" workflow)
  - summarize_pdf -> save_memory          (read then remember)
  - web_search -> fill_web_form           (research then submit)
These recurring co-occurrences are what association mining should surface, and
give the demo a checkable answer.
"""

from __future__ import annotations

import random

import numpy as np
import pandas as pd

from .config import RANDOM_SEED, TASK_PROFILES, TASK_TO_AGENT

# Frequent workflows planted in the data (basket -> relative frequency weight).
_WORKFLOWS = [
    (["open_app", "run_script", "send_email"], 4),
    (["summarize_pdf", "save_memory"], 3),
    (["web_search", "fill_web_form"], 3),
    (["extract_tables", "draft_message"], 2),
    (["recall_memory", "open_app", "run_script"], 2),
]
_SINGLETONS = list(TASK_PROFILES.keys())


def _duration(task_type: str, step_count: int, hour: int, rng: random.Random) -> float:
    """Ground-truth timing model the regressor tries to recover.

    duration = base + per_step*steps + mild time-of-day load + noise.
    Late-night (0-6h) runs a bit slower to give ``time_of_day`` real signal.
    """
    base, per_step, _tier = TASK_PROFILES[task_type]
    load = 1.15 if hour < 6 else (1.05 if hour >= 20 else 1.0)
    mean = (base + per_step * step_count) * load
    return max(0.3, rng.gauss(mean, mean * 0.12))


def _pick_basket(rng: random.Random) -> list[str]:
    # ~70% of sessions draw from a planted workflow, else random singletons.
    if rng.random() < 0.70:
        pool = []
        for wf, w in _WORKFLOWS:
            pool.extend([tuple(wf)] * w)
        basket = list(rng.choice(pool))
    else:
        basket = rng.sample(_SINGLETONS, k=rng.randint(1, 3))
    # occasionally tack on a stray task
    if rng.random() < 0.25:
        basket.append(rng.choice(_SINGLETONS))
    return basket


def generate_logs(n_sessions: int = 1200, seed: int = RANDOM_SEED):
    """Return ``(tasks_df, sessions_df)``.

    tasks_df columns: session_id, task_type, agent, step_count, hour,
                      historical_avg, duration_sec, tier, outcome, routing_arm
    sessions_df columns: session_id, items (space-separated task types)
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    task_rows, session_rows = [], []
    # running historical average per task type (models the "historical avg" feature)
    hist = {t: TASK_PROFILES[t][0] + TASK_PROFILES[t][1] * 3 for t in TASK_PROFILES}
    hist_n = {t: 1 for t in TASK_PROFILES}

    for sid in range(n_sessions):
        basket = _pick_basket(rng)
        hour = int(np_rng.integers(0, 24))
        session_rows.append({"session_id": sid, "items": " ".join(basket)})

        for task_type in basket:
            step_count = int(np_rng.integers(1, 8))
            dur = _duration(task_type, step_count, hour, rng)

            # update running historical average BEFORE recording the feature
            prev_avg = hist[task_type] / hist_n[task_type]

            # RL substrate: which routing arm was tried, and did it succeed?
            arm = rng.choice(["direct_dispatch", "planner_llm", "cached_plan"])
            # ground-truth success propensity per arm (what RL should learn)
            p_success = {"direct_dispatch": 0.82, "planner_llm": 0.90, "cached_plan": 0.68}[arm]
            outcome = "success" if rng.random() < p_success else "corrected"

            task_rows.append({
                "session_id": sid,
                "task_type": task_type,
                "agent": TASK_TO_AGENT[task_type],
                "step_count": step_count,
                "hour": hour,
                "historical_avg": round(prev_avg, 3),
                "duration_sec": round(dur, 3),
                "tier": TASK_PROFILES[task_type][2],
                "routing_arm": arm,
                "outcome": outcome,
            })

            hist[task_type] += dur
            hist_n[task_type] += 1

    return pd.DataFrame(task_rows), pd.DataFrame(session_rows)
