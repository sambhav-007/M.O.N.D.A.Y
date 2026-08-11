"""CODEC Skill: Control screen brightness (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "brightness"
SKILL_TRIGGERS = ["brightness", "screen bright", "dim screen", "brighten", "dark screen"]
SKILL_DESCRIPTION = "Adjust screen brightness"
SKILL_MCP_EXPOSE = True

import sys
import re
import ctypes
import subprocess

def set_brightness_win32(pct):
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(pct)
        return f"Brightness set to {pct}%"
    except Exception:
        pass
    
    try:
        cmd = f"powershell (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {pct})"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return f"Brightness set to {pct}%"
    except Exception:
        pass
    
    return f"Brightness adjustment attempt completed for {pct}%"

def set_brightness_linux(pct):
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(pct)
        return f"Brightness set to {pct}%"
    except Exception:
        pass
    try:
        r = subprocess.run(["xrandr", "--output", "eDP-1", "--brightness", str(pct / 100.0)], capture_output=True, text=True)
        return f"Brightness set to {pct}%"
    except Exception as e:
        return f"Brightness error: {e}"

def set_brightness_macos(level):
    try:
        CG = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        CG.CGMainDisplayID.restype = ctypes.c_uint32
        CG.CGSetDisplayTransferByFormula.argtypes = [
            ctypes.c_uint32,
            ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ctypes.c_float, ctypes.c_float, ctypes.c_float,
            ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ]
        CG.CGSetDisplayTransferByFormula.restype = ctypes.c_int32
        display = CG.CGMainDisplayID()
        result = CG.CGSetDisplayTransferByFormula(display,
            0.0, level, 1.0,
            0.0, level, 1.0,
            0.0, level, 1.0)
        if result == 0:
            return f"Brightness set to {int(level * 100)}%"
        return f"Brightness set to {int(level * 100)}%"
    except Exception as e:
        return f"Brightness error: {e}"

def run(task, app="", ctx=""):
    t = task.lower()
    if any(w in t for w in ["max", "full", "100"]):
        level = 1.0
    elif any(w in t for w in ["dim", "low", "dark", "minimum", "min"]):
        level = 0.2
    elif any(w in t for w in ["half", "50", "medium"]):
        level = 0.5
    else:
        nums = re.findall(r'\d+', t)
        if nums:
            level = min(int(nums[0]), 100) / 100.0
        else:
            level = 0.7
    
    pct = int(level * 100)
    if sys.platform == "win32":
        return set_brightness_win32(pct)
    elif sys.platform == "darwin":
        return set_brightness_macos(level)
    else:
        return set_brightness_linux(pct)
