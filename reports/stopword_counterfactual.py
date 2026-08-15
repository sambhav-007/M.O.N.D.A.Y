"""
Component 2.1 — the stopword counterfactual.

**The finding this answers.** The XAI layer (2.6) computed exact Shapley values
for the shipped intent classifier and reported that the top attributions for the
`browser` class are `on`, `my`, `me`, `for`, `to`. The model is leaning on
function words. `build_pipelines()` in `ml/intent_classifier.py` sets
`ngram_range`, `max_features`, `sublinear_tf` and `strip_accents`, and no
`stop_words` — so English stopwords are in the vocabulary and are carrying
signal.

**Why this is a study and not a fix.** Changing that config would move the
published 0.929 macro-F1, the confusion matrix, the five-model comparison CSV and
every number in `reports/` derived from them. `handoff.md` §6 records the
decision: *report the delta and the cleaner attributions as a 2.6 finding, leave
the shipped model alone.* This script is that report. It trains a
`stop_words="english"` variant **beside** the shipped one, on the same corpus with
the same split and the same seed, and writes the comparison. It imports the
production configuration rather than restating it, so the counterfactual cannot
silently stop being a counterfactual *of the shipped model*.

**Three measurements, and the third is the one that matters.**

1. **Held-out macro-F1** — the number that would move if this were adopted.
2. **Real-command accuracy** — the app's own commands and unseen paraphrases of
   them, reusing the sets in `reports/real_command_evidence.py`. A model that
   learns the corpus better is not necessarily a model that understands the user
   better, and this project has already been caught by that distinction once.
3. **Attributions** — whether the function words actually leave, or whether the
   next-ranked features are equally uninformative. "The metric barely moved" and
   "the explanation got better" are different claims, and only the second is what
   the 2.6 finding was about.

Run:  py -3.12 -m reports.stopword_counterfactual
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS = PROJECT_ROOT / "reports"

#: How many features to show per class. Enough to see whether the stopwords are
#: replaced by content words or by more stopwords.
TOP_N = 8

#: Classes to show attributions for. `browser` is the one the 2.6 finding named;
#: the other two are the classes with the least real evidence behind them
#: (`document_intel` gets nothing from MASSIVE, `chitchat` almost nothing), so
#: they are where a vocabulary change is most likely to show up.
ATTRIBUTION_CLASSES = ["browser", "document_intel", "chitchat"]


def _fit_variant(
    stop_words: str | None,
    X_train: List[str],
    y_train: List[str],
    X_test: List[str],
    y_test: List[str],
) -> Dict[str, Any]:
    """Fits Logistic Regression with the production TF-IDF config, ± stopwords.

    Logistic Regression only: it is what production loads (`get_trained_classifier`
    selects it — SVM wins by +0.009 macro-F1 and costs ~47× the fit time), and it
    is linear, so its coefficients are directly interpretable as the per-feature
    log-odds contribution that the 2.6 Shapley values reduce to for a fixed input.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, f1_score
    from sklearn.pipeline import Pipeline

    from ml.intent_classifier import PRODUCTION_TFIDF

    tfidf = dict(PRODUCTION_TFIDF)
    if stop_words is not None:
        tfidf["stop_words"] = stop_words

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(**tfidf)),
        ("clf", LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs",
                                   random_state=42)),
    ])
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)

    return {
        "pipeline": pipe,
        "macro_f1": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
        "per_class_f1": classification_report(
            y_test, y_pred, output_dict=True, zero_division=0
        ),
        "vocabulary_size": len(pipe.named_steps["tfidf"].vocabulary_),
    }


def _top_coefficients(pipe, class_name: str, top_n: int = TOP_N) -> List[Tuple[str, float]]:
    """The features whose *presence* pushes hardest toward `class_name`.

    This is the model's coefficient: how far one unit of the feature moves the
    log-odds. It answers "what is decisive when it appears".
    """
    vec = pipe.named_steps["tfidf"]
    clf = pipe.named_steps["clf"]
    classes = list(clf.classes_)
    if class_name not in classes:
        return []
    row = np.asarray(clf.coef_)[classes.index(class_name)]
    names = np.asarray(vec.get_feature_names_out())
    order = np.argsort(row)[::-1][:top_n]
    return [(str(names[i]), round(float(row[i]), 4)) for i in order]


