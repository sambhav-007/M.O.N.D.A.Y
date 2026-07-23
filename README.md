# Project M.O.N.D.A.Y — Classical ML Layer

Course **24CSE0316 (AI & Machine Learning)** · Jul–Dec 2026 · 4 members.

An LLM-orchestration assistant with **five classical ML components** built inside
it, each a real engineering choice and each mapped 1:1 to a Course Learning
Outcome. This repo is the ML layer + a thin demo harness (not the full product).

## Components → CLO map

| # | Component | Technique | CLO | Package |
|---|-----------|-----------|-----|---------|
| 2.1 | Intent Classifier | Classification | CLO04 | `ml/intent_classifier` |
| 2.2 | Task ETA | Regression | CLO03 | `ml/eta_regression` |
| 2.3 | Memory Clustering | Clustering + PCA | CLO04 | `ml/memory_clustering` |
| 2.4 | Workflow Mining | Association rules | CLO05 | `ml/assoc_mining` |
| 2.5 | Routing Optimizer | RL (bandit) | CLO05 | `ml/rl_router` |
| 2.6 | XAI (bonus) | SHAP/LIME | CLO02/06 | `xai/` |

Full plan and build order: [reports/PROJECT_PLAN.md](reports/PROJECT_PLAN.md).

## Setup

> ⚠️ **Python is not installed on this machine.** Install **Python 3.11+** first
> (https://www.python.org/downloads/), then:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Generate the datasets (do this first — component zero)

```bash
python -m datagen.generate
```

Writes `commands.csv`, `action_tasks.csv`, `action_sessions.csv` into
`data/synthetic/`. Every model reads from there.

## Layout

```
datagen/   synthetic data simulators (build these datasets first)
common/    shared preprocessing, metrics, io
ml/        the five components (see each package README)
notebooks/ the graded model-comparison notebooks
harness/   thin demo tying the models together
xai/       SHAP/LIME bonus
reports/   plan + CLO evidence (figures, comparative report)
```
