"""Production entry point for the Intent Classifier (2.1).

Loads the trained pipeline and classifies raw command text. Implements the
routing contract from the README: a high-confidence prediction is returned as-is
(the harness dispatches straight to that agent, skipping the LLM Planner); a
low-confidence prediction is coerced to ``llm_fallback`` so the command falls
through to the Planner — which is exactly the signal the RL router (2.5) learns from.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib

MODEL_PATH = Path(__file__).with_name("model.joblib")
DEFAULT_THRESHOLD = 0.55
FALLBACK_INTENT = "llm_fallback"


@dataclass
class Prediction:
    intent: str          # routed intent (possibly coerced to llm_fallback)
    confidence: float    # max class probability from the model
    raw_intent: str      # what the model actually predicted, pre-threshold
    fell_back: bool      # True if confidence was below threshold


class IntentClassifier:
    def __init__(self, model_path: Path = MODEL_PATH):
        if not model_path.exists():
            raise FileNotFoundError(
                f"{model_path} not found — run `python -m ml.intent_classifier.train` first."
            )
        bundle = joblib.load(model_path)
        self.pipeline = bundle["pipeline"]
        self.model_name = bundle["model_name"]
        self.labels = bundle["labels"]

    def predict(self, text: str, threshold: float = DEFAULT_THRESHOLD) -> Prediction:
        proba = self.pipeline.predict_proba([text])[0]
        classes = self.pipeline.classes_
        best_idx = proba.argmax()
        raw_intent = str(classes[best_idx])
        confidence = float(proba[best_idx])

        if confidence < threshold and raw_intent != FALLBACK_INTENT:
            return Prediction(FALLBACK_INTENT, confidence, raw_intent, True)
        return Prediction(raw_intent, confidence, raw_intent, False)


def _demo() -> None:
    clf = IntentClassifier()
    samples = [
        "summarize the quarterly report",
        "email priyanka the schedule",
        "open vs code and run the build",
        "what did I save about the DBMS project",
        "search github for fastapi examples",
        "just deal with it",
    ]
    print(f"Loaded model: {clf.model_name}\n")
    for s in samples:
        p = clf.predict(s)
        tag = "  -> FALLBACK to Planner" if p.fell_back else ""
        print(f"{s!r:52} -> {p.intent:18} ({p.confidence:.2f}){tag}")


if __name__ == "__main__":
    _demo()
