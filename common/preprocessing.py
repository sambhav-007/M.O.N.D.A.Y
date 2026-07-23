"""Reusable preprocessing for the supervised text component (2.1).

Kept here rather than inside the classifier package so the same cleaning +
vectorization can be reused by the XAI layer (2.6) and any demo harness.
"""

from __future__ import annotations

import re

from sklearn.feature_extraction.text import TfidfVectorizer

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def clean_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Deliberately simple — the graded pipeline is text -> cleaning ->
    TF-IDF -> classifier, and keeping cleaning transparent helps the XAI step.
    """
    text = text.lower()
    text = _NON_ALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip()


def build_vectorizer(**overrides) -> TfidfVectorizer:
    """TF-IDF feature extractor (CLO03 feature engineering).

    Unigrams + bigrams capture short command phrasings like "open vscode".
    """
    params = dict(
        preprocessor=clean_text,
        ngram_range=(1, 2),
        min_df=2,
        max_features=5000,
        sublinear_tf=True,
    )
    params.update(overrides)
    return TfidfVectorizer(**params)
