# 2.4 Association Rule Mining — CLO05 (pattern recommendation)

**Owner:** Automation/DevOps specialist · **Reuses:** Apriori, FP-Growth, Market Basket Analysis

Treats each session's action sequence as a basket and mines frequent action-sets
to detect repetitive workflows worth automating.

## Data
`data/synthetic/action_sessions.csv` — `session_id, items` (space-separated task types).
The generator plants known workflows (documented in `datagen/action_logs.py`), e.g.
`open_app → run_script → send_email`, so you have a **checkable ground truth**.

## Models to compare
Apriori vs FP-Growth (use `mlxtend`), compared on **runtime** over the dataset.

## Graded evidence (`notebooks/2_4_assoc_mining.ipynb`)
- **support, confidence, lift** for discovered rules
- **Top 10 rules**; confirm the planted workflows appear
- Apriori vs FP-Growth timing comparison

## Production hook
Surfaces "I noticed you always do X after Y — automate this?" prompts.