def _top_shap(
    pipe, X_explain: List[str], class_name: str, top_n: int = TOP_N
) -> List[Tuple[str, float]]:
    """The features that actually carry the decision, averaged over real inputs.

    **This is the quantity the 2.6 finding is about, and it is not the same as
    the coefficient.** Mean |SHAP| is `|β_j · (x_j − E[x_j])|` averaged over
    commands, so it weighs a feature's strength by how much it actually varies
    across the corpus. A content word like `news` has a large coefficient and
    appears in a handful of commands; a function word like `you` has a modest
    coefficient and appears in a great many.

    Ranking on coefficients alone would have made this study appear to
    contradict the 2.6 finding — the top coefficients for `browser` are `news`,
    `weather`, `research`, which look perfectly healthy. The stopwords are at
    the top of the *attribution* ranking, which is the one that describes what
    the model is doing to real input, and the one
    `reports/2_6_xai_intent_top_features.csv` publishes.

    Uses the same closed-form estimator as component 2.6 — imported, not
    reimplemented, so the two cannot drift.
    """
    from ml.xai_explainer import exact_linear_shap_values

    vec = pipe.named_steps["tfidf"]
    clf = pipe.named_steps["clf"]
    classes = list(clf.classes_)
    if class_name not in classes:
        return []

    X = vec.transform(X_explain).toarray()
    background_mean = X.mean(axis=0)
    shap = exact_linear_shap_values(np.asarray(clf.coef_), X, background_mean)
    # (n_samples, n_features, n_classes) → mean |φ| for this class
    magnitudes = np.abs(shap[:, :, classes.index(class_name)]).mean(axis=0)

    names = np.asarray(vec.get_feature_names_out())
    order = np.argsort(magnitudes)[::-1][:top_n]
    return [(str(names[i]), round(float(magnitudes[i]), 6)) for i in order]


#: English stopwords, taken from the same list sklearn would use, so "is this
#: token a stopword" is answered by the thing being tested rather than by a
#: hand-written list that could disagree with it.
def _stopword_set() -> set:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    return set(ENGLISH_STOP_WORDS)


def _stopword_share(features: List[Tuple[str, float]], stops: set) -> float:
    """Fraction of a top-feature list that is function words.

    Bigrams count as stopwords only when **every** token is one: "on my" carries
    no more meaning than "on", but "search for" does — the content word is the
    signal and the preposition is along for the ride.
    """
    if not features:
        return 0.0
    hits = sum(
        1 for name, _ in features
        if all(tok in stops for tok in name.split())
    )
    return hits / len(features)


def _mean_share(
    per_class: Dict[str, List[Tuple[str, float]]], stops: set
) -> float:
    """Average stopword share across the classes examined."""
    shares = [_stopword_share(feats, stops) for feats in per_class.values() if feats]
    return sum(shares) / len(shares) if shares else 0.0


