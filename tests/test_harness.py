"""
Integration Test — Unified System Harness Execution
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness import run_integration_harness


class TestSystemHarness(unittest.TestCase):
    def test_harness_execution(self):
        summary = run_integration_harness()
        self.assertIn("2.1_intent", summary)
        self.assertIn("2.2_eta", summary)
        self.assertIn("2.3_clustering", summary)
        self.assertIn("2.4_assoc", summary)
        self.assertIn("2.5_rl", summary)
        self.assertEqual(summary.get("master_planner"), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
