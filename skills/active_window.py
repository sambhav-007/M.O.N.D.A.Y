"""CODEC Skill: Return the currently focused app + window title (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "active_window"
SKILL_DESCRIPTION = "Return the frontmost app name, window title, and process/bundle id"
SKILL_TRIGGERS = [
    "active window", "frontmost app", "focused app", "what app",
    "what window", "current window", "which app is open",
    "what's on screen", "what am i looking at",
]
SKILL_MCP_EXPOSE = True

import sys
import os
import json
import subprocess

def get_active_window_win32():
    try:
        import ctypes
        import psutil
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"app": "Desktop", "bundle_id": "explorer.exe", "window_title": ""}
        
        # Get window text
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # Get process name
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = ""
        executable = ""
        if pid.value:
            try:
                proc = psutil.Process(pid.value)
                process_name = proc.name()
                executable = proc.exe()
            except Exception:
                pass
        
        return {
            "app": process_name or "Unknown",
            "bundle_id": executable or process_name,
            "window_title": title,
        }
    except Exception as e:
        return {"error": str(e)}

def get_active_window_linux():
    try:
        r = subprocess.run(["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=3)
        title = r.stdout.strip()
        r_pid = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"], capture_output=True, text=True, timeout=3)
        pid = r_pid.stdout.strip()
        app_name = "Unknown"
        if pid:
            try:
                import psutil
                proc = psutil.Process(int(pid))
                app_name = proc.name()
            except Exception:
                pass
        return {"app": app_name, "bundle_id": app_name, "window_title": title}
    except Exception as e:
        return {"error": str(e)}

def get_active_window_macos():
    _SCRIPT = '''
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set bundleId to bundle identifier of frontApp
    try
        set winName to name of front window of frontApp
    on error
        set winName to ""
    end try
end tell
return appName & "||" & bundleId & "||" & winName
'''
    try:
        r = subprocess.run(["osascript", "-e", _SCRIPT], capture_output=True, text=True, timeout=5)
        out = (r.stdout or "").strip()
        if not out:
            return {"error": r.stderr.strip() or "no output"}
        parts = out.split("||")
        while len(parts) < 3:
            parts.append("")
        return {
            "app": parts[0],
            "bundle_id": parts[1],
            "window_title": parts[2],
        }
    except Exception as e:
        return {"error": str(e)}

def run(task="", app="", ctx=""):
    if sys.platform == "win32":
        res = get_active_window_win32()
    elif sys.platform == "darwin":
        res = get_active_window_macos()
    else:
        res = get_active_window_linux()
    return json.dumps(res)
