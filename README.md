# 🤖 Project M.O.N.D.A.Y.

<div align="center">

**Modular Operational Neural Desktop Assistant for You**

*An AI agent that doesn't just chat with you — it actually does tasks for you.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.4+-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)](https://scikit-learn.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Course](https://img.shields.io/badge/Course-24CSE0316-7C3AED?style=flat-square)](.)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Overview

M.O.N.D.A.Y. is a multi-agent AI assistant built around **five classical ML components**, each doing genuine work inside the system and each mapped 1-to-1 to a Course Learning Outcome (CLO) from **24CSE0316 — Artificial Intelligence and Machine Learning**.

This folder (`M.O.N.D.A.Y/`) contains the complete Python ML backend. For the full product architecture and website, see the companion [`monday-site/`](../monday-site/) folder.

---

## The Five ML Components

| # | Module | CLO | Technique | Production Role |
|---|--------|-----|-----------|-----------------|
| 2.1 | [`intent_classifier.py`](ml/intent_classifier.py) | **CLO04** | Logistic Reg / KNN / Decision Tree / Random Forest / SVM | Routes commands, skips LLM for simple intents |
| 2.2 | [`task_eta_regression.py`](ml/task_eta_regression.py) | **CLO03** | Simple / Multiple / Polynomial Regression | Feeds Tier-2 confirmation UI with task ETA |
| 2.3 | [`memory_clustering.py`](ml/memory_clustering.py) | **CLO04** | K-Means / DBSCAN / Hierarchical + PCA | Organises Memory Agent, enables proactive suggestions |
| 2.4 | [`association_rules.py`](ml/association_rules.py) | **CLO05** | Apriori / FP-Growth | Detects repetitive workflows, suggests automation |
| 2.5 | [`rl_router.py`](ml/rl_router.py) | **CLO05** | ε-greedy Multi-Armed Bandit | Learns optimal agent routing from task outcomes |
| 2.6 | [`xai_explainer.py`](ml/xai_explainer.py) | **CLO02/CLO06** (Bonus) | SHAP | Explains classifier and regressor predictions |

---

## CLO Coverage Map

```
CLO01  AI Concepts & Ethics      ←  Full PRD §9 safety/permission model
CLO02  ML Workflows & Tools      ←  All 5 modules use NumPy/Pandas/scikit-learn
CLO03  Regression                ←  Component 2.2 (Task ETA)
CLO04  Classification+Clustering ←  Component 2.1 (Intent) + 2.3 (Memory)
CLO05  RL & Pattern Mining       ←  Component 2.4 (Assoc Rules) + 2.5 (RL)
CLO06  Implement in Python       ←  All of 2.1–2.6 + live FastAPI demo
```

---

## Folder Structure

```
M.O.N.D.A.Y/
├── app.py                        # Desktop Living Entity Shell launcher
├── ui/                           # WebGL 3D Living Entity Desktop UI
│   └── index.html                # Audio-reactive WebGL 3D entity & LOD performance controls
├── ml/
│   ├── __init__.py
│   ├── intent_classifier.py      # CLO04 — 5-model classification comparison
│   ├── task_eta_regression.py    # CLO03 — 3-model regression comparison
│   ├── memory_clustering.py      # CLO04 — 3-method clustering + PCA
│   ├── association_rules.py      # CLO05 — Apriori + FP-Growth comparison
│   ├── rl_router.py              # CLO05 — ε-greedy bandit + comparative report
│   └── xai_explainer.py          # CLO02/06 Bonus — SHAP explanations
├── api/
│   ├── __init__.py
│   └── main.py                   # FastAPI demo server (all endpoints + /app UI)
├── models/                       # Saved models (created at runtime)
├── data/                         # Synthetic datasets (generated in-code)
├── requirements.txt
├── .env.example
├── README.md                     # This file
├── MONDAY_ACADEMIC.md            # Full academic CLO-mapping document
└── MONDAY_PRD.md                 # Product Requirements Document
```

---

## 🖥️ Living 3D AI Entity Desktop Shell

M.O.N.D.A.Y. features a **Python + WebGL Native Desktop Application Shell (`app.py` & `ui/index.html`)** rendering the living molten gold AI entity in real time:
- **Frameless OS Window**: Borderless window execution (`frameless=True`) with native JavaScript bridge (`DesktopWindowApi`) supporting `✕` close, `—` minimize, and `Esc` keyboard shortcut.
- **Dual Presentation Modes**:
  - **Presence Mode** (Default): Fullscreen 3D WebGL Living Entity with zero app chrome. Entity states (`idle`, `listening`, `thinking`, `speaking`) are communicated 100% visually through an audio-reactive particle field and GLSL Fresnel rim lighting shader. Push-to-talk via Spacebar.
  - **Console Mode**: Full developer diagnostic console with real-time multi-agent execution logs and command input. Toggleable via `Ctrl+``.
- **Multi-Turn Clarification Engine (`pending_clarification`)**: Interactive task pausing, candidate disambiguation, SQLite memory caching, and task resumption.
- **Live Google People API & Outlook COM Contacts**: Native OAuth2 Google Contacts sync (`data/google_token.json`) and Windows Outlook MAPI contacts resolution with zero hardcoded/mock fallback data.
- **WebGL 3D Engine & LOD Performance Control**: 8,000 particle fields, GLSL Fresnel rim-light core, and torus energy ring. Toggle between High (8,000 p), Balanced (4,000 p), and Battery Saver (1,800 p) with real-time FPS monitoring.

---

## Quick Start

### 1. Set up environment

```bash
# From the M.O.N.D.A.Y/ directory
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Copy environment variables

