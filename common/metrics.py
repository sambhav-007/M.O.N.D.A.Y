"""Standard metric reporters so every notebook reports the CLO-required numbers
in the same format. Classification (2.1) -> CLO04, regression (2.2) -> CLO03.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)


def classification_metrics(y_true, y_pred, labels=None) -> dict:
    """CLO04 evidence: accuracy + macro precision/recall/F1 + confusion matrix."""
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_macro": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels),
        "report": classification_report(y_true, y_pred, zero_division=0),
    }


def regression_metrics(y_true, y_pred) -> dict:
    """CLO03 evidence: MAE, MSE, RMSE, R²."""
    mse = mean_squared_error(y_true, y_pred)
    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "MSE": mse,
        "RMSE": float(np.sqrt(mse)),
        "R2": r2_score(y_true, y_pred),
    }
