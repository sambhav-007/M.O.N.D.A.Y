# 2.1 Intent Classifier — CLO04 (classification)

**Owner:** AI/ML specialist · **Labs reused:** 14–20 (LogReg, SVM, KNN, Decision Tree)

Routes a raw command into one of 6 intents so high-confidence commands skip the
LLM Planner entirely (real latency/cost win).

## Data
`data/synthetic/commands.csv` — `text, intent`. Regenerate: `python -m datagen.generate`.

## Pipeline
`text → common.preprocessing.clean_text → TF-IDF (common.preprocessing.build_vectorizer) → classifier`

## Models to compare (formal comparison, not a single pick)
Logistic Regression · KNN · Decision Tree · Random Forest · SVM

## Graded evidence (put in `notebooks/2_1_intent_classifier.ipynb`)
- Per-class **confusion matrix**
- **accuracy, precision, recall, F1** (macro + per class) via `common.metrics.classification_metrics`
- A table ranking the 5 models + one paragraph on which wins and why

## Production hook
Expose `predict(text) -> (intent, confidence)`. If `confidence < threshold`,
return `llm_fallback` so the harness routes to the Planner — this is the
low-confidence signal the RL router (2.5) consumes.
