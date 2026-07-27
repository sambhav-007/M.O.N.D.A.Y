# Final Project Proposal — Project M.O.N.D.A.Y.
## Academic Version — Fully Mapped to Course 24CSE0316 (AI & Machine Learning) CLOs

**Course**: Artificial Intelligence and Machine Learning (24CSE0316)  
**Course Coordinator**: Dr. Priyanka Gupta  
**Session**: July–Dec 2026  
**Team Size**: 4 members (Siddhant Bhatia, Sambhav Sehgal, Samarth Sharma, Shivansh Chandel)  

---

## 1. Five Classical ML Components (Mapped 1:1 to Lab Plan)

| # | ML Component | CLO Mapping | Lab Reference | Production Role |
|---|--------------|-------------|---------------|-----------------|
| **2.1** | **Intent Classification Model** | **CLO04** (Classification) | Lab 14–20 (Logistic Reg, SVM, KNN, Decision Tree, Random Forest) | Routes incoming user commands to target agents. High confidence skips LLM. |
| **2.2** | **Task ETA Regression Model** | **CLO03** (Regression & Feature Engineering) | Lab 8–13 (Simple, Multiple, Polynomial Regression) | Predicts execution time in seconds to feed the Tier-2 confirmation prompt ("Est. 12s — Approve?"). |
| **2.3** | **Memory/Document Clustering** | **CLO04** (Clustering) | Lab 21–26 (K-Means, DBSCAN, Hierarchical, PCA) | Organises Memory Agent entries into topic clusters; powers proactive user suggestions. |
| **2.4** | **Association Rule Mining** | **CLO05** (Pattern Mining) | Lecture/Lab (Apriori, FP-Growth, Market Basket Analysis) | Mines user session action logs to detect repetitive habits and suggest automations. |
| **2.5** | **RL Agent Router** | **CLO05** (Reinforcement Learning) | Lecture 28–30 (RL, agent/environment/reward/policy) | Multi-armed ε-greedy bandit that learns optimal agent routing strategy from task outcomes. |
| **2.6** | **XAI Layer (Bonus)** | **CLO02 / CLO06** (Beyond Syllabus) | SHAP (SHapley Additive exPlanations) | Explains feature importances for intent classification and ETA predictions. |

---

## 2. Final CLO Coverage Grid

| CLO | Requirement | Satisfied By | Assessment Evidence |
|-----|-------------|--------------|---------------------|
| **CLO01** | AI concepts, evolution, ethics | Full PRD §9 (safety/permission model), agentic AI design, ethics of automation | Report chapter + viva discussion |
| **CLO02** | ML workflows, Python/tools | Full pipeline: NumPy, Pandas, scikit-learn used across 2.1–2.6 | Codebase + notebooks |
| **CLO03** | Preprocessing, feature engineering, regression | Component 2.2 (ETA Regression) + feature pipelines in 2.1/2.3 | MAE/MSE/RMSE/R² report |
| **CLO04** | Classification & clustering with metrics | Component 2.1 (classification) + Component 2.3 (clustering) | Confusion matrix, F1, Silhouette Score |
| **CLO05** | RL, recommendation systems, emerging tech | Component 2.5 (RL) + Component 2.4 (association rules/pattern recommendation) | Cumulative reward curve, regret curve, rule support/confidence/lift |
| **CLO06** | Implement AI/ML algorithms in Python | All of 2.1–2.6 implemented and demoed | Live demo + GitHub repo |

---

## 3. Assessment Scheme Alignment

| Course Component | Weight | What MONDAY Submits |
|------------------|--------|---------------------|
| **Continuous Evaluation (CE)** | 20% | Component 2.1 (classifier) working demo + notebook |
| **Sessional Test (ST-1)** | 20% | Written coverage of clustering/association rule/PCA concepts as applied in 2.3/2.4 |
| **End Term — Project-Based** | 30% | Full integrated MONDAY system demo: all 5 ML components + agent architecture live |
| **End Term — MCQ** | 30% | Standard course MCQ exam |
