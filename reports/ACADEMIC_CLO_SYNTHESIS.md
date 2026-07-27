# M.O.N.D.A.Y. — Academic CLO Mapping & Empirical Synthesis Report

**Course**: 24CSE0316 — AI & Machine Learning  
**Project**: M.O.N.D.A.Y. (Multi-modal Autonomous Network & Desktop Assistant System)  
**Deliverable**: Comprehensive Empirical Proof & Course Learning Outcome (CLO) Synthesis  

---

## Executive Summary

This synthesis report documents the empirical proof, architectural design, model benchmark evidence, and code line mapping for **Project M.O.N.D.A.Y.** across all six Course Learning Outcomes (CLO01 – CLO06). The system combines classical machine learning pipelines, unsupervised pattern mining, reinforcement learning, multi-agent task execution, and ethical safety boundaries into a cohesive autonomous desktop assistant.

---

## Course Learning Outcome (CLO) Coverage & Mapping

### 1. CLO01: Ethical AI & Agentic System Design
* **Requirement**: Explain ethical considerations, security guardrails, and autonomous agent design principles.
* **Code Implementation**: [`core/security.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/core/security.py) & [`core/autonomy.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/core/autonomy.py)
* **Empirical Evidence**:
  * **Tiered Action Control**: Actions are classified into Tier-1 (read-only / low-risk) and Tier-2 (modifying / high-risk). Tier-2 actions enforce explicit user confirmation dialogues (`data/staging/` isolation and prompt checks).
  * **Confidentiality & Privacy**: OAuth tokens and local SQLite memory databases are explicitly excluded from version control via `.gitignore`.
  * **Human-in-the-Loop Autonomy**: Autonomy levels (Level 0: Advisory to Level 3: Full Autonomous Execution) are dynamically scoped per tool.

---

### 2. CLO02: Modern Machine Learning Workflow & Tooling
* **Requirement**: Apply NumPy, Pandas, scikit-learn, and standard Python ML libraries to preprocess datasets and train models.
* **Code Implementation**: [`common/preprocessing.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/common/preprocessing.py) & [`datagen/generate.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/datagen/generate.py)
* **Empirical Evidence**:
  * Synthetic dataset generation pipelines in `datagen/` produce structured datasets (`commands.csv`, `action_tasks.csv`, `action_sessions.csv`).
  * TF-IDF vectorizers (unigrams + bigrams) and scikit-learn standard scaling pipelines sanitize and transform raw features across components.

---

### 3. CLO03: Regression Modeling & Feature Engineering
* **Requirement**: Implement feature engineering and compare Simple, Multiple, and Polynomial Regression models using standard metrics.
* **Code Implementation**: [`ml/task_eta_regression.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ml/task_eta_regression.py) & [`notebooks/2_2_task_eta_regression.ipynb`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/notebooks/2_2_task_eta_regression.ipynb)
* **Empirical Evidence**:
  * **Artifact**: [`reports/2_2_regression_metrics.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_2_regression_metrics.csv) & [`reports/figures/2_2_regression_comparison.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_2_regression_comparison.png)
  * **Feature Engineering**: One-hot encoding for task types/agents, cyclic encoding ($sin(2\pi h / 24)$, $cos(2\pi h / 24)$) for time-of-day.
  * **Model Comparison Results**:
    * **Simple Linear**: High MAE/RMSE due to single feature limitation.
    * **Multiple Linear**: Captures linear multi-variable overheads.
    * **Polynomial Regression (deg=2)**: Achieves lowest RMSE and highest $R^2$ score by modeling non-linear step count penalties.

---

### 4. CLO04: Classification & Unsupervised Clustering Evaluation
* **Requirement**: Formally compare classification models and clustering algorithms using confusion matrices and Silhouette scores.
* **Code Implementation**: [`ml/intent_classifier.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ml/intent_classifier.py) & [`ml/memory_clustering.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ml/memory_clustering.py)
* **Empirical Evidence**:
  * **Classification (2.1)**:
    * **Artifacts**: [`reports/figures/2_1_confusion_matrix.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_1_confusion_matrix.png) & [`reports/2_1_classification_report.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_1_classification_report.csv)
    * Evaluates Logistic Regression, KNN, Decision Tree, Random Forest, and linear SVM across 6 intent classes.
  * **Clustering (2.3)**:
    * **Artifacts**: [`reports/figures/2_3_pca_clusters.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_3_pca_clusters.png)
    * Compares K-Means ($k=7$), Agglomerative Clustering ($k=7$), and DBSCAN over 64-dimensional memory embeddings mapped via 2D Principal Component Analysis (PCA).

