"""
Unit Tests — ML Pipelines & Artifact Entry Points
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from ml.intent_classifier import get_trained_classifier, predict_intent
from ml.task_eta_regression import get_trained_regressor, engineer_features, generate_action_log
from ml.memory_clustering import generate_memory_embeddings
from ml.association_rules import generate_session_log, encode_transactions
from ml.rl_router import EpsilonGreedyBandit, ROUTING_ACTIONS


class TestMLPipelines(unittest.TestCase):
    def test_intent_classifier_inference(self):
        pipeline = get_trained_classifier()
        intent, confidence, fallback = predict_intent(pipeline, "summarize the PDF document")
        self.assertIsInstance(intent, str)
        self.assertTrue(0.0 <= confidence <= 1.0)
        self.assertIsInstance(fallback, bool)

    def test_task_eta_regression_inference(self):
        pipeline = get_trained_regressor()
        df = generate_action_log(n_samples=10, seed=42)
        X, _ = engineer_features(df)
        preds = pipeline.predict(X)
        self.assertEqual(len(preds), 10)
        self.assertTrue((preds > 0).all())

    def test_memory_clustering_generation(self):
        embeddings, true_labels, sample_texts = generate_memory_embeddings(n_samples=50, seed=42)
        self.assertGreater(embeddings.shape[0], 0)
        self.assertEqual(embeddings.shape[1], 64)

    def test_association_rules_encoding(self):
        sessions = generate_session_log(n_sessions=20, seed=42)
        self.assertGreater(len(sessions), 0)
        df_encoded = encode_transactions(sessions)
        self.assertIsInstance(df_encoded, pd.DataFrame)
        self.assertGreater(df_encoded.shape[0], 0)

    def test_rl_router_bandit(self):
        bandit = EpsilonGreedyBandit(n_arms=len(ROUTING_ACTIONS), epsilon=0.1, seed=42)
        action_idx = bandit.select_action()
        self.assertTrue(0 <= action_idx < len(ROUTING_ACTIONS))
        bandit.update(action_idx, reward=1.0)
        self.assertEqual(bandit.pull_counts[action_idx], 1)


if __name__ == "__main__":
    unittest.main()
