"""
M.O.N.D.A.Y. — Component 2.1: Intent Classification Model
===========================================================
Course Mapping : CLO04 — Classification with metrics
Lab Reference  : Lab 14–20 (Logistic Regression, SVM, KNN, Decision Tree)
Owner          : AI/ML Specialist

Purpose
-------
Before invoking the (expensive, slower) LLM Planner, classify simple/common
commands directly into one of 7 intent categories:

    document_intel | communication | browser | desktop_automation
    memory_query   | chitchat      | unclear → LLM_fallback

Dataset
-------
Labelled commands come from `datagen/` (data/synthetic/commands.csv), which
shares filler vocabulary across intents and injects ~6% label noise so the
classes overlap the way real user commands do. Without that overlap the task
is trivially separable and every linear model scores ~100%, which makes the
model comparison below meaningless.

Pipeline
--------
raw text → cleaning/tokenisation → TF-IDF vectorisation → classifier

Models compared (formal evaluation, not just picking one):
    Logistic Regression | KNN | Decision Tree | Random Forest | SVM

Evaluation (CLO04 requirement)
-------------------------------
Confusion matrix, accuracy, precision, recall, F1 score per class.
The best model is identified and its production role is explained.

Production Role
---------------
High-confidence predictions skip the LLM call entirely (faster, cheaper).
Low-confidence predictions fall through to the Planner Agent.
"""

from __future__ import annotations

import os
import sys
import time
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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")
console = Console()

# ── Intent Classes ─────────────────────────────────────────────────────────────
INTENT_CLASSES = [
    "document_intel",
    "communication",
    "browser",
    "desktop_automation",
    "memory_query",
    "chitchat",
    "unclear",
]

# `datagen/` names the low-confidence bucket `llm_fallback`; the rest of the
# system (planner routing, predict_intent) calls it `unclear`. Normalise on load.
DATAGEN_LABEL_ALIASES = {"llm_fallback": "unclear"}

# ── Synthetic Command Dataset ──────────────────────────────────────────────────
# Fallback seeds ONLY. The real dataset comes from `datagen/` — see
# build_synthetic_dataset(). These seeds use disjoint per-intent vocabulary,
# which makes the classes trivially separable (linear models score ~100%), so
# they are not a defensible basis for the CLO04 model comparison.

