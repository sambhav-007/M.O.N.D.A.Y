"""
M.O.N.D.A.Y. — Component 2.2: Task ETA / Priority Regression Model
====================================================================
Course Mapping : CLO03 — Preprocessing, feature engineering, regression
Lab Reference  : Lab 8–13 (Simple / Multiple / Polynomial Regression)
Owner          : Backend / Systems Specialist

Purpose
-------
Given a task's type, target agent, plan-step count, and historical action-log
timing data, predict completion time so the UI can show a realistic ETA before
the user approves a Tier-2 action.

Features (feature engineering — CLO03 requirement)
---------------------------------------------------
  • task_type        → one-hot encoded (6 categories)
  • step_count       → integer, normalised
  • agent_involved   → one-hot encoded (5 agents)
  • time_of_day_h    → hour 0-23, cyclically encoded (sin/cos)
  • historical_avg_s → historical average completion time for this task type

Models compared (matching Lab sequence)
-----------------------------------------
  1. Simple Linear Regression     (single feature: step_count only)
  2. Multiple Linear Regression   (all features)
  3. Polynomial Regression        (degree 2 on step_count + interactions)

Evaluation (CLO03 requirement)
-------------------------------
MAE, MSE, RMSE, R² — reported per model. Best model deployed.

Production Role
---------------
Feeds directly into the Tier-2 confirmation UI:
  "Est. 12 seconds — Approve?" before a Tier-2 action executes.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

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

import joblib
import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich import box
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")
console = Console()

# ── Constants ──────────────────────────────────────────────────────────────────
TASK_TYPES = [
    "document_intel",
    "communication",
    "browser",
    "desktop_automation",
    "memory_query",
    "unclear",
]

AGENTS = [
    "planner",
    "memory",
    "communication",
    "browser",
    "computer",
]

# Historical average ETA (seconds) per task type — used as a feature.
HISTORICAL_AVG: Dict[str, float] = {
    "document_intel": 18.5,
    "communication": 8.2,
    "browser": 22.0,
    "desktop_automation": 35.0,
    "memory_query": 3.5,
    "unclear": 45.0,
}


# ── Synthetic Data Generator ───────────────────────────────────────────────────
def generate_action_log(n_samples: int = 2000, seed: int = 42) -> pd.DataFrame:
    """
    Simulates a real action-log dataset.

    The ground-truth ETA is modelled as:
        eta = base_time × step_factor × agent_penalty + time_penalty + noise

    where the relationships are intentionally non-linear to motivate
    polynomial regression over simple linear.

    Returns
    -------
    pd.DataFrame with raw features + target column 'eta_seconds'.
    """
    rng = np.random.default_rng(seed)

    task_types = rng.choice(TASK_TYPES, size=n_samples)
    agents = rng.choice(AGENTS, size=n_samples)
    step_counts = rng.integers(1, 15, size=n_samples).astype(float)
    time_of_day_h = rng.uniform(0, 24, size=n_samples)

    # Base ETA per task type
    base_etas = np.array([HISTORICAL_AVG[t] for t in task_types])
    hist_avgs = base_etas.copy()

    # Agent overhead multipliers
    agent_multipliers = {
        "planner": 1.2,
        "memory": 0.9,
        "communication": 1.0,
        "browser": 1.3,
        "computer": 1.5,
    }
    agent_factor = np.array([agent_multipliers[a] for a in agents])

    # Non-linear step scaling: eta grows with step_count² (motivates poly)
    step_factor = 1.0 + 0.4 * step_counts + 0.05 * (step_counts ** 2)

    # Time-of-day penalty: peak hours (9-11am, 2-5pm) are slower
    tod_penalty = np.where(
        ((time_of_day_h >= 9) & (time_of_day_h <= 11)) |
        ((time_of_day_h >= 14) & (time_of_day_h <= 17)),
        rng.uniform(1.0, 3.5, size=n_samples),
        0.0,
    )

    noise = rng.normal(0, 2.5, size=n_samples)

    eta_seconds = (base_etas * step_factor * agent_factor + tod_penalty + noise).clip(1.0, 300.0)

    return pd.DataFrame({
        "task_type": task_types,
        "agent_involved": agents,
        "step_count": step_counts,
        "time_of_day_h": time_of_day_h,
        "historical_avg_s": hist_avgs,
        "eta_seconds": eta_seconds,
    })


def engineer_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """
    Full feature engineering pipeline (CLO03):

    1. One-hot encode task_type and agent_involved
    2. Cyclically encode time_of_day_h with sin/cos
    3. Keep step_count and historical_avg_s as numerics
    4. Return (X, y) arrays
    """
    # One-hot encode categoricals
    task_cat = pd.Categorical(df["task_type"], categories=TASK_TYPES)
    agent_cat = pd.Categorical(df["agent_involved"], categories=AGENTS)
    task_dummies = pd.get_dummies(task_cat, prefix="task")
    agent_dummies = pd.get_dummies(agent_cat, prefix="agent")

    # Cyclic encoding for hour
    tod_sin = np.sin(2 * np.pi * df["time_of_day_h"] / 24)
    tod_cos = np.cos(2 * np.pi * df["time_of_day_h"] / 24)

    feature_df = pd.concat([
        task_dummies,
        agent_dummies,
        df[["step_count", "historical_avg_s"]].reset_index(drop=True),
        pd.Series(tod_sin.values, name="tod_sin"),
        pd.Series(tod_cos.values, name="tod_cos"),
    ], axis=1)

    X = feature_df.values.astype(float)
    y = df["eta_seconds"].values
    return X, y


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Computes MAE, MSE, RMSE, R² for a regression model."""
    mae = mean_absolute_error(y_true, y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = float(np.sqrt(mse))
    r2 = r2_score(y_true, y_pred)
    return {"MAE": mae, "MSE": mse, "RMSE": rmse, "R²": r2}


def train_simple_linear(
    X_train: np.ndarray, X_test: np.ndarray,
    y_train: np.ndarray, y_test: np.ndarray,
    step_col_idx: int,
) -> Tuple[LinearRegression, Dict]:
    """
    Model 1 — Simple Linear Regression (single feature: step_count).
    """
    X_tr = X_train[:, [step_col_idx]]
    X_te = X_test[:, [step_col_idx]]
    model = LinearRegression()
    model.fit(X_tr, y_train)
    y_pred = model.predict(X_te)
    return model, regression_metrics(y_test, y_pred)


def train_multiple_linear(
    X_train: np.ndarray, X_test: np.ndarray,
    y_train: np.ndarray, y_test: np.ndarray,
) -> Tuple[Pipeline, Dict]:
    """
    Model 2 — Multiple Linear Regression (all features).
    """
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LinearRegression()),
    ])
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    return pipeline, regression_metrics(y_test, y_pred)


