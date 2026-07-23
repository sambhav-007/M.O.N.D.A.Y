# 2.2 Task ETA Regression — CLO03

**Owner:** Backend/Systems specialist · **Labs reused:** 8–13 (Linear, Multiple, Polynomial)

Predicts how long a queued task will take so the Tier-2 confirmation UI can show
a realistic ETA ("Est. 12 seconds") before the user approves.

## Data
`data/synthetic/action_tasks.csv`. Target = `duration_sec`.

## Features (feature engineering, CLO03)
`task_type` (one-hot) · `step_count` · `agent` (one-hot) · `hour` (time of day) · `historical_avg`

## Models to compare (in lab order)
Simple Linear → Multiple Linear → Polynomial Regression

## Graded evidence (`notebooks/2_2_eta_regression.ipynb`)
- **MAE, MSE, RMSE, R²** per model via `common.metrics.regression_metrics`
- Best model deployed; short justification. Watch polynomial degree for overfit.

## Production hook
`predict_eta(task_features) -> seconds` feeding the Tier-2 approval flow.