COMMAND_SEEDS: Dict[str, List[str]] = {
    "document_intel": [
        "summarize the PDF I uploaded",
        "find all mentions of budget in my notes",
        "extract key points from the quarterly report",
        "generate a summary of today's lecture notes",
        "what did the professor say about deadlines",
        "compare these two documents",
        "highlight action items from meeting notes",
        "find the section about machine learning",
        "create a table of contents for my thesis",
        "translate this document to English",
        "extract figures from the research paper",
        "search my files for anything about the project deadline",
        "summarize the last five emails about the internship",
        "what are the key findings of this paper",
        "draft a summary report from these bullet points",
    ],
    "communication": [
        "send an email to my professor about the assignment",
        "draft a reply to Sambhav's message",
        "write a follow-up email to the HR team",
        "message Shivansh about the code review",
        "compose an apology email for missing the meeting",
        "reply to the job offer with my acceptance",
        "send a thank you note to Dr. Priyanka",
        "forward this email to the team",
        "schedule a meeting invitation for Friday",
        "send a Slack message to the dev channel",
        "email the client the updated proposal",
        "notify the team about the deployment",
        "write a formal email requesting an extension",
        "draft a weekly status update for the manager",
        "reply to all attendees with the meeting notes",
    ],
    "browser": [
        "search for the cheapest flight to Mumbai",
        "open YouTube and play lo-fi music",
        "go to the IRCTC website and check trains",
        "find the top 5 laptops under 60000 on Amazon",
        "browse news about AI developments",
        "look up the weather for tomorrow in Delhi",
        "navigate to the GitHub page for scikit-learn",
        "open Google Scholar and search for NLP papers",
        "compare prices of the iPhone across sites",
        "find a recipe for pasta carbonara",
        "download the latest Python installer",
        "check if the server is responding",
        "search Stack Overflow for the error message",
        "open the HDFC bank portal",
        "find reviews for the new restaurant near me",
    ],
    "desktop_automation": [
        "open VSCode and create a new project folder",
        "organize my Downloads folder by file type",
        "take a screenshot of the current window",
        "move all PDFs to the Documents folder",
        "close all background apps",
        "run the python script in the terminal",
        "rename all images in the folder sequentially",
        "create a backup of the project directory",
        "install the requirements from requirements.txt",
        "run git commit and push to main",
        "open the task manager and show CPU usage",
        "delete all files older than 30 days in temp",
        "compress the folder into a zip archive",
        "change the desktop wallpaper to nature theme",
        "enable dark mode on windows",
    ],
    "memory_query": [
        "what did I say about the project timeline last week",
        "remind me what we discussed in yesterday's session",
        "what was the name of that library I used before",
        "do I have any pending tasks for today",
        "what notes did I take during the AI lecture",
        "recall the API key I used for the weather service",
        "what was the deadline I mentioned for the submission",
        "find my previous conversation about the database design",
        "what was the login link for the course portal",
        "remember what I told you about my sleep schedule",
        "what are the items on my to-do list",
        "did I bookmark anything about reinforcement learning",
        "what was the contact email I stored for the recruiter",
        "show me everything I saved about the internship",
        "what were the three ideas I mentioned last session",
    ],
    "chitchat": [
        "hello",
        "hi monday",
        "hey there",
        "good morning",
        "good evening",
        "how are you today",
        "who are you",
        "what is your name",
        "nice to meet you",
        "thanks for the help",
        "thank you monday",
        "are you an AI",
        "tell me a joke",
        "how is the weather",
    ],
    "unclear": [
        "do the thing",
        "make it work",
        "you know what to do",
        "handle it",
        "take care of everything",
        "just fix it",
        "blah blah blah",
        "asdf qwer",
        "idk just do something useful",
        "go ahead",
        "whatever you think is best",
        "do something with this",
        "help",
        "yes please",
        "okay go",
    ],
}


#: Rows kept per intent. This was **500**, which quietly threw away 72% of the
#: corpus: `commands.csv` held 9,996 rows and the model was fitted on 2,800 of
#: them. Growing the dataset does nothing at all until this number moves, so it
#: is named here rather than left as a default buried in three call sites.
#:
#: 2,500 is the per-class target `datagen.generate` builds to, so the cap now
#: admits the whole corpus and stops being the binding constraint.
SAMPLES_PER_CLASS = 2500

#: The pipeline `get_trained_classifier()` fits for the running app. Named here
#: so `intent_classifier_report.md` can state it alongside the comparison
#: winner: SVM edges Logistic Regression on macro-F1 and costs ~47× the fit
#: time, and the model is refitted on any clone without the cached artefact.
PRODUCTION_MODEL = "Logistic Regression"


def build_synthetic_dataset(samples_per_class: int = SAMPLES_PER_CLASS) -> pd.DataFrame:
    """
    Loads the labelled command dataset, preferring the `datagen/` corpus.

    Resolution order:
      1. data/synthetic/commands.csv  (written by `python -m datagen.generate`)
      2. datagen.commands.build_corpus() in-process
      3. the COMMAND_SEEDS fallback above (last resort — see its caveat)

    The datagen corpus deliberately shares filler vocabulary across intents and
    carries ~6% label noise, so the classes overlap the way real user commands
    do. That is what makes the 5-model comparison informative; the seed
    fallback is separable enough that every linear model scores ~100%.

    Returns a DataFrame with columns ``command`` and ``intent``, capped at
    ``samples_per_class`` rows per intent.
    """
    df = _load_datagen_commands()
    if df is not None:
        return _balance(df, samples_per_class)

    warnings.warn(
        "datagen corpus unavailable — falling back to COMMAND_SEEDS, which is "
        "trivially separable and NOT valid for the CLO04 model comparison. "
        "Run `python -m datagen.generate` to restore the real dataset."
    )
    return _build_seed_dataset(samples_per_class)