```bash
cp .env.example .env
```

### 3. Run individual ML modules

```bash
# Component 2.1 — Intent Classifier (CLO04)
python -m ml.intent_classifier

# Component 2.2 — Task ETA Regression (CLO03)
python -m ml.task_eta_regression

# Component 2.3 — Memory Clustering (CLO04)
python -m ml.memory_clustering

# Component 2.4 — Association Rule Mining (CLO05)
python -m ml.association_rules

# Component 2.5 — RL Agent Router (CLO05)
python -m ml.rl_router

# Component 2.6 — XAI Bonus (CLO02/CLO06)
python -m ml.xai_explainer
```

### 4. Start the FastAPI demo server

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Endpoints

| Method | Endpoint | Component | Description |
|--------|----------|-----------|-------------|
| `GET` | `/` | — | Health check |
| `POST` | `/intent/classify` | 2.1 | Classify command intent |
| `POST` | `/task/predict-eta` | 2.2 | Predict task completion time |
| `GET` | `/memory/clusters` | 2.3 | Get memory topic clusters |
| `GET` | `/workflows/rules` | 2.4 | Get top workflow rules |
| `POST` | `/router/decide` | 2.5 | RL bandit routing decision |
| `GET` | `/clo-map` | — | Academic CLO mapping reference |

### Example: Classify Intent

```bash
curl -X POST http://localhost:8000/intent/classify \
  -H "Content-Type: application/json" \
  -d '{"command": "please summarize the quarterly report PDF", "confidence_threshold": 0.65}'
```

Response:
```json
{
  "command": "please summarize the quarterly report PDF",
  "predicted_intent": "document_intel",
  "confidence": 0.9213,
  "llm_fallback_required": false,
  "component": "2.1 — Intent Classifier",
  "clo": "CLO04"
}
```

### Example: Predict Task ETA

```bash
curl -X POST http://localhost:8000/task/predict-eta \
  -H "Content-Type: application/json" \
  -d '{"task_type": "browser", "agent_involved": "browser", "step_count": 7, "time_of_day_h": 14.5}'
```

---

## Evaluation Metrics (per module)

### Component 2.1 — Intent Classifier
- **Confusion matrix** (6×6)
- **Accuracy, Precision, Recall, F1** per class
- **Macro-averaged F1** for model comparison

### Component 2.2 — Task ETA Regression
- **MAE** (Mean Absolute Error)
- **MSE** (Mean Squared Error)
- **RMSE** (Root Mean Squared Error)
- **R² Score**

### Component 2.3 — Memory Clustering
- **Silhouette Score** per method
- Cluster size distribution
- PCA variance explained

### Component 2.4 — Association Rules
- **Support** (frequency)
- **Confidence** (accuracy of rule)
- **Lift** (strength vs. random)
- Apriori vs. FP-Growth runtime comparison

### Component 2.5 — RL Router
- **Cumulative reward** over time vs. fixed baseline
- **Regret curve**
- Learned Q-values per routing action

---

## Tech Stack

All libraries are within the course-approved ecosystem:

| Library | Version | Purpose |
|---------|---------|---------|
| `scikit-learn` | ≥1.4 | All classical ML (classify, regression, cluster) |
| `pandas` | ≥2.1 | Data manipulation and feature engineering |
| `numpy` | ≥1.26 | Numerical computation |
| `mlxtend` | ≥0.23 | Apriori and FP-Growth |
| `shap` | ≥0.44 | XAI explanations (bonus) |
| `fastapi` | ≥0.111 | Demo REST API server |
| `rich` | ≥13.7 | Beautiful console output |

---

## Team

| Name | Role | Speciality |
|------|------|------------|
| **Siddhant Bhatia** | Founder & Lead Architect | Core vision, coordination |
| **Sambhav Sehgal** | AI & Intelligence Lead | Models, reasoning, CLO04 |
| **Samarth Sharma** | ML Engineer | Neural systems, CLO03/05 |
| **Shivansh Chandel** | Infrastructure & Platform | Security, distribution |

**Course Coordinator**: Dr. Priyanka Gupta
**Session**: July–December 2026

---

## License

MIT License — see [LICENSE](LICENSE) for details.