---

### 5. CLO05: Pattern Mining & Reinforcement Learning Systems
* **Requirement**: Implement association rule mining and online reinforcement learning decision systems.
* **Code Implementation**: [`ml/association_rules.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ml/association_rules.py) & [`ml/rl_router.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ml/rl_router.py)
* **Empirical Evidence**:
  * **Pattern Mining (2.4)**:
    * **Artifacts**: [`reports/2_4_top10_association_rules.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_4_top10_association_rules.csv) & [`reports/figures/2_4_apriori_vs_fpgrowth.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_4_apriori_vs_fpgrowth.png)
    * Benchmarks **Apriori** vs **FP-Growth** algorithms on session transaction logs, surfacing repetitive developer workflows (e.g. `{open_vscode, git_status} => {git_commit}`).
  * **Reinforcement Learning (2.5)**:
    * **Artifacts**: [`reports/figures/2_5_rl_reward_curves.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_5_rl_reward_curves.png)
    * Implements an $\epsilon$-Greedy Multi-Armed Bandit router that dynamically optimizes action selection over 1,000 steps, demonstrating superior cumulative reward and declining regret over fixed/random baselines.

---

### 6. CLO06: Complete Python Implementation & Live Web/CLI Integration
* **Requirement**: Deliver a production-grade, integrated Python codebase with working REST API endpoints and web interface.
* **Code Implementation**: [`api/main.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/api/main.py), [`app.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/app.py), [`cli.py`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/cli.py), and [`ui/index.html`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/ui/index.html).
* **Empirical Evidence**: Full end-to-end integration exposing REST API services for intent classification, DAG plan generation, ETA prediction, cluster retrieval, rule mining, and multi-agent execution.

---

## Summary Matrix of Generated Artifacts

| Component | Target Output | Generated File Path | Status |
|---|---|---|---|
| 2.1 Intent Classifier | Confusion Matrix | [`reports/figures/2_1_confusion_matrix.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_1_confusion_matrix.png) | Verified |
| 2.1 Intent Classifier | Precision/Recall CSV | [`reports/2_1_classification_report.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_1_classification_report.csv) | Verified |
| 2.2 Task ETA Regression | RMSE / R² Chart | [`reports/figures/2_2_regression_comparison.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_2_regression_comparison.png) | Verified |
| 2.2 Task ETA Regression | Metrics Table CSV | [`reports/2_2_regression_metrics.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_2_regression_metrics.csv) | Verified |
| 2.3 Memory Clustering | 2D PCA Scatter Plot | [`reports/figures/2_3_pca_clusters.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_3_pca_clusters.png) | Verified |
| 2.4 Association Mining | Apriori vs FP-Growth Plot | [`reports/figures/2_4_apriori_vs_fpgrowth.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_4_apriori_vs_fpgrowth.png) | Verified |
| 2.4 Association Mining | Top 10 Rules CSV | [`reports/2_4_top10_association_rules.csv`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/2_4_top10_association_rules.csv) | Verified |
| 2.5 RL Router | Reward & Regret Curves | [`reports/figures/2_5_rl_reward_curves.png`](file:///c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/reports/figures/2_5_rl_reward_curves.png) | Verified |