def _load_datagen_commands() -> pd.DataFrame | None:
    """Reads the datagen corpus from CSV, or generates it in-process."""
    csv_path = PROJECT_ROOT / "data" / "synthetic" / "commands.csv"
    df = None

    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            df = None

    if df is None:
        try:
            from datagen.commands import build_corpus
            df = build_corpus()
        except Exception:
            return None

    # datagen writes `text`; earlier revisions of this module wrote `command`.
    if "text" in df.columns:
        df = df.rename(columns={"text": "command"})
    if "command" not in df.columns or "intent" not in df.columns:
        return None

    df = df.copy()
    df["intent"] = df["intent"].replace(DATAGEN_LABEL_ALIASES)
    unknown = set(df["intent"]) - set(INTENT_CLASSES)
    if unknown:
        warnings.warn(f"Dropping rows with unmapped intents: {sorted(unknown)}")
        df = df[df["intent"].isin(INTENT_CLASSES)]

    return df.dropna(subset=["command", "intent"]).reset_index(drop=True)


def _balance(df: pd.DataFrame, samples_per_class: int) -> pd.DataFrame:
    """Caps each intent at `samples_per_class` rows and reshuffles."""
    capped = df[df.groupby("intent").cumcount() < samples_per_class]
    return capped.sample(frac=1, random_state=42).reset_index(drop=True)


def _build_seed_dataset(samples_per_class: int = 500) -> pd.DataFrame:
    """Last-resort generator built from COMMAND_SEEDS. Trivially separable."""
    rng = np.random.default_rng(42)

    prefixes = [
        "please ", "can you ", "monday, ", "hey monday ", "quickly ", "",
        "i need you to ", "could you ", "would you mind ", "go ahead and ",
    ]
    suffixes = [
        "", " for me", " right now", " asap", " when you can", " please",
        " and let me know when done", " and report back",
    ]
    noise_words = ["just", "actually", "basically", "kindly", "also", "now"]

    records: List[Dict[str, str]] = []

    for intent, seeds in COMMAND_SEEDS.items():
        generated = set()
        attempts = 0
        while len(generated) < samples_per_class and attempts < samples_per_class * 20:
            attempts += 1
            seed = seeds[rng.integers(len(seeds))]
            prefix = prefixes[rng.integers(len(prefixes))]
            suffix = suffixes[rng.integers(len(suffixes))]
            command = f"{prefix}{seed}{suffix}".strip()

            # Optionally inject a noise word
            if rng.random() < 0.25:
                words = command.split()
                pos = rng.integers(max(1, len(words)))
                noise = noise_words[rng.integers(len(noise_words))]
                words.insert(int(pos), noise)
                command = " ".join(words)

            # Lowercase normalisation
            command = command.lower()
            generated.add(command)

        for cmd in list(generated)[:samples_per_class]:
            records.append({"command": cmd, "intent": intent})

    df = pd.DataFrame(records).sample(frac=1, random_state=42).reset_index(drop=True)
    return df


def build_pipelines() -> Dict[str, Pipeline]:
    """
    Returns a dict of named scikit-learn pipelines (TF-IDF → classifier),
    one for each algorithm being compared.
    """
    tfidf = dict(
        ngram_range=(1, 2),
        max_features=8000,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    return {
        "Logistic Regression": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf)),
            ("clf", LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs",
                                       random_state=42)),
        ]),
        "KNN": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf)),
            ("clf", KNeighborsClassifier(n_neighbors=7, metric="cosine")),
        ]),
        "Decision Tree": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf)),
            ("clf", DecisionTreeClassifier(max_depth=20, random_state=42)),
        ]),
        "Random Forest": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf)),
            ("clf", RandomForestClassifier(n_estimators=200, n_jobs=-1, random_state=42)),
        ]),
        "SVM": Pipeline([
            ("tfidf", TfidfVectorizer(**tfidf)),
            ("clf", SVC(kernel="linear", C=1.0, probability=True, random_state=42)),
        ]),
    }


