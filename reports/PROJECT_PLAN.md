# Project M.O.N.D.A.Y — Build Plan

Course 24CSE0316 (AI & Machine Learning). Companion to `MONDAY_PRD.md` (product)
and `MONDAY_Academic_CLO_Mapping.md` (rubric mapping). This doc is the **build
plan**: what we build, in what order, who owns it, and what evidence each piece
must produce to satisfy its CLO.

## Scope decision (agreed)

Deliverable = **the five ML components + a thin demo harness** that shows each in
its role. We do **not** build the full MONDAY agent product first; that is
optional stretch. The five comparison notebooks + a small integration demo
satisfy every CLO.

## The dominant risk: cold-start data

Four of five components need data that doesn't exist yet (no real usage). So
**component zero is `datagen/`** — documented synthetic simulators. Assumptions
live in the code in the open (timing model in `action_logs.py`, command
templates in `commands.py`) so the datasets are defensible in the viva, not
"fabricated numbers." Only 2.3 (clustering) can use real external data.

## Build order (dependency-driven)

| Phase | Build | Depends on | Owner |
|-------|-------|-----------|-------|
| 0 | `datagen/` + `common/` | — | Backend + Automation |
| 1 | 2.1 Classifier · 2.3 Clustering | phase 0 (2.1) / real docs (2.3) | AI/ML |
| 2 | 2.2 Regression · 2.4 Assoc mining | phase 0 logs | Backend / Automation |
| 3 | 2.5 RL router | 2.1 confidence + task outcomes | AI/ML |
| 4 | 2.6 XAI · comparative report · harness | trained models | AI/ML + all |

Phases 1 and 2 parallelize across the four owners.

## Definition of done per component

Each component ships three things:
1. a **package** (`ml/<name>/`) with a productionized `predict()`-style entry point,
2. a **notebook** (`notebooks/<n>.ipynb`) with the required model comparison, and
3. **evidence** written to `reports/` (figures + numbers) for the CLO.

| Component | CLO evidence (must appear) |
|-----------|----------------------------|
| 2.1 | confusion matrix, accuracy/precision/recall/F1, 5-model ranking |
| 2.2 | MAE, MSE, RMSE, R² per model |
| 2.3 | silhouette per method, post-PCA cluster plot |
| 2.4 | support/confidence/lift, top-10 rules, Apriori vs FP-Growth timing |
| 2.5 | cumulative reward vs baseline, regret curve, Supervised/Unsupervised/RL write-up |

## CLO coverage (final)

- **CLO01** ethics/agentic design → PRD §9 + report chapter
- **CLO02** ML workflow/tools → NumPy/Pandas/scikit-learn across 2.1–2.4
- **CLO03** regression/feature eng → 2.2 (+ feature pipelines in 2.1/2.3)
- **CLO04** classification + clustering w/ metrics → 2.1 + 2.3
- **CLO05** RL + recommendation/emerging → 2.5 + 2.4
- **CLO06** implement in Python → all of 2.1–2.6 + live demo

## Open items for the team

- [x] Install Python 3.11+ — done. 3.12.10 via the Python Install Manager MSIX;
      the classic MSI is broken on this machine (`0x80070003`). Use `py -3.12`.
- [x] Confirm `MONDAY_PRD.md` lives in the repo — present.
- [x] Decide 2.3 embeddings — TF-IDF. sentence-transformers was not pursued.
- [x] Gather real docs/notes for 2.3 — done; 2.3 ships with evidence.

## Scope note (added 2026-08-07)

The "scope decision" above — five ML components plus a thin harness, with the
agent product as optional stretch — was overtaken by events. The full multi-agent
product was built as well. The graded deliverable is unchanged, but the repo now
contains considerably more than this plan describes; `README.md` is the accurate
description of what exists, and its *Status & Known Limitations* section is the
authoritative list of what does not.

`common/` is **not** orphaned, contrary to an earlier note: it is imported by
`datagen/generate.py` and by `notebooks/2_1_intent_classifier.ipynb`.
