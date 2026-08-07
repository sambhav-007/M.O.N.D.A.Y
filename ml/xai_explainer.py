"""
M.O.N.D.A.Y. — Component 2.6 (Bonus): Explainable AI (XAI) Layer
==================================================================
Course Mapping : CLO02/CLO06 — Beyond-Syllabus credit (XAI)
Technique      : Exact Shapley values, computed in closed form

Purpose
-------
Attribute every prediction to the features that caused it, for:
  1. The Intent Classifier (Component 2.1) — which words pushed the model
     toward a given intent?
  2. The ETA Regression model (Component 2.2) — which features (step count,
     agent, task type, time of day) drive the predicted time?

This serves two goals at once:
  • Beyond-syllabus academic credit (CLO02/CLO06)
  • The PRD's transparency requirement (§9): the Tier-2 confirmation prompt can
    say *why* it estimated 14s, not merely that it did.

Why this does not import the `shap` library
--------------------------------------------
`shap` cannot be installed on the target machine. It hard-imports `numba` at
package load (`shap/utils/_clustering.py`), and:

  • numba 0.66 — the only release supporting numpy>=2.3.5, which mlxtend
    (Component 2.4) requires — is blocked by Windows Smart App Control:
    "DLL load failed while importing _typeconv: An Application Control policy
    has blocked this file."
  • numba 0.61.2 loads under Smart App Control but pins numpy<2.2, which breaks
    mlxtend and therefore Component 2.4.

No numba version satisfies both constraints, and disabling Smart App Control is
a one-way system security change. Rather than drop the component, we compute the
Shapley values directly — which for these two models is exact, not an
approximation.

The mathematics
---------------
Both explained models are **linear**: Component 2.1 is Logistic Regression over
TF-IDF features, Component 2.2 is Linear Regression over engineered features.

For a linear model f(x) = b + Σ_j β_j x_j, the Shapley value of feature j under
interventional (marginal) perturbation against a background distribution D has
the closed form

    φ_j(x) = β_j · ( x_j − E_D[x_j] )

with base value

    φ_0 = E_D[ f(x) ] = b + Σ_j β_j E_D[x_j]

This is not an approximation of the sampling-based estimate — it is the exact
Shapley value, and it is precisely what `shap.LinearExplainer` computes when
`feature_perturbation="interventional"`. Because the model is additive, the
feature-independence assumption that makes the closed form valid is the same
assumption `LinearExplainer` makes.

Equivalence to `shap.LinearExplainer` is not merely asserted. The functions below
were run against the reference implementation (shap 0.52.0, in an isolated venv,
since shap cannot be installed here) on both a regression and a 6-class logistic
model. The Shapley values agreed to **0.000e+00 — bit-for-bit identical** — once
both sides were given the same background distribution. See
`reports/2_6_shap_equivalence.md` for the full procedure and output.

Every explanation produced here is checked against the **local accuracy**
(efficiency) axiom before being returned:

    Σ_j φ_j(x) + φ_0  ==  f(x)

If that identity does not hold, the explanation is wrong and we raise rather
than report a plausible-looking number.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
from rich.console import Console
from rich.table import Table
from rich import box
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")
console = Console()

REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

# Tolerance for the local-accuracy assertion. Float64 linear algebra over a few
# thousand TF-IDF features accumulates a little error; 1e-8 is far tighter than
# any figure we report to 4 decimal places.
LOCAL_ACCURACY_TOL = 1e-8


# ── Core: exact Shapley values for linear models ─────────────────────────────
def exact_linear_shap_values(
    coef: np.ndarray,
    X: np.ndarray,
    background_mean: np.ndarray,
) -> np.ndarray:
    """
    Exact Shapley values for a linear model, in closed form.

        φ_j(x) = β_j · (x_j − E[x_j])

    Parameters
    ----------
    coef            : (n_features,) for regression / binary,
                      (n_classes, n_features) for multiclass
    X               : (n_samples, n_features) dense feature matrix to explain
    background_mean : (n_features,) feature means of the background dataset

    Returns
    -------
    (n_samples, n_features)              if coef is 1-D
    (n_samples, n_features, n_classes)   if coef is 2-D
    """
    coef = np.asarray(coef, dtype=float)
    X = np.asarray(X, dtype=float)
    background_mean = np.asarray(background_mean, dtype=float).ravel()

    if X.ndim != 2:
        raise ValueError(f"X must be 2-D, got shape {X.shape}")
    if background_mean.shape[0] != X.shape[1]:
        raise ValueError(
            f"background_mean has {background_mean.shape[0]} features, "
            f"X has {X.shape[1]}"
        )

    centred = X - background_mean

    if coef.ndim == 1:
        if coef.shape[0] != X.shape[1]:
            raise ValueError(f"coef has {coef.shape[0]} features, X has {X.shape[1]}")
        return centred * coef

    if coef.shape[1] != X.shape[1]:
        raise ValueError(f"coef has {coef.shape[1]} features, X has {X.shape[1]}")
    # (n_samples, n_features, 1) * (1, n_features, n_classes)
    return centred[:, :, None] * coef.T[None, :, :]


def linear_shap_base_value(
    intercept: np.ndarray | float,
    coef: np.ndarray,
    background_mean: np.ndarray,
) -> np.ndarray:
    """
    Base value φ_0 = E[f(x)] = b + Σ_j β_j E[x_j].

    Returns a scalar array for 1-D coef, or (n_classes,) for 2-D coef.
    """
    coef = np.asarray(coef, dtype=float)
    background_mean = np.asarray(background_mean, dtype=float).ravel()
    return np.asarray(intercept, dtype=float) + coef @ background_mean


def check_local_accuracy(
    shap_values: np.ndarray,
    base_value: np.ndarray,
    model_output: np.ndarray,
    label: str = "model",
) -> float:
    """
    Enforces the Shapley efficiency axiom:  Σ_j φ_j(x) + φ_0 == f(x).

    Returns the maximum absolute deviation. Raises if it exceeds tolerance,
    because an explanation that violates local accuracy is simply incorrect and
    must never be presented as evidence.
    """
    if shap_values.ndim == 3:
        # (n_samples, n_features, n_classes) -> sum over features
        reconstructed = shap_values.sum(axis=1) + np.asarray(base_value).ravel()[None, :]
    else:
        reconstructed = shap_values.sum(axis=1) + float(np.asarray(base_value))

    deviation = float(np.max(np.abs(reconstructed - np.asarray(model_output))))
    if not np.isfinite(deviation) or deviation > LOCAL_ACCURACY_TOL:
        raise AssertionError(
            f"Local accuracy violated for {label}: max |Σφ + φ₀ − f(x)| = "
            f"{deviation:.3e} exceeds tolerance {LOCAL_ACCURACY_TOL:.0e}. "
            "The Shapley values do not reconstruct the model output."
        )
    return deviation


# ── Utility: Top N SHAP Features ─────────────────────────────────────────────
def top_shap_features(
    shap_values: np.ndarray,
    feature_names: List[str],
    class_idx: Optional[int] = None,
    top_n: int = 10,
) -> List[tuple]:
    """
    Returns top-N features sorted by mean |SHAP value|.

    Parameters
    ----------
    shap_values   : (n_samples, n_features) or (n_samples, n_features, n_classes)
    feature_names : list of feature names
    class_idx     : if multiclass, which class to inspect
    top_n         : how many top features to return
    """
    if shap_values.ndim == 3 and class_idx is not None:
        sv = shap_values[:, :, class_idx]
    elif shap_values.ndim == 3:
        sv = shap_values.mean(axis=2)
    else:
        sv = shap_values

    mean_abs = np.abs(sv).mean(axis=0)
    top_idx = np.argsort(mean_abs)[::-1][:top_n]
    return [(feature_names[i], float(mean_abs[i])) for i in top_idx]


def print_shap_table(
    features: List[tuple],
    title: str,
    value_label: str = "Mean |SHAP|",
) -> None:
    """Prints a Rich table of SHAP feature importances."""
    table = Table(
        title=f"[bold gold1]{title}[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Rank", justify="center", width=6)
    table.add_column("Feature", min_width=32)
    table.add_column(value_label, justify="right")
    table.add_column("Importance Bar", min_width=20)

    max_val = features[0][1] if features else 1.0
    if max_val == 0:
        max_val = 1.0
    for i, (feat, val) in enumerate(features, 1):
        bar_len = int((val / max_val) * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        style = "bold green" if i <= 3 else ""
        table.add_row(str(i), feat[:40], f"{val:.4f}", f"[green]{bar}[/]", style=style)
    console.print(table)


# ── Lazily-built, cached models ───────────────────────────────────────────────
_INTENT_CACHE: Optional[Dict[str, Any]] = None
_ETA_CACHE: Optional[Dict[str, Any]] = None


def _build_intent_explainer(samples_per_class: int = 300) -> Dict[str, Any]:
    """
    Trains the 2.1 Logistic Regression pipeline and prepares everything needed
    to explain it: coefficients, TF-IDF vocabulary, and background means.
    """
    global _INTENT_CACHE
    if _INTENT_CACHE is not None:
        return _INTENT_CACHE

    from ml.intent_classifier import build_synthetic_dataset, build_pipelines

    df = build_synthetic_dataset(samples_per_class=samples_per_class)
    X = df["command"].tolist()
    y = df["intent"].tolist()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pipeline = build_pipelines()["Logistic Regression"]
    pipeline.fit(X_train, y_train)

    vectoriser = pipeline.named_steps["tfidf"]
    clf = pipeline.named_steps["clf"]

    X_train_tfidf = vectoriser.transform(X_train)
    # Background expectation E[x_j] over the training distribution.
    background_mean = np.asarray(X_train_tfidf.mean(axis=0)).ravel()

    _INTENT_CACHE = {
        "pipeline": pipeline,
        "vectoriser": vectoriser,
        "clf": clf,
        "feature_names": vectoriser.get_feature_names_out().tolist(),
        "background_mean": background_mean,
        "classes": list(clf.classes_),
        "X_test": X_test,
        "y_test": y_test,
    }
    return _INTENT_CACHE


def _build_eta_explainer(n_samples: int = 1000) -> Dict[str, Any]:
    """Trains the 2.2 Linear Regression pipeline and prepares its explainer."""
    global _ETA_CACHE
    if _ETA_CACHE is not None:
        return _ETA_CACHE

    from ml.task_eta_regression import (
        generate_action_log,
        engineer_features,
        TASK_TYPES,
        AGENTS,
    )
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    df = generate_action_log(n_samples=n_samples)
    X, y = engineer_features(df)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    scaler = StandardScaler().fit(X_train)
    X_train_scaled = scaler.transform(X_train)
    lr = LinearRegression().fit(X_train_scaled, y_train)

    feature_names = (
        [f"task_{t}" for t in TASK_TYPES]
        + [f"agent_{a}" for a in AGENTS]
        + ["step_count", "historical_avg_s", "tod_sin", "tod_cos"]
    )

    _ETA_CACHE = {
        "scaler": scaler,
        "model": lr,
        "feature_names": feature_names,
        "background_mean": X_train_scaled.mean(axis=0),
        "X_test_scaled": scaler.transform(X_test),
        "y_test": y_test,
    }
    return _ETA_CACHE


# ── XAI for Intent Classifier (2.1) ──────────────────────────────────────────
def explain_classifier(n_explain: int = 100, write_evidence: bool = True) -> pd.DataFrame:
    """
    Computes exact Shapley values for the Component 2.1 intent classifier and
    reports the words that most drive each intent.

    Returns a tidy DataFrame of (intent, rank, feature, mean_abs_shap).
    """
    console.rule("[bold gold1]XAI — Intent Classifier (Component 2.1)[/]")

    ctx = _build_intent_explainer()
    vectoriser, clf = ctx["vectoriser"], ctx["clf"]
    feature_names = ctx["feature_names"]
    background_mean = ctx["background_mean"]
    classes = ctx["classes"]

    console.print("\n[cyan]► Explaining Logistic Regression over TF-IDF features...[/]")
    X_explain = vectoriser.transform(ctx["X_test"][:n_explain]).toarray()
    console.print(f"  TF-IDF features : {len(feature_names)}")
    console.print(f"  Intent classes  : {len(classes)}")
    console.print(f"  Explaining {X_explain.shape[0]} test samples...\n")

    shap_values = exact_linear_shap_values(clf.coef_, X_explain, background_mean)
    base_value = linear_shap_base_value(clf.intercept_, clf.coef_, background_mean)

    # The classifier's raw margin is what the additive attribution reconstructs.
    deviation = check_local_accuracy(
        shap_values, base_value, clf.decision_function(X_explain), "intent classifier"
    )
    console.print(
        f"  [green]✓ Local accuracy verified[/] — max |Σφ + φ₀ − f(x)| = "
        f"[bold]{deviation:.2e}[/]\n"
    )

    rows: List[Dict[str, Any]] = []
    for class_idx, class_name in enumerate(classes):
        top_feats = top_shap_features(
            shap_values, feature_names, class_idx=class_idx, top_n=8
        )
        print_shap_table(top_feats, f"Top Words for Intent: {class_name}", "Mean |SHAP|")
        console.print()
        for rank, (feat, val) in enumerate(top_feats, 1):
            rows.append(
                {
                    "intent": class_name,
                    "rank": rank,
                    "feature": feat,
                    "mean_abs_shap": round(val, 6),
                }
            )

    result = pd.DataFrame(rows)
    if write_evidence:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORTS_DIR / "2_6_xai_intent_top_features.csv"
        result.to_csv(out, index=False)
        console.print(f"[dim]  evidence → {out.relative_to(PROJECT_ROOT)}[/]")

    return result


# ── XAI for ETA Regressor (2.2) ──────────────────────────────────────────────
def explain_regressor(n_explain: int = 200, write_evidence: bool = True) -> pd.DataFrame:
    """
    Computes exact Shapley values for the Component 2.2 ETA regressor.

    Returns a DataFrame of (rank, feature, mean_abs_shap, mean_signed_shap).
    """
    console.rule("[bold gold1]XAI — ETA Regression Model (Component 2.2)[/]")

    ctx = _build_eta_explainer()
    lr = ctx["model"]
    feature_names = ctx["feature_names"]
    background_mean = ctx["background_mean"]

    X_explain = ctx["X_test_scaled"][:n_explain]
    console.print(f"\n[cyan]► Explaining Multiple Linear Regression...[/]")
    console.print(f"  Feature count : {X_explain.shape[1]}")
    console.print(f"  Explaining {X_explain.shape[0]} test samples...\n")

    shap_values = exact_linear_shap_values(lr.coef_, X_explain, background_mean)
    base_value = linear_shap_base_value(lr.intercept_, lr.coef_, background_mean)

    deviation = check_local_accuracy(
        shap_values, base_value, lr.predict(X_explain), "ETA regressor"
    )
    console.print(
        f"  [green]✓ Local accuracy verified[/] — max |Σφ + φ₀ − f(x)| = "
        f"[bold]{deviation:.2e}[/]"
    )
    console.print(f"  Base value E[f(x)] = [bold]{float(base_value):.2f}s[/]\n")

    top_feats = top_shap_features(shap_values, feature_names, top_n=10)
    print_shap_table(top_feats, "Top Features Driving Task ETA Predictions")

    mean_abs = np.abs(shap_values).mean(axis=0)
    mean_signed = shap_values.mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    result = pd.DataFrame(
        {
            "rank": np.arange(1, len(order) + 1),
            "feature": [feature_names[i] for i in order],
            "mean_abs_shap": np.round(mean_abs[order], 6),
            # Direction of effect. This is the coefficient, NOT mean signed SHAP:
            # mean signed SHAP only records whether the explained samples happened
            # to sit above or below the background mean, so its sign is close to
            # noise and can invert a feature whose true effect is unambiguous.
            # (step_count has coefficient +63.2 — more steps means a longer ETA —
            # yet its mean signed SHAP is negative purely because this test subset
            # averages 0.08 SD below the training mean.)
            "coefficient": np.round(np.asarray(lr.coef_, dtype=float)[order], 6),
            "mean_signed_shap": np.round(mean_signed[order], 6),
        }
    )

    if write_evidence:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORTS_DIR / "2_6_xai_eta_feature_importance.csv"
        result.to_csv(out, index=False)
        console.print(f"\n[dim]  evidence → {out.relative_to(PROJECT_ROOT)}[/]")

    console.print("\n[bold cyan]Insight Summary:[/]")
    console.print(
        "  Features with the largest mean |SHAP| are the primary drivers of the\n"
        "  ETA prediction. This is what lets the Tier-2 confirmation prompt say not\n"
        "  just [italic]'Est. 14s'[/] but [italic]'primarily because this task has 8 steps\n"
        "  and runs on the Browser agent at peak hours.'[/]\n"
    )
    return result


# ── Single-prediction explanations (used by the notebook and the API) ────────
def explain_intent_prediction(command: str, top_n: int = 8) -> Dict[str, Any]:
    """
    Explains one intent prediction with exact Shapley values.

    Returns the predicted intent, the base value, and the signed contribution of
    each influential token — signed, because "which words pushed *towards* this
    intent" is the question a user actually asks.
    """
    ctx = _build_intent_explainer()
    vectoriser, clf = ctx["vectoriser"], ctx["clf"]
    feature_names = ctx["feature_names"]
    classes = ctx["classes"]

    x = vectoriser.transform([command]).toarray()
    predicted = str(clf.predict(x)[0])
    class_idx = classes.index(predicted)

    shap_values = exact_linear_shap_values(clf.coef_, x, ctx["background_mean"])
    base_value = linear_shap_base_value(clf.intercept_, clf.coef_, ctx["background_mean"])
    check_local_accuracy(
        shap_values, base_value, clf.decision_function(x), "single intent prediction"
    )

    phi = shap_values[0, :, class_idx]

    # Restrict the reported attributions to tokens that actually occur in the
    # command. Absent tokens do carry a non-zero Shapley value — φ_j = β_j(0 −
    # E[x_j]) — and that contribution is real and is included in the local
    # accuracy check above. But "the word 'you', which you did not say, pushed
    # this towards chitchat" is not an explanation a user can act on, and for an
    # empty command it would rank the entire vocabulary. The global analysis in
    # explain_classifier() keeps the full vector.
    present = np.flatnonzero(np.asarray(x[0]) != 0)
    ranked = present[np.argsort(np.abs(phi[present]))[::-1]][:top_n]

    contributions = [
        {"feature": feature_names[i], "shap_value": round(float(phi[i]), 6)}
        for i in ranked
    ]
    return {
        "xai_method": "Exact Shapley values (closed form, linear model)",
        "command": command,
        "predicted_intent": predicted,
        "base_value": round(float(np.asarray(base_value).ravel()[class_idx]), 6),
        "contributions": contributions,
        "key_influencing_features": [c["feature"] for c in contributions],
        "explanation": (
            f"Predicted '{predicted}'"
            + (
                f" driven by: {', '.join(c['feature'] for c in contributions[:3])}"
                if contributions
                else " — no known vocabulary in this command"
            )
        ),
    }


def explain_eta_prediction(
    task_type: str = "web_research",
    agent: str = "BrowserAgent",
    step_count: int = 8,
    historical_avg_s: float = 12.0,
    time_of_day_h: int = 14,
    top_n: int = 8,
) -> Dict[str, Any]:
    """
    Explains one ETA prediction with exact Shapley values, in the form the
    Tier-2 confirmation prompt needs.
    """
    from ml.task_eta_regression import engineer_features

    ctx = _build_eta_explainer()
    scaler, lr = ctx["scaler"], ctx["model"]
    feature_names = ctx["feature_names"]

    row = pd.DataFrame(
        [
            {
                "task_type": task_type,
                "agent_involved": agent,
                "step_count": step_count,
                "historical_avg_s": historical_avg_s,
                "time_of_day_h": time_of_day_h,
                "eta_seconds": 0.0,  # unused; engineer_features returns it as y
            }
        ]
    )
    X, _ = engineer_features(row)
    x = scaler.transform(X)

    shap_values = exact_linear_shap_values(lr.coef_, x, ctx["background_mean"])
    base_value = linear_shap_base_value(lr.intercept_, lr.coef_, ctx["background_mean"])
    check_local_accuracy(shap_values, base_value, lr.predict(x), "single ETA prediction")

    phi = shap_values[0]
    ranked = np.argsort(np.abs(phi))[::-1][:top_n]
    contributions = [
        {"feature": feature_names[i], "shap_value": round(float(phi[i]), 4)}
        for i in ranked
        if phi[i] != 0
    ]
    predicted = float(lr.predict(x)[0])

    return {
        "xai_method": "Exact Shapley values (closed form, linear model)",
        "predicted_eta_seconds": round(predicted, 2),
        "base_value": round(float(base_value), 4),
        "contributions": contributions,
        "explanation": (
            f"Est. {predicted:.0f}s — primarily because "
            + ", ".join(
                f"{c['feature']} ({c['shap_value']:+.1f}s)" for c in contributions[:3]
            )
        ),
    }


def explain_command_intent(command: str, pipeline=None) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper used by the API (`/ml/xai/explain`).

    Previously this split the string on whitespace and returned arbitrary words
    while claiming to be SHAP output. It now returns real Shapley attributions.
    """
    try:
        result = explain_intent_prediction(command)
    except Exception as exc:  # noqa: BLE001 - surface the failure, never fake it
        return {
            "xai_method": "unavailable",
            "command": command,
            "key_influencing_features": [],
            "error": f"{type(exc).__name__}: {exc}",
            "explanation": "XAI explanation could not be computed for this command.",
        }
    result["xai_model"] = result["xai_method"]  # legacy key
    return result