def evaluate_model(
    pipeline: Pipeline,
    X_train: List[str],
    X_test: List[str],
    y_train: np.ndarray,
    y_test: np.ndarray,
    label_names: List[str],
) -> Dict:
    """
    Trains the pipeline and returns a comprehensive evaluation dictionary.
    """
    t0 = time.perf_counter()
    pipeline.fit(X_train, y_train)
    train_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    y_pred = pipeline.predict(X_test)
    infer_time = time.perf_counter() - t0

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "macro_precision": precision_score(y_test, y_pred, average="macro", zero_division=0),
        "macro_recall": recall_score(y_test, y_pred, average="macro", zero_division=0),
        "macro_f1": f1_score(y_test, y_pred, average="macro", zero_division=0),
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=label_names),
        "report": classification_report(y_test, y_pred, target_names=label_names,
                                        zero_division=0),
        "train_time_s": train_time,
        "infer_time_ms": infer_time * 1000,
        "y_pred": y_pred,
    }


def print_comparison_table(results: Dict[str, Dict]) -> str:
    """Prints a Rich comparison table and returns the winner model name."""
    table = Table(
        title="[bold gold1]Intent Classifier — Model Comparison[/]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Model", style="bold white", min_width=20)
    table.add_column("Accuracy", justify="right")
    table.add_column("Macro Precision", justify="right")
    table.add_column("Macro Recall", justify="right")
    table.add_column("Macro F1", justify="right")
    table.add_column("Train Time (s)", justify="right")
    table.add_column("Infer Time (ms)", justify="right")

    best_model = max(results, key=lambda k: results[k]["macro_f1"])

    for name, r in results.items():
        is_best = name == best_model
        style = "bold green" if is_best else ""
        mark = " ★" if is_best else ""
        table.add_row(
            f"{name}{mark}",
            f"{r['accuracy']:.4f}",
            f"{r['macro_precision']:.4f}",
            f"{r['macro_recall']:.4f}",
            f"{r['macro_f1']:.4f}",
            f"{r['train_time_s']:.2f}",
            f"{r['infer_time_ms']:.1f}",
            style=style,
        )

    console.print(table)
    return best_model


