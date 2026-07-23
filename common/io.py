"""Filesystem paths and small load/save helpers shared across components."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Project root = parent of this file's parent (common/ -> repo root).
ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
RAW = DATA / "raw"
SYNTHETIC = DATA / "synthetic"
PROCESSED = DATA / "processed"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_csv(df: pd.DataFrame, name: str, folder: Path = SYNTHETIC) -> Path:
    """Write a dataframe to ``folder/name`` (adds .csv if missing)."""
    _ensure(folder)
    if not name.endswith(".csv"):
        name += ".csv"
    out = folder / name
    df.to_csv(out, index=False)
    return out


def load_csv(name: str, folder: Path = SYNTHETIC) -> pd.DataFrame:
    if not name.endswith(".csv"):
        name += ".csv"
    return pd.read_csv(folder / name)
