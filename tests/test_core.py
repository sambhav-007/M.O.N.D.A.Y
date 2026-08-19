"""
Unit Tests — Core Engine Subsystem (Task DAG, Security, Tools, Autonomy)
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.security import classify_action_risk, evaluate_action_permission
from core.tool_registry import ToolRegistry
from core.multi_step import split_compound
from core.planner import MasterPlanner
from core.autonomy import AutonomyDaemon


class TestCoreSubsystem(unittest.TestCase):
    def test_security_manager_tiers(self):
        tier_1, desc_1 = classify_action_risk("search_memory")
        self.assertEqual(tier_1, 1)

        tier_2, desc_2 = classify_action_risk("delete_file")
        self.assertEqual(tier_2, 2)

        res_permission = evaluate_action_permission("send_email", target="user@test.com")
        self.assertEqual(res_permission["risk_tier"], 2)

    def test_tool_registry_registration(self):
        reg = ToolRegistry()
        tools = reg.list_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

    def test_multi_step_split_keeps_the_order_asked_for(self):
        """`TaskDAGEngine` was deleted 2026-08-18 — ROADMAP Phase 10."""
        steps = split_compound("search memory and then summarize document")
        self.assertEqual(steps, ["search memory", "summarize document"])

    def test_planner_decomposition(self):
        planner = MasterPlanner()
        plan = planner.process_command("summarize my notes", user_approved=True)
        self.assertIsNotNone(plan)

    def test_autonomy_daemon(self):
        daemon = AutonomyDaemon()
        self.assertIsNotNone(daemon)


if __name__ == "__main__":
    unittest.main()