def print_confusion_matrix(cm: np.ndarray, labels: List[str], model_name: str) -> None:
    """Prints a confusion matrix as a Rich table."""
    table = Table(
        title=f"[bold gold1]Confusion Matrix — {model_name}[/]",
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("True \\ Pred", style="bold white")
    for label in labels:
        table.add_column(label[:8], justify="right")  # truncate for width

    for i, row_label in enumerate(labels):
        table.add_row(row_label[:12], *[str(cm[i][j]) for j in range(len(labels))])

    console.print(table)


def predict_intent(
    pipeline: Pipeline,
    command: str,
    confidence_threshold: float = 0.65,
) -> Tuple[str, float, bool]:
    """
    Predicts intent for a single command.

    Returns
    -------
    (intent, confidence, should_fallback_to_llm)
    """
    proba = pipeline.predict_proba([command])[0]
    confidence = float(np.max(proba))
    intent = pipeline.classes_[int(np.argmax(proba))]
    fallback = confidence < confidence_threshold or intent == "unclear"
    return intent, confidence, fallback


def run() -> Pipeline:
    """
    Main entry point. Builds dataset, trains all models, evaluates, prints
    results, and returns the best pipeline ready for use.
    """
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.1: Intent Classifier[/]")
    console.print("\n[dim]CLO04 · Classification · Lab 14–20[/]\n")

    # ── Dataset ────────────────────────────────────────────────────────────────
    console.print("[cyan]► Loading the labelled command corpus...[/]")
    df = build_synthetic_dataset()
    console.print(f"  Total samples  : [bold]{len(df)}[/]")
    console.print(f"  Classes        : [bold]{df['intent'].nunique()}[/]")
    if "source" in df.columns:
        prov = df["source"].value_counts().to_dict()
        console.print(
            f"  Provenance     : [bold]{prov.get('massive', 0)}[/] real (Amazon "
            f"MASSIVE, en-US) + [bold]{prov.get('generated', 0)}[/] generated"
        )
    console.print(f"  Class balance  :\n{df['intent'].value_counts().to_string()}\n")

    X = df["command"].tolist()
    y = df["intent"].tolist()
    label_names = INTENT_CLASSES

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    console.print(f"  Train size: {len(X_train)} | Test size: {len(X_test)}\n")

    # ── Train & Evaluate All Models ────────────────────────────────────────────
    pipelines = build_pipelines()
    results: Dict[str, Dict] = {}

    console.print("[cyan]► Training and evaluating models...[/]")
    for name, pipeline in pipelines.items():
        console.print(f"  Training [bold]{name}[/]...")
        results[name] = evaluate_model(pipeline, X_train, X_test, y_train, y_test, label_names)

    console.print()

    # ── Comparison Table ───────────────────────────────────────────────────────
    best_name = print_comparison_table(results)
    console.print(f"\n[bold green]► Best model: {best_name}[/]")

    # ── Confusion Matrix for Best ──────────────────────────────────────────────
    console.print()
    print_confusion_matrix(
        results[best_name]["confusion_matrix"], label_names, best_name
    )

    # ── Detailed Classification Report ────────────────────────────────────────
    console.print(f"\n[bold cyan]Full Classification Report — {best_name}[/]")
    console.print(results[best_name]["report"])

    # ── Persist the comparison ────────────────────────────────────────────────
    # `reports/intent_classifier_comparison.csv` and `intent_classifier_report.md`
    # were last written on 2026-07-23 by a generator that no longer exists, and
    # nothing in the repo has rewritten them since — while `data/DATASET.md`
    # cites the report as the five-model evidence. Anyone quoting it was quoting
    # a number produced from a corpus that had since been replaced twice. They
    # are written from this run now, so the published comparison and the live
    # corpus cannot drift apart again.
    _write_comparison_artefacts(results, best_name, df)

    # ── Live Inference Demo ────────────────────────────────────────────────────
    console.rule("[bold gold1]Live Inference Demo[/]")
    best_pipeline = pipelines[best_name]

    demo_commands = [
        "please summarize the quarterly report PDF for me",
        "send an email to my professor about the upcoming exam",
        "find the cheapest flights to Bangalore on MakeMyTrip",
        "organize my Downloads folder and delete duplicates",
        "what did I say about the database design last week",
        "just do it",
    ]

    demo_table = Table(box=box.ROUNDED, header_style="bold cyan",
                       title="[bold gold1]Inference Examples[/]")
    demo_table.add_column("Command", max_width=48)
    demo_table.add_column("Predicted Intent", justify="center")
    demo_table.add_column("Confidence", justify="right")
    demo_table.add_column("LLM Fallback?", justify="center")

    for cmd in demo_commands:
        intent, conf, fallback = predict_intent(best_pipeline, cmd)
        demo_table.add_row(
            cmd[:48],
            f"[bold]{intent}[/]",
            f"{conf:.2%}",
            "[red]Yes[/]" if fallback else "[green]No[/]",
        )

    console.print(demo_table)

    console.print(
        "\n[bold green]✓ Component 2.1 complete.[/] "
        f"Best model: [bold]{best_name}[/] — ready for production routing.\n"
    )
    return best_pipeline


def _write_comparison_artefacts(
    results: Dict[str, Dict], best_name: str, df: pd.DataFrame
) -> None:
    """Writes the five-model comparison to `reports/`, keyed to this corpus."""
    reports = PROJECT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    rows = sorted(
        (
            {
                "model": name.replace(" ", ""),
                "accuracy": round(r["accuracy"], 4),
                "precision_macro": round(r["macro_precision"], 4),
                "recall_macro": round(r["macro_recall"], 4),
                "f1_macro": round(r["macro_f1"], 4),
                "fit_seconds": round(r["train_time_s"], 3),
            }
            for name, r in results.items()
        ),
        key=lambda r: r["f1_macro"],
        reverse=True,
    )
    pd.DataFrame(rows).to_csv(reports / "intent_classifier_comparison.csv", index=False)

    prov = df["source"].value_counts().to_dict() if "source" in df.columns else {}
    provenance = (
        f"{prov.get('massive', 0)} real (Amazon MASSIVE, en-US) + "
        f"{prov.get('generated', 0)} generated"
        if prov else f"{len(df)} rows"
    )
    header = "| " + " | ".join(rows[0]) + " |"
    divider = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = [
        "| " + " | ".join(str(v) for v in r.values()) + " |" for r in rows
    ]
    best = results[best_name]
    md = [
        "# 2.1 Intent Classifier — Results (CLO04)",
        "",
        f"Winner: **{best_name}** by macro-F1.",
        "",
        f"Corpus: **{len(df)}** rows, {df['intent'].nunique()} classes — {provenance}.",
        "",
        "## Model comparison",
        "",
        header, divider, *body,
        "",
        "## Best model — macro metrics",
        "",
        f"- accuracy: {best['accuracy']:.4f}",
        f"- precision (macro): {best['macro_precision']:.4f}",
        f"- recall (macro): {best['macro_recall']:.4f}",
        f"- f1 (macro): {best['macro_f1']:.4f}",
        "",
        "## What this number is, and is not",
        "",
        "This is a held-out slice of the corpus the model trained on. It measures",
        "that the model learned the corpus — not that the corpus resembles what a",
        "user types. For the second question see",
        "[`real_command_evidence.md`](real_command_evidence.md), which evaluates",
        "the app's own advertised commands and paraphrases of them.",
        "",
        "## Which model production actually loads",
        "",
        f"`get_trained_classifier()` fits **{PRODUCTION_MODEL}**, not necessarily the",
        f"winner above. On this corpus {PRODUCTION_MODEL} fits in "
        f"{results[PRODUCTION_MODEL]['train_time_s']:.2f}s against "
        f"{best['train_time_s']:.2f}s for {best_name}, for "
        f"{best['macro_f1'] - results[PRODUCTION_MODEL]['macro_f1']:+.4f} macro-F1 —"
        " and the model is refitted whenever the cached artefact is missing, "
        "including on a fresh clone. The comparison is the coursework "
        "deliverable; the production choice is a latency trade-off, and stating "
        "both is the point.",
        "",
        "_Generated by `py -3.12 -m ml.intent_classifier`._",
    ]
    (reports / "intent_classifier_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


# ── Public API ─────────────────────────────────────────────────────────────────
def get_trained_classifier() -> Pipeline:
    """Returns a trained intent-classifier pipeline (uses best model found)."""
    model_dir = PROJECT_ROOT / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "intent_classifier.joblib"

    if model_path.exists():
        try:
            return joblib.load(model_path)
        except Exception:
            pass

    df = build_synthetic_dataset()
    X, y = df["command"].tolist(), df["intent"].tolist()
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    pipeline = build_pipelines()[PRODUCTION_MODEL]
    pipeline.fit(X_train, y_train)

    try:
        joblib.dump(pipeline, model_path)
    except Exception as e:
        warnings.warn(f"Could not save model artifact to {model_path}: {e}")

    return pipeline


if __name__ == "__main__":
    run()