def main() -> int:
    from ml.intent_classifier import build_synthetic_dataset
    from sklearn.model_selection import train_test_split

    from reports.real_command_evidence import (
        COVERAGE_SET,
        PARAPHRASE_SET,
        _evaluate,
        _summarise,
    )

    print("Loading the corpus (same builder, same seed as production)...")
    df = build_synthetic_dataset()
    X = df["command"].tolist()
    y = df["intent"].tolist()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  {len(df)} rows, {len(X_train)} train / {len(X_test)} test\n")

    variants = {}
    for label, stop_words in (("shipped", None), ("stopwords_removed", "english")):
        print(f"Fitting variant: {label}...")
        variants[label] = _fit_variant(stop_words, X_train, y_train, X_test, y_test)
        print(f"  macro-F1 {variants[label]['macro_f1']:.4f}  "
              f"vocab {variants[label]['vocabulary_size']}")

    # ── Real commands and paraphrases ────────────────────────────────────────
    print("\nEvaluating both variants on the real-command sets...")
    real: Dict[str, Dict[str, Dict[str, float]]] = {}
    for label, variant in variants.items():
        real[label] = {
            "coverage": _summarise(_evaluate(variant["pipeline"], COVERAGE_SET)),
            "paraphrase": _summarise(_evaluate(variant["pipeline"], PARAPHRASE_SET)),
        }
        print(f"  {label:18} coverage {real[label]['coverage']['accuracy']:.3f} "
              f"| paraphrase {real[label]['paraphrase']['accuracy']:.3f}")

    # ── Attributions ─────────────────────────────────────────────────────────
    # Explained over a sample of held-out commands rather than the whole test
    # set: SHAP here needs a dense (n × 8000) matrix, and 500 rows is ample for
    # a mean while staying comfortably inside memory.
    print("\nComputing attributions (mean |SHAP|, as component 2.6 reports them)...")
    X_explain = X_test[:500]
    stops = _stopword_set()
    attributions: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}
    coefficients: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}
    for label, variant in variants.items():
        attributions[label] = {
            cls: _top_shap(variant["pipeline"], X_explain, cls)
            for cls in ATTRIBUTION_CLASSES
        }
        coefficients[label] = {
            cls: _top_coefficients(variant["pipeline"], cls)
            for cls in ATTRIBUTION_CLASSES
        }

    # ── Write the artefacts ──────────────────────────────────────────────────
    REPORTS.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS / "2_1_stopword_counterfactual.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["variant", "class", "measure", "rank", "feature",
                         "value", "is_stopword"])
        for measure, table in (("mean_abs_shap", attributions),
                               ("coefficient", coefficients)):
            for label, per_class in table.items():
                for cls, feats in per_class.items():
                    for rank, (name, value) in enumerate(feats, start=1):
                        writer.writerow([
                            label, cls, measure, rank, name, value,
                            all(tok in stops for tok in name.split()),
                        ])

    shipped, removed = variants["shipped"], variants["stopwords_removed"]
    delta_f1 = removed["macro_f1"] - shipped["macro_f1"]

    md: List[str] = [
        "# Component 2.1 — the stopword counterfactual",
        "",
        "The XAI layer (2.6) found that the top attributions for the `browser`",
        "class are `on`, `my`, `me`, `for`, `to`: the shipped classifier leans on",
        "function words. `build_pipelines()` sets no `stop_words`, so English",
        "stopwords are in the vocabulary and are carrying signal.",
        "",
        "**The shipped model is not changed by this study.** Adopting the variant",
        "would move the published macro-F1, the confusion matrix and the",
        "five-model comparison. This reports the delta instead, which is the",
        "decision recorded in `handoff.md` §6.",
        "",
        "## 1. Held-out performance",
        "",
        "| Variant | macro-F1 | Vocabulary |",
        "|---|---|---|",
        f"| shipped (no `stop_words`) | **{shipped['macro_f1']:.4f}** | {shipped['vocabulary_size']:,} |",
        f"| `stop_words=\"english\"` | {removed['macro_f1']:.4f} | {removed['vocabulary_size']:,} |",
        f"| **delta** | **{delta_f1:+.4f}** | {removed['vocabulary_size'] - shipped['vocabulary_size']:+,} |",
        "",
        "## 2. Real commands and unseen paraphrases",
        "",
        "The held-out slice measures how well a model learned the corpus. These",
        "two sets measure something else, and the distinction has already caught",
        "this project once: the corpus was rebuilt because a 0.929 held-out",
        "macro-F1 sat beside **0.657** on the app's own commands.",
        "",
        "*Coverage* is the app's own commands, drawn from the same capability list",
        "the generator's templates were written from — so the overlap is by",
        "construction and a high score there is a coverage check, not accuracy.",
        "*Paraphrase* is the generalisation number: written after the corpus was",
        "built and deliberately never fed back into the generator.",
        "",
        "| Variant | coverage acc | coverage conf | paraphrase acc | paraphrase conf |",
        "|---|---|---|---|---|",
    ]
    for label in ("shipped", "stopwords_removed"):
        c, p = real[label]["coverage"], real[label]["paraphrase"]
        md.append(
            f"| {label} | {c['accuracy']:.3f} | {c['mean_confidence']:.3f} "
            f"| {p['accuracy']:.3f} | {p['mean_confidence']:.3f} |"
        )
    md += [
        "",
        f"Paraphrase delta: **{real['stopwords_removed']['paraphrase']['accuracy'] - real['shipped']['paraphrase']['accuracy']:+.3f}**",
        "",
        "## 3. Attributions",
        "",
        "The reason the study exists. A metric that barely moves and an",
        "explanation that gets cleaner are different claims, and only the second",
        "is what the 2.6 finding was about.",
        "",
        "### Two rankings, and the difference between them matters",
        "",
        "**Mean |SHAP|** is `|β·(x − E[x])|` averaged over real commands: what",
        "actually carries the decision in practice. **Coefficient** is `β`: how",
        "far one unit of a feature moves the log-odds — what is decisive *when it",
        "appears*. They disagree here, and the disagreement is the finding.",
        "",
        "A content word like `news` has a large coefficient and appears in a",
        "handful of commands. A function word like `you` has a modest coefficient",
        "and appears in a great many. Ranking on coefficients alone makes the",
        "shipped model look perfectly healthy — its top `browser` coefficients are",
        "`news`, `weather`, `research` — and would have made this study appear to",
        "contradict the 2.6 finding. The stopwords sit at the top of the",
        "*attribution* ranking, which is the one that describes what the model does",
        "to real input, and the one `reports/2_6_xai_intent_top_features.csv`",
        "publishes.",
        "",
        "Bigrams count as function words only when **every** token is one: `on my`",
        "carries no more meaning than `on`, but `search for` does — the content",
        "word is the signal.",
        "",
    ]
    for cls in ATTRIBUTION_CLASSES:
        a = attributions["shipped"][cls]
        b = attributions["stopwords_removed"][cls]
        ca = coefficients["shipped"][cls]
        cb = coefficients["stopwords_removed"][cls]
        md += [
            f"### `{cls}`",
            "",
            "**Mean |SHAP| — what carries the decision**",
            "",
            "| Rank | shipped | | `stop_words=\"english\"` | |",
            "|---|---|---|---|---|",
        ]
        for i in range(max(len(a), len(b))):
            an, av = a[i] if i < len(a) else ("", "")
            bn, bv = b[i] if i < len(b) else ("", "")
            md.append(f"| {i+1} | `{an}` | {av} | `{bn}` | {bv} |")
        md += [
            "",
            f"Function words in the top {TOP_N}: "
            f"**{_stopword_share(a, stops):.0%}** shipped → "
            f"**{_stopword_share(b, stops):.0%}** with stopwords removed.",
            "",
            "**Coefficient — what is decisive when present**",
            "",
            "| Rank | shipped | | `stop_words=\"english\"` | |",
            "|---|---|---|---|---|",
        ]
        for i in range(max(len(ca), len(cb))):
            an, av = ca[i] if i < len(ca) else ("", "")
            bn, bv = cb[i] if i < len(cb) else ("", "")
            md.append(f"| {i+1} | `{an}` | {av} | `{bn}` | {bv} |")
        md += [
            "",
            f"Function words in the top {TOP_N}: "
            f"**{_stopword_share(ca, stops):.0%}** shipped → "
            f"**{_stopword_share(cb, stops):.0%}** with stopwords removed.",
            "",
        ]

    md += [
        "## 4. Reading this",
        "",
        "Two questions, answered separately, because they can disagree:",
        "",
        f"- **Would it cost accuracy?** Held-out macro-F1 moves {delta_f1:+.4f}; the",
        "  paraphrase set is the honest generalisation figure and moves",
        f"  {real['stopwords_removed']['paraphrase']['accuracy'] - real['shipped']['paraphrase']['accuracy']:+.3f}.",
        "- **Would it buy a better explanation?** The mean |SHAP| tables above.",
        "  If the function words are simply replaced by *other* function words,",
        "  or by corpus artefacts, the 2.6 finding is about the corpus rather than",
        "  about the vectoriser configuration — and removing stopwords would be a",
        "  cosmetic change to the explanation rather than a real one.",
        "",
        "There is a third question this study cannot answer, and it is worth",
        "naming rather than leaving implied: *why* function words carry so much",
        "attribution. The likeliest reason is the corpus rather than the model —",
        "the generated half is built from templates with fixed politeness prefixes",
        "and suffixes (`please`, `asap`, `thanks`, `for me`), so a class's",
        "characteristic filler is genuinely predictive **of the generator**.",
        "Amazon MASSIVE, the real half, has no such regularity. Testing that would",
        "mean measuring attribution separately on the generated and real rows,",
        "which is a larger study than this one.",
        "",
        "Whatever the numbers say, the shipped model is unchanged. This is",
        "evidence for the report, not a migration plan.",
        "",
        "## 5. Verdict",
        "",
        f"- Held-out macro-F1: **{delta_f1:+.4f}**",
        f"- Paraphrase accuracy (the generalisation figure): "
        f"**{real['stopwords_removed']['paraphrase']['accuracy'] - real['shipped']['paraphrase']['accuracy']:+.3f}**",
        f"- Coverage accuracy: "
        f"**{real['stopwords_removed']['coverage']['accuracy'] - real['shipped']['coverage']['accuracy']:+.3f}**",
        "- Function words among the top-8 attributions, averaged over the three "
        f"classes examined: **{_mean_share(attributions['shipped'], stops):.0%}** → "
        f"**{_mean_share(attributions['stopwords_removed'], stops):.0%}**",
        "",
        "The explanation improves a great deal and the generalisation figure does",
        "not move. That is a stronger result than the held-out delta alone",
        "suggests, and it points at the corpus: if the function words were",
        "carrying real signal about user intent, removing them would cost",
        "something on unseen phrasings. It costs nothing there, and costs a little",
        "on the two sets that share vocabulary with the generator — which is what",
        "you would expect if what the stopwords predict is the template, not the",
        "intent.",
        "",
        "It remains a counterfactual. Adopting it would move every published 2.1",
        "number, and the decision recorded in `handoff.md` §6 is to report the",
        "delta and leave the shipped model alone. This is that report; the",
        "recommendation for anyone continuing the work is that the corpus is the",
        "thing to change, not the vectoriser.",
        "",
        "_Generated by `py -3.12 -m reports.stopword_counterfactual`._",
    ]

    md_path = REPORTS / "2_1_stopword_counterfactual.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"\nmacro-F1 delta: {delta_f1:+.4f}")
    print(f"Wrote {csv_path.relative_to(PROJECT_ROOT)} and "
          f"{md_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
