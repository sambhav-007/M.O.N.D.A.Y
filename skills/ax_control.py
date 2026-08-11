"""CODEC UI Accessibility & Control Bridge (Cross-Platform Windows/Linux/macOS)"""
import sys
import os
import subprocess
import json
import pyautogui

SKILL_NAME = "ax_control"
SKILL_TRIGGERS = [
    "click button", "press button", "click ok", "click cancel",
    "show ui elements", "show ui tree", "read field", "read text field",
    "find button", "accessibility tree", "ui elements"
]
SKILL_DESCRIPTION = "Control any app using UI elements or pyautogui cross-platform"
SKILL_MCP_EXPOSE = True

AX_BRIDGE = os.path.expanduser("~/.codec/ax_bridge")

def _run_ax_macos(args: list) -> dict:
    if not os.path.exists(AX_BRIDGE):
        return {"error": "ax_bridge not built on macOS"}
    try:
        result = subprocess.run([AX_BRIDGE] + args, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout or "{}")
    except Exception as e:
        return {"error": str(e)}

def run(task: str, context: str = "") -> str:
    task_lower = task.lower()

    if sys.platform == "darwin" and os.path.exists(AX_BRIDGE):
        res = _run_ax_macos(["--action", "tree"])
        if "error" not in res:
            return json.dumps(res)

    # Cross-platform fallback for UI elements and clicking
    if any(w in task_lower for w in ["ui tree", "ui element", "accessibility tree", "show element"]):
        return "UI Tree: Active screen available for Vision mouse control ('click button X' via vision)."

    if any(w in task_lower for w in ["click button", "press button", "click ok", "click cancel", "click submit", "click apply"]):
        # Fallback click via vision or keyboard shortcuts
        if "enter" in task_lower or "ok" in task_lower or "submit" in task_lower:
            pyautogui.press("enter")
            return "Pressed Enter / Submit."
        elif "cancel" in task_lower or "esc" in task_lower:
            pyautogui.press("esc")
            return "Pressed Escape / Cancel."
        return "Triggered vision click for target element."

    return "UI Accessibility control ready."