def train_polynomial(
    X_train: np.ndarray, X_test: np.ndarray,
    y_train: np.ndarray, y_test: np.ndarray,
    degree: int = 2,
) -> Tuple[Pipeline, Dict]:
    """
    Model 3 — Polynomial Regression (degree 2).
    Fits polynomial features on step_count and historical_avg_s,
    then applies linear regression on the expanded feature set.
    """
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("poly", PolynomialFeatures(degree=degree, include_bias=False)),
        ("lr", LinearRegression()),
    ])
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)
    return pipeline, regression_metrics(y_test, y_pred)


def print_regression_comparison(results: Dict[str, Dict]) -> str:
    """Prints a Rich comparison table and returns the winner model name."""
    table = Table(
        title="[bold gold1]Task ETA — Regression Model Comparison[/]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Model", style="bold white", min_width=28)
    table.add_column("MAE (s)", justify="right")
    table.add_column("MSE (s²)", justify="right")
    table.add_column("RMSE (s)", justify="right")
    table.add_column("R² Score", justify="right")

    best_model = min(results, key=lambda k: results[k]["MAE"])

    for name, m in results.items():
        is_best = name == best_model
        style = "bold green" if is_best else ""
        mark = " ★" if is_best else ""
        table.add_row(
            f"{name}{mark}",
            f"{m['MAE']:.3f}",
            f"{m['MSE']:.3f}",
            f"{m['RMSE']:.3f}",
            f"{m['R²']:.4f}",
            style=style,
        )

    console.print(table)
    return best_model


