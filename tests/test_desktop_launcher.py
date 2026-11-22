"""Regression coverage for the native desktop launcher bridge."""

import app
import api.main as api_main


def test_pywebview_bridge_does_not_supply_tier2_approval(monkeypatch):
    captured = {}

    class FakePlanner:
        def process_command(self, command, user_approved=False):
            captured["command"] = command
            captured["user_approved"] = user_approved
            return {"success": True}

    monkeypatch.setattr(api_main, "get_planner", lambda: FakePlanner())

    result = app.DesktopWindowApi().execute_command("kill notepad")

    assert result == {"success": True}
    assert captured == {"command": "kill notepad", "user_approved": False}
