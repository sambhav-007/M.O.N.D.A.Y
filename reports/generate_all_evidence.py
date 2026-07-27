"""
M.O.N.D.A.Y. — Complete Academic Evidence Generator
===================================================
Executes all 5 ML components (2.1 to 2.5), produces high-resolution PNG
figures, and exports evaluation CSV tables into the reports/ directory
to satisfy all course CLO requirements (CLO01 – CLO06).
"""

import os
import sys
import time
import warnings
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay, classification_report
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.metrics import silhouette_score

warnings.filterwarnings("ignore")

# Output Directories
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


def generate_2_1_evidence():
    """Generates 2.1 Intent Classifier confusion matrix and report."""
    print("Generating Component 2.1 evidence (Intent Classifier)...")
    from ml.intent_classifier import (
        build_synthetic_dataset,
        build_pipelines,
        INTENT_CLASSES
    )
    df = build_synthetic_dataset(samples_per_class=300)
    X, y = df["command"].tolist(), df["intent"].tolist()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    pipeline = build_pipelines()["Logistic Regression"]
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    
    labels = sorted(list(set(y)))
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    
    fig, ax = plt.subplots(figsize=(8, 6))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(cmap="Blues", ax=ax, xticks_rotation=45)
    ax.set_title("2.1 Intent Classifier Confusion Matrix (Logistic Regression)")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "2_1_confusion_matrix.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    
    report_dict = classification_report(y_test, y_pred, output_dict=True)
    report_df = pd.DataFrame(report_dict).transpose()
    report_df.to_csv(REPORTS_DIR / "2_1_classification_report.csv")
    print("✓ Component 2.1 evidence saved.")


def generate_2_2_evidence():
    """Generates 2.2 Task ETA Regression metrics and plots."""
    print("Generating Component 2.2 evidence (Task ETA Regression)...")
    from ml.task_eta_regression import (
        generate_action_log,
        engineer_features,
        train_simple_linear,
        train_multiple_linear,
        train_polynomial,
        TASK_TYPES, AGENTS
    )
    df = generate_action_log(n_samples=2000, seed=42)
    X, y = engineer_features(df)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    feature_cols = (
        [f"task_{t}" for t in TASK_TYPES] +
        [f"agent_{a}" for a in AGENTS] +
        ["step_count", "historical_avg_s", "tod_sin", "tod_cos"]
    )
    step_idx = feature_cols.index("step_count")
    
    _, m_simple = train_simple_linear(X_train, X_test, y_train, y_test, step_idx)
    _, m_multiple = train_multiple_linear(X_train, X_test, y_train, y_test)
    _, m_poly = train_polynomial(X_train, X_test, y_train, y_test, degree=2)
    
    res_df = pd.DataFrame([
        {"Model": "Simple Linear", **m_simple},
        {"Model": "Multiple Linear", **m_multiple},
        {"Model": "Polynomial (deg=2)", **m_poly}
    ]).set_index("Model")
    
    res_df.to_csv(REPORTS_DIR / "2_2_regression_metrics.csv")
    
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    res_df["RMSE"].plot(kind="bar", color=["salmon", "orange", "lightgreen"], ax=ax[0])
    ax[0].set_title("Regression RMSE Comparison (Lower is Better)")
    ax[0].set_ylabel("RMSE (seconds)")
    
    res_df["R²"].plot(kind="bar", color=["salmon", "orange", "lightgreen"], ax=ax[1])
    ax[1].set_title("Regression R² Score Comparison (Higher is Better)")
    ax[1].set_ylabel("R² Score")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "2_2_regression_comparison.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("✓ Component 2.2 evidence saved.")