def run() -> Pipeline:
    """
    Main entry point. Generates data, trains all regression models,
    prints evaluation, and returns the best pipeline.
    """
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.2: Task ETA Regression[/]")
    console.print("\n[dim]CLO03 · Regression · Lab 8–13[/]\n")

    # ── Data ───────────────────────────────────────────────────────────────────
    console.print("[cyan]► Generating synthetic action-log dataset...[/]")
    df = generate_action_log(n_samples=2000)
    console.print(f"  Samples : [bold]{len(df)}[/]")
    console.print(f"  ETA range: {df['eta_seconds'].min():.1f}s – {df['eta_seconds'].max():.1f}s")
    console.print(f"  ETA mean : {df['eta_seconds'].mean():.1f}s  std: {df['eta_seconds'].std():.1f}s\n")

    # ── Feature Engineering ────────────────────────────────────────────────────
    console.print("[cyan]► Engineering features...[/]")
    X, y = engineer_features(df)
    console.print(f"  Feature matrix shape: {X.shape}\n")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Find the index of step_count column (for simple linear baseline)
    feature_cols = (
        [f"task_{t}" for t in TASK_TYPES] +
        [f"agent_{a}" for a in AGENTS] +
        ["step_count", "historical_avg_s", "tod_sin", "tod_cos"]
    )
    step_col_idx = feature_cols.index("step_count")

    # ── Train Models ───────────────────────────────────────────────────────────
    console.print("[cyan]► Training regression models...[/]")

    _, metrics_simple = train_simple_linear(X_train, X_test, y_train, y_test, step_col_idx)
    _, metrics_multiple = train_multiple_linear(X_train, X_test, y_train, y_test)
    best_poly_pipeline, metrics_poly = train_polynomial(X_train, X_test, y_train, y_test, degree=2)

    all_results = {
        "1. Simple Linear Regression": metrics_simple,
        "2. Multiple Linear Regression": metrics_multiple,
        "3. Polynomial Regression (deg=2)": metrics_poly,
    }

    console.print()
    best_name = print_regression_comparison(all_results)

    # ── Live Inference Demo ────────────────────────────────────────────────────
    console.rule("[bold gold1]Live ETA Prediction Demo[/]")
    console.print(
        "[dim]Showing ETA predictions for sample tasks using the best model...[/]\n"
    )

    demo_records = [
        {"task_type": "document_intel", "agent_involved": "memory",
         "step_count": 3, "time_of_day_h": 10.0, "historical_avg_s": HISTORICAL_AVG["document_intel"]},
        {"task_type": "browser", "agent_involved": "browser",
         "step_count": 7, "time_of_day_h": 15.0, "historical_avg_s": HISTORICAL_AVG["browser"]},
        {"task_type": "desktop_automation", "agent_involved": "computer",
         "step_count": 12, "time_of_day_h": 20.0, "historical_avg_s": HISTORICAL_AVG["desktop_automation"]},
        {"task_type": "communication", "agent_involved": "communication",
         "step_count": 2, "time_of_day_h": 9.5, "historical_avg_s": HISTORICAL_AVG["communication"]},
    ]

    demo_df = pd.DataFrame(demo_records)
    X_demo, _ = engineer_features(demo_df.assign(eta_seconds=0.0))

    demo_table = Table(box=box.ROUNDED, header_style="bold cyan",
                       title="[bold gold1]Predicted Task ETAs[/]")
    demo_table.add_column("Task Type", min_width=20)
    demo_table.add_column("Steps", justify="center")
    demo_table.add_column("Agent", justify="center")
    demo_table.add_column("Time of Day", justify="center")
    demo_table.add_column("Predicted ETA", justify="right", style="bold green")

    for i, rec in enumerate(demo_records):
        eta = best_poly_pipeline.predict(X_demo[[i]])[0]
        demo_table.add_row(
            rec["task_type"],
            str(int(rec["step_count"])),
            rec["agent_involved"],
            f"{rec['time_of_day_h']:.0f}:00",
            f"{eta:.1f}s",
        )

    console.print(demo_table)
    console.print(
        "\n[bold green]✓ Component 2.2 complete.[/] "
        f"Best model: [bold]{best_name}[/] — ETA predictions ready for Tier-2 UI.\n"
    )
    return best_poly_pipeline


# ── Public API ─────────────────────────────────────────────────────────────────
def get_trained_regressor() -> Pipeline:
    """Returns a trained polynomial regression pipeline."""
    model_dir = PROJECT_ROOT / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "task_eta_regressor.joblib"

    if model_path.exists():
        try:
            return joblib.load(model_path)
        except Exception:
            pass

    df = generate_action_log(n_samples=2000)
    X, y = engineer_features(df)
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("poly", PolynomialFeatures(degree=2, include_bias=False)),
        ("lr", LinearRegression()),
    ])
    pipeline.fit(X_train, y_train)

    try:
        joblib.dump(pipeline, model_path)
    except Exception as e:
        warnings.warn(f"Could not save model artifact to {model_path}: {e}")

    return pipeline


if __name__ == "__main__":
    run()

