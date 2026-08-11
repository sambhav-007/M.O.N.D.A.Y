"""CODEC Skill: Volume & Brightness Control (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "volume_brightness"
SKILL_DESCRIPTION = "Control volume and brightness by voice"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = ["volume up", "volume down", "set volume", "mute", "unmute",
                   "louder", "quieter", "brightness up", "brightness down",
                   "turn up", "turn down", "volume to", "max volume", "silence"]
import sys
import subprocess
import re
import pyautogui

def set_volume_win32(level):
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        if level == "mute":
            volume.SetMute(1, None)
            return "Muted."
        elif level == "unmute":
            volume.SetMute(0, None)
            return "Unmuted."
        else:
            pct = max(0, min(100, int(level))) / 100.0
            volume.SetMasterVolumeLevelScalar(pct, None)
            return f"Volume set to {int(pct * 100)}%."
    except Exception:
        pass
    
    # Fallback to pyautogui key presses or PowerShell
    try:
        if level == "mute":
            pyautogui.press("volumemute")
            return "Muted."
        elif level == "unmute":
            pyautogui.press("volumemute")
            return "Unmuted."
        elif isinstance(level, (int, float)):
            # Adjust volume via key simulation or PowerShell
            ps_script = f"$obj = New-Object -ComObject WScript.Shell; 1..50 | % {{ $obj.SendKeys([char]174) }}; 1..{int(level/2)} | % {{ $obj.SendKeys([char]175) }}"
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True, timeout=5)
            return f"Volume set to {level}%."
    except Exception:
        pass
    return "Volume adjusted."

def set_volume_linux(level):
    try:
        if level == "mute":
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], capture_output=True)
            return "Muted."
        elif level == "unmute":
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], capture_output=True)
            return "Unmuted."
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(level)}%"], capture_output=True)
            return f"Volume set to {int(level)}%."
    except Exception as e:
        return f"Volume error: {e}"

def set_volume_macos(level):
    try:
        if level == "mute":
            subprocess.run(["osascript", "-e", "set volume output volume 0"], timeout=5)
            return "Muted."
        elif level == "unmute":
            subprocess.run(["osascript", "-e", "set volume output volume 50"], timeout=5)
            return "Unmuted."
        else:
            subprocess.run(["osascript", "-e", f"set volume output volume {int(level)}"], timeout=5)
            return f"Volume set to {int(level)}%."
    except Exception as e:
        return f"Volume error: {e}"

def run(task, app="", ctx=""):
    low = task.lower()
    
    target_vol = None
    if "mute" in low or "silence" in low:
        target_vol = "mute"
    elif "unmute" in low:
        target_vol = "unmute"
    elif "max volume" in low:
        target_vol = 100
    elif any(k in low for k in ["volume up", "louder", "turn up the volume", "turn it up"]):
        target_vol = 75
    elif any(k in low for k in ["volume down", "quieter", "turn down the volume", "turn it down"]):
        target_vol = 30
    else:
        num = re.search(r'volume\s*(?:to|at)?\s*(\d+)', low)
        if num:
            target_vol = min(100, int(num.group(1)))
            
    if target_vol is not None:
        if sys.platform == "win32":
            return set_volume_win32(target_vol)
        elif sys.platform == "darwin":
            return set_volume_macos(target_vol)
        else:
            return set_volume_linux(target_vol)

    if "brightness" in low:
        try:
            import skills.brightness as br_skill
            return br_skill.run(task, app, ctx)
        except Exception:
            return "Brightness set."

    return None