def generate_2_3_evidence():
    """Generates 2.3 Memory Clustering PCA plot and silhouette scores."""
    print("Generating Component 2.3 evidence (Memory Clustering)...")
    from ml.memory_clustering import (
        generate_memory_embeddings,
        N_TOPICS
    )
    embeddings, _, _ = generate_memory_embeddings(n_samples=700, seed=42)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(embeddings)
    
    pca = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_scaled)
    
    kmeans = KMeans(n_clusters=N_TOPICS, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    sil = silhouette_score(X_scaled, labels)
    
    fig, ax = plt.subplots(figsize=(7, 5))
    scatter = ax.scatter(X_pca[:, 0], X_pca[:, 1], c=labels, cmap="tab10", alpha=0.7, s=25)
    ax.set_title(f"2D PCA Memory Clusters (K-Means, Silhouette: {sil:.3f})")
    ax.set_xlabel("PCA Component 1")
    ax.set_ylabel("PCA Component 2")
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "2_3_pca_clusters.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("✓ Component 2.3 evidence saved.")


def generate_2_4_evidence():
    """Generates 2.4 Association Rule Mining top 10 rules and benchmark."""
    print("Generating Component 2.4 evidence (Association Mining)...")
    from ml.association_rules import (
        generate_session_log,
        encode_transactions,
        run_apriori,
        run_fpgrowth,
        MLXTEND_AVAILABLE
    )
    sessions = generate_session_log(n_sessions=1000, seed=42)
    
    if MLXTEND_AVAILABLE:
        df_encoded = encode_transactions(sessions)
        rules_ap, time_ap = run_apriori(df_encoded, min_support=0.05, min_confidence=0.5)
        rules_fp, time_fp = run_fpgrowth(df_encoded, min_support=0.05, min_confidence=0.5)
        
        if not rules_fp.empty:
            top10 = rules_fp.sort_values(by="lift", ascending=False).head(10)
            top10.to_csv(REPORTS_DIR / "2_4_top10_association_rules.csv", index=False)
            
        fig, ax = plt.subplots(figsize=(6, 4))
        pd.Series({"Apriori": time_ap, "FP-Growth": time_fp}).plot(kind="bar", color=["coral", "seagreen"], ax=ax)
        ax.set_title("Apriori vs FP-Growth Execution Time (s)")
        ax.set_ylabel("Seconds")
        plt.tight_layout()
        fig.savefig(FIGURES_DIR / "2_4_apriori_vs_fpgrowth.png", dpi=300, bbox_inches="tight")
        plt.close(fig)
    print("✓ Component 2.4 evidence saved.")


def generate_2_5_evidence():
    """Generates 2.5 RL Router reward & regret curves."""
    print("Generating Component 2.5 evidence (RL Router)...")
    from ml.rl_router import (
        EpsilonGreedyBandit,
        simulate_reward,
        ROUTING_ACTIONS,
        OPTIMAL_REWARD
    )
    n_steps = 1000
    bandit = EpsilonGreedyBandit(n_arms=len(ROUTING_ACTIONS), epsilon=0.3, epsilon_decay=0.995, seed=42)
    
    rewards_bandit, rewards_random, rewards_fixed = [], [], []
    rng = np.random.default_rng(42)
    
    for step in range(n_steps):
        act_idx = bandit.select_action()
        r_b = simulate_reward(act_idx, rng=rng)
        bandit.update(act_idx, r_b)
        rewards_bandit.append(r_b)
        
        rand_idx = rng.integers(0, len(ROUTING_ACTIONS))
        r_rand = simulate_reward(rand_idx, rng=rng)
        rewards_random.append(r_rand)
        
        clarify_idx = ROUTING_ACTIONS.index("clarify_user")
        r_fix = simulate_reward(clarify_idx, rng=rng)
        rewards_fixed.append(r_fix)
        
    cum_b = np.cumsum(rewards_bandit)
    cum_r = np.cumsum(rewards_random)
    cum_f = np.cumsum(rewards_fixed)
    regret_b = np.cumsum(OPTIMAL_REWARD - np.array(rewards_bandit))
    
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    ax[0].plot(cum_b, label="RL Bandit", color="mediumseagreen", linewidth=2)
    ax[0].plot(cum_r, label="Random Baseline", color="gray", linestyle="--")
    ax[0].plot(cum_f, label="Fixed Baseline", color="crimson", linestyle=":")
    ax[0].set_title("Cumulative Reward over Time")
    ax[0].set_xlabel("Steps")
    ax[0].set_ylabel("Accumulated Reward")
    ax[0].legend()
    
    ax[1].plot(regret_b, label="RL Bandit Regret", color="mediumseagreen", linewidth=2)
    ax[1].set_title("Cumulative Regret over Time")
    ax[1].set_xlabel("Steps")
    ax[1].set_ylabel("Regret")
    ax[1].legend()
    
    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "2_5_rl_reward_curves.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("✓ Component 2.5 evidence saved.")


def main():
    print("==================================================")
    print("M.O.N.D.A.Y. — Academic Evidence Generation Suite")
    print("==================================================")
    generate_2_1_evidence()
    generate_2_2_evidence()
    generate_2_3_evidence()
    generate_2_4_evidence()
    generate_2_5_evidence()
    print("\n✓ All academic report figures and metric CSVs generated successfully!")


if __name__ == "__main__":
    main()
