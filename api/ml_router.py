"""
Classical ML Component Endpoints (CLO evidence)
================================================
Exposes the four ML components that were implemented but not yet reachable
over the API, so all five are demoable at /docs:

    2.2  Task ETA Regression      → CLO03   POST /ml/eta/predict
    2.3  Memory Clustering + PCA  → CLO04   GET  /ml/memory/clusters
    2.4  Association Rule Mining   → CLO05   GET  /ml/workflows/rules
    2.5  RL Agent Router (bandit)  → CLO05   GET  /ml/router/policy

(2.1 Intent Classification is already served at /intent/classify.)

These call the SAME trained models the notebooks produce — they run on the
project's documented synthetic datasets, which are the graded deliverable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ml import task_eta_regression as eta
from ml import memory_clustering as mc
from ml import association_rules as ar
from ml import rl_router as rl

router = APIRouter(prefix="/ml")


# ── 2.2  Task ETA Regression (CLO03) ─────────────────────────────────────────
class ETARequest(BaseModel):
    task_type: str = Field("document_intel", description=f"one of {eta.TASK_TYPES}")
    agent: str = Field("browser", description=f"one of {eta.AGENTS}")
    step_count: int = Field(5, ge=1, le=20, description="number of plan steps")
    hour: float = Field(14.0, ge=0, le=24, description="hour of day (0-24)")


@router.post("/eta/predict", tags=["2.2 ETA Regression (CLO03)"])
def predict_eta(req: ETARequest) -> dict:
    """Predicts task completion time (seconds) — feeds the Tier-2 confirmation UI."""
    task_type = req.task_type if req.task_type in eta.TASK_TYPES else "unclear"
    agent = req.agent if req.agent in eta.AGENTS else "planner"
    hist = eta.HISTORICAL_AVG.get(task_type, 20.0)
    row = pd.DataFrame([{
        "task_type": task_type,
        "agent_involved": agent,
        "step_count": float(req.step_count),
        "time_of_day_h": float(req.hour),
        "historical_avg_s": hist,
        "eta_seconds": 0.0,  # placeholder; engineer_features needs the column
    }])
    X, _ = eta.engineer_features(row)
    model = eta.get_trained_regressor()
    pred = float(model.predict(X)[0])
    return {
        "predicted_eta_seconds": round(pred, 2),
        "inputs": {"task_type": task_type, "agent": agent,
                   "step_count": req.step_count, "hour": req.hour},
        "model": "Polynomial Regression (deg=2)",
        "clo": "CLO03",
        "valid_task_types": eta.TASK_TYPES,
        "valid_agents": eta.AGENTS,
    }


# ── 2.3  Memory Clustering + PCA (CLO04) ─────────────────────────────────────
@router.get("/memory/clusters", tags=["2.3 Memory Clustering (CLO04)"])
def memory_clusters(n_samples: int = 700, n_clusters: int = 0) -> dict:
    """Clusters memory embeddings (PCA → K-Means) and reports the silhouette score."""
    if n_clusters <= 0:
        n_clusters = mc.N_TOPICS
    X, _true, texts = mc.generate_memory_embeddings(n_samples=n_samples, seed=42)
    X_cluster, _X_vis, _pca = mc.apply_pca(X)
    labels = mc.cluster_kmeans(X_cluster, n_clusters)
    silhouette = float(mc.evaluate_clustering(X_cluster, labels))

    grouped: dict[int, list[str]] = {}
    for lbl, txt in zip(labels.tolist(), texts):
        grouped.setdefault(int(lbl), []).append(txt)
    clusters = [
        {"cluster": k, "size": len(v), "sample_items": v[:3]}
        for k, v in sorted(grouped.items())
    ]
    return {
        "method": "K-Means on PCA-reduced embeddings",
        "n_clusters": n_clusters,
        "silhouette_score": round(silhouette, 4),
        "clusters": clusters,
        "clo": "CLO04",
    }


# ── 2.4  Association Rule Mining (CLO05) ──────────────────────────────────────
@router.get("/workflows/rules", tags=["2.4 Association Mining (CLO05)"])
def workflow_rules(top_n: int = 10, min_support: float = 0.10,
                   min_confidence: float = 0.55) -> dict:
    """Mines frequent workflows (Apriori vs FP-Growth) and returns the top rules by lift."""
    sessions = ar.generate_session_log()
    encoded = ar.encode_transactions(sessions)
    ap_rules, ap_runtime = ar.run_apriori(encoded, min_support, min_confidence)
    fp_rules, fp_runtime = ar.run_fpgrowth(encoded, min_support, min_confidence)

    top = ap_rules.nlargest(top_n, "lift") if not ap_rules.empty else ap_rules
    rules = [{
        "if": sorted(list(r["antecedents"])),
        "then": sorted(list(r["consequents"])),
        "support": round(float(r["support"]), 3),
        "confidence": round(float(r["confidence"]), 3),
        "lift": round(float(r["lift"]), 3),
    } for _, r in top.iterrows()]

    return {
        "n_sessions": len(sessions),
        "n_rules_found": int(len(ap_rules)),
        "top_rules": rules,
        "runtime_comparison_seconds": {
            "apriori": round(ap_runtime, 4),
            "fpgrowth": round(fp_runtime, 4),
        },
        "clo": "CLO05",
    }


# ── 2.5  RL Agent Router — ε-greedy bandit (CLO05) ───────────────────────────
@router.get("/router/policy", tags=["2.5 RL Router (CLO05)"])
def rl_policy(n_steps: int = 1000) -> dict:
    """Runs the bandit vs a fixed baseline and reports the learned routing policy."""
    rl_rewards, _base_rewards, rl_cum, base_cum = rl.run_simulation(n_steps=n_steps, seed=42)

    # Re-train a bandit to expose the learned Q-values / policy.
    bandit = rl.EpsilonGreedyBandit(seed=42)
    rng = np.random.default_rng(123)
    for _ in range(n_steps):
        a = bandit.select_action()
        bandit.update(a, rl.simulate_reward(a, rng))

    regret = rl.compute_regret(rl_rewards, n_steps)
    q_values = {name: round(float(v), 3)
                for name, v in zip(rl.ROUTING_ACTIONS, bandit.q_values)}

    rl_total, base_total = float(rl_cum[-1]), float(base_cum[-1])
    return {
        "learned_policy": bandit.get_policy(),
        "optimal_action": rl.OPTIMAL_ACTION,
        "q_values": q_values,
        "rl_total_reward": rl_total,
        "baseline_total_reward": base_total,
        "improvement_vs_baseline_pct": round((rl_total - base_total) / max(base_total, 1) * 100, 1),
        "final_regret": round(float(regret[-1]), 2),
        "n_steps": n_steps,
        "clo": "CLO05",
    }


# ── CLO coverage summary ─────────────────────────────────────────────────────
@router.get("/clo-map", tags=["ML Components (CLO Evidence)"])
def clo_map() -> dict:
    """Maps every ML component to its endpoint and CLO."""
    return {
        "2.1 Intent Classification": {"endpoint": "POST /intent/classify", "clo": "CLO04"},
        "2.2 Task ETA Regression": {"endpoint": "POST /ml/eta/predict", "clo": "CLO03"},
        "2.3 Memory Clustering": {"endpoint": "GET /ml/memory/clusters", "clo": "CLO04"},
        "2.4 Association Mining": {"endpoint": "GET /ml/workflows/rules", "clo": "CLO05"},
        "2.5 RL Agent Router": {"endpoint": "GET /ml/router/policy", "clo": "CLO05"},
    }
