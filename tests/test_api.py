"""
Integration Tests — FastAPI REST Server Endpoints
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestAPIServer(unittest.TestCase):
    def test_health_endpoint(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ONLINE")
        self.assertIn("M.O.N.D.A.Y.", data["engine"])

    def test_root_endpoint(self):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ONLINE")

    def test_app_endpoint(self):
        response = client.get("/app")
        self.assertEqual(response.status_code, 200)

    def test_agent_execute_endpoint(self):
        payload = {"command": "summarize notes", "user_approved": True}
        response = client.post("/agent/execute", json=payload)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