# ── Evidence figures ─────────────────────────────────────────────────────────
def _write_figures(intent_df: pd.DataFrame, eta_df: pd.DataFrame) -> None:
    """Writes the CLO evidence figures for Component 2.6."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Figure 1: top words per intent ──
    intents = list(dict.fromkeys(intent_df["intent"].tolist()))
    n = len(intents)
    ncols = 3
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 3.4 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for ax, intent in zip(axes, intents):
        sub = intent_df[intent_df["intent"] == intent].head(6).iloc[::-1]
        ax.barh(sub["feature"], sub["mean_abs_shap"], color="#4C72B0")
        ax.set_title(f"{intent}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Mean |SHAP|", fontsize=9)
        ax.tick_params(labelsize=8)
    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle(
        "Component 2.6 — Exact Shapley Attribution per Intent (Component 2.1)",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out1 = FIGURES_DIR / "2_6_xai_intent_top_features.png"
    fig.savefig(out1, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ── Figure 2: ETA global feature importance ──
    top = eta_df.head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    # Colour by the sign of the coefficient — the model's actual directional
    # effect — not by mean signed SHAP, which reflects only where the explained
    # sample happened to fall relative to the background.
    colours = ["#C44E52" if c < 0 else "#55A868" for c in top["coefficient"]]
    ax.barh(top["feature"], top["mean_abs_shap"], color=colours)
    ax.set_xlabel("Mean |SHAP| (seconds)", fontsize=10)
    ax.set_title(
        "Component 2.6 — Feature Attribution for Task ETA (Component 2.2)",
        fontsize=12,
        fontweight="bold",
    )
    ax.tick_params(labelsize=9)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color="#55A868"),
        plt.Rectangle((0, 0), 1, 1, color="#C44E52"),
    ]
    ax.legend(
        handles,
        ["higher value → longer ETA", "higher value → shorter ETA"],
        fontsize=9,
        loc="lower right",
    )
    fig.tight_layout()
    out2 = FIGURES_DIR / "2_6_xai_eta_feature_importance.png"
    fig.savefig(out2, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ── Figure 3: single-prediction waterfall ──
    single = explain_eta_prediction()
    contribs = single["contributions"][:8][::-1]
    labels = [c["feature"] for c in contribs]
    values = [c["shap_value"] for c in contribs]

    fig, ax = plt.subplots(figsize=(9, 5))
    colours = ["#C44E52" if v < 0 else "#55A868" for v in values]
    ax.barh(labels, values, color=colours)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("SHAP contribution to predicted ETA (seconds)", fontsize=10)
    ax.set_title(
        f"Single Prediction — base {single['base_value']:.1f}s "
        f"→ predicted {single['predicted_eta_seconds']:.1f}s",
        fontsize=12,
        fontweight="bold",
    )
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    out3 = FIGURES_DIR / "2_6_xai_single_prediction.png"
    fig.savefig(out3, dpi=300, bbox_inches="tight")
    plt.close(fig)

    for out in (out1, out2, out3):
        console.print(f"[dim]  figure → {out.relative_to(PROJECT_ROOT)}[/]")


# ── Entry point ──────────────────────────────────────────────────────────────
def run() -> None:
    """Main entry point — runs both explanations and writes CLO evidence."""
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.6 (Bonus): XAI Layer[/]")
    console.print("\n[dim]CLO02/CLO06 · Explainable AI · Exact Shapley values[/]\n")

    intent_df = explain_classifier()
    console.print()
    eta_df = explain_regressor()

    console.print("\n[cyan]► Writing evidence figures...[/]")
    _write_figures(intent_df, eta_df)

    console.print(
        "\n[bold green]✓ Component 2.6 (Bonus XAI) complete.[/] "
        "Exact Shapley attributions for both the Intent Classifier and the ETA "
        "Regressor, verified against the local-accuracy axiom.\n"
    )


if __name__ == "__main__":
    run()
