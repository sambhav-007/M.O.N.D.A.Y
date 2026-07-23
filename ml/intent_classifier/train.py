"""2.1 Intent Classifier — train and compare five models (CLO04).

Runs the formal comparison the rubric asks for: TF-IDF + {Logistic Regression,
KNN, Decision Tree, Random Forest, SVM}, evaluated with accuracy / precision /
recall / F1 and a confusion matrix. The best model (by macro-F1) is refit on the
full data and saved as a single sklearn Pipeline so production code can call it
on raw command text.

Run from the repo root:
    python -m ml.intent_classifier.train
"""

from __future__ import annotations

import time
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")  # headless: write PNGs without a display
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

# classifiers under comparison
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC

from common.io import FIGURES, REPORTS, load_csv, _ensure
from common.metrics import classification_metrics
from common.preprocessing import build_vectorizer
from datagen.config import INTENTS, RANDOM_SEED

MODEL_PATH = Path(__file__).with_name("model.joblib")


def candidate_models() -> dict:
    """The five models to compare (matches Labs 14-20)."""
    return {
        "LogisticRegression": LogisticRegression(max_iter=1000, C=4.0),
        "KNN": KNeighborsClassifier(n_neighbors=7, weights="distance"),
        "DecisionTree": DecisionTreeClassifier(random_state=RANDOM_SEED),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, random_state=RANDOM_SEED, n_jobs=-1
        ),
        "SVM": SVC(kernel="linear", C=1.0, probability=True, random_state=RANDOM_SEED),
    }


def _pipeline(model) -> Pipeline:
    # Each model gets its own TF-IDF so the comparison is fully independent.
    return Pipeline([("tfidf", build_vectorizer()), ("clf", model)])


def run() -> pd.DataFrame:
    df = load_csv("commands.csv")
    X, y = df["text"].values, df["intent"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )
    print(f"train={len(X_train)}  test={len(X_test)}  classes={sorted(set(y))}")

    rows, detail = [], {}
    for name, model in candidate_models().items():
        pipe = _pipeline(model)
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        fit_s = time.perf_counter() - t0
        y_pred = pipe.predict(X_test)
        m = classification_metrics(y_test, y_pred, labels=INTENTS)
        detail[name] = (pipe, m, y_pred)
        rows.append({
            "model": name,
            "accuracy": round(m["accuracy"], 4),
            "precision_macro": round(m["precision_macro"], 4),
            "recall_macro": round(m["recall_macro"], 4),
            "f1_macro": round(m["f1_macro"], 4),
            "fit_seconds": round(fit_s, 3),
        })

    table = (
        pd.DataFrame(rows)
        .sort_values("f1_macro", ascending=False)
        .reset_index(drop=True)
    )
    print("\n=== Model comparison (sorted by macro-F1) ===")
    print(table.to_string(index=False))

    best_name = table.iloc[0]["model"]
    best_pipe, best_metrics, best_pred = detail[best_name]
    print(f"\nBest model: {best_name} (macro-F1={table.iloc[0]['f1_macro']})")
    print("\nPer-class report for best model:\n")
    print(best_metrics["report"])

    _write_evidence(table, best_name, best_metrics, y_test, best_pred)
    _save_best(best_name, X, y)
    return table


def _md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavored markdown table (no extra deps)."""
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def _write_evidence(table, best_name, best_metrics, y_test, best_pred) -> None:
    _ensure(REPORTS)
    _ensure(FIGURES)

    # 1) comparison table (CSV) for the report appendix
    table.to_csv(REPORTS / "intent_classifier_comparison.csv", index=False)

    # 2) confusion matrix figure for the best model
    fig, ax = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay.from_predictions(
        y_test, best_pred, labels=INTENTS, xticks_rotation=45,
        cmap="Blues", ax=ax, colorbar=False,
    )
    ax.set_title(f"Intent Classifier — Confusion Matrix ({best_name})")
    fig.tight_layout()
    fig_path = FIGURES / "intent_classifier_confusion_matrix.png"
    fig.savefig(fig_path, dpi=130)
    plt.close(fig)

    # 3) markdown summary tying it to CLO04
    md = REPORTS / "intent_classifier_report.md"
    lines = [
        "# 2.1 Intent Classifier — Results (CLO04)",
        "",
        f"Winner: **{best_name}** by macro-F1.",
        "",
        "## Model comparison",
        "",
        _md_table(table),
        "",
        "## Best model — macro metrics",
        "",
        f"- accuracy: {best_metrics['accuracy']:.4f}",
        f"- precision (macro): {best_metrics['precision_macro']:.4f}",
        f"- recall (macro): {best_metrics['recall_macro']:.4f}",
        f"- f1 (macro): {best_metrics['f1_macro']:.4f}",
        "",
        "Confusion matrix: `reports/figures/intent_classifier_confusion_matrix.png`",
        "",
        "## Per-class report",
        "",
        "```",
        best_metrics["report"].rstrip(),
        "```",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nEvidence written:\n  {REPORTS / 'intent_classifier_comparison.csv'}"
          f"\n  {fig_path}\n  {md}")


def _save_best(best_name, X, y) -> None:
    """Refit the winning model on ALL data and persist it for production use."""
    best_model = candidate_models()[best_name]
    final = _pipeline(best_model).fit(X, y)
    joblib.dump({"pipeline": final, "model_name": best_name, "labels": INTENTS},
                MODEL_PATH)
    print(f"  {MODEL_PATH}  (refit on full dataset)")


if __name__ == "__main__":
    run()
