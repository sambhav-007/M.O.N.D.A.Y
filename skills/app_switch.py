"""CODEC Skill: App Switcher (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "app_switch"
SKILL_DESCRIPTION = "Switch to any running app by name. If a URL is present, open it in the named browser."
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = ["switch to", "go to app", "focus on", "bring up", "activate app",
                   "open app", "open the app", "switch up to", "switch up",
                   "in safari", "in chrome", "in firefox", "in brave", "in edge", "in the browser",
                   "on safari", "on chrome", "on firefox", "on brave", "on edge",
                   "using safari", "using chrome", "using firefox", "using brave", "using edge",
                   "via safari", "via chrome", "via firefox", "via brave", "via edge",
                   "with safari", "with chrome", "with firefox", "with brave", "with edge",
                   "into safari", "into chrome", "into firefox", "into brave", "into edge",
                   "safari", "firefox", "brave", "edge"]

import sys
import os
import subprocess
import re
import webbrowser

ALIASES = {
    "chrome": "Google Chrome", "safari": "Safari", "firefox": "Firefox",
    "edge": "Microsoft Edge", "msedge": "Microsoft Edge",
    "terminal": "cmd.exe" if sys.platform == "win32" else "Terminal",
    "cmd": "cmd.exe", "powershell": "powershell.exe",
    "finder": "explorer.exe" if sys.platform == "win32" else "Finder",
    "explorer": "explorer.exe",
    "mail": "Mail", "whatsapp": "WhatsApp", "telegram": "Telegram",
    "slack": "Slack", "discord": "Discord", "spotify": "Spotify",
    "music": "Music", "notes": "Notes", "calendar": "Calendar",
    "photos": "Photos", "preview": "Preview", "vscode": "Code",
    "code": "Code", "notion": "Notion", "figma": "Figma",
    "teams": "Microsoft Teams", "outlook": "Outlook",
    "calculator": "calc.exe" if sys.platform == "win32" else "Calculator",
    "notepad": "notepad.exe" if sys.platform == "win32" else "TextEdit",
}

SITE_ALIASES = {
    "time magazine": "time.com",
    "time": "time.com",
    "new york times": "nytimes.com",
    "nytimes": "nytimes.com",
    "wall street journal": "wsj.com",
    "washington post": "washingtonpost.com",
    "the verge": "theverge.com",
    "techcrunch": "techcrunch.com",
    "bbc": "bbc.com",
    "cnn": "cnn.com",
}

def open_url_cross_platform(url, browser_name=""):
    try:
        if sys.platform == "darwin":
            browser_map = {"chrome": "Google Chrome", "firefox": "Firefox", "brave": "Brave Browser", "safari": "Safari"}
            b = browser_map.get(browser_name.lower(), "Safari")
            r = subprocess.run(["open", "-a", b, url], capture_output=True, timeout=5)
            if r.returncode == 0:
                return f"Opened {url} in {b}."
        elif sys.platform == "win32":
            webbrowser.open(url)
            return f"Opened {url} in browser."
        else:
            subprocess.run(["xdg-open", url], capture_output=True, timeout=5)
            return f"Opened {url}."
    except Exception:
        webbrowser.open(url)
        return f"Opened {url}."

def switch_app_cross_platform(app_name):
    try:
        if sys.platform == "win32":
            # Windows app switching / launching
            # Check if app is running and bring to front via win32gui/psutil or launch via start
            try:
                import ctypes
                user32 = ctypes.windll.user32
                import psutil
                
                app_lower = app_name.lower()
                for proc in psutil.process_iter(['pid', 'name']):
                    pname = (proc.info['name'] or '').lower()
                    if app_lower in pname or pname.startswith(app_lower):
                        # Found running process, launch/focus
                        os.system(f'start "" "{proc.info["name"]}"')
                        return f"Switched to {proc.info['name']}."
            except Exception:
                pass
            os.system(f'start "" "{app_name}"')
            return f"Opening {app_name}."
        elif sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return f"Switched to {app_name}."
            r2 = subprocess.run(["open", "-a", app_name], capture_output=True, timeout=5)
            if r2.returncode == 0:
                return f"Opening {app_name}."
        else:
            subprocess.run([app_name], capture_output=True, timeout=5)
            return f"Opening {app_name}."
    except Exception:
        pass
    return None

def run(task, app="", ctx=""):
    low = task.lower()

    url_match = re.search(r'https?://\S+', task)
    if not url_match:
        dom_match = re.search(r'\b([a-zA-Z0-9-]+\.(?:com|org|net|io|dev|ai|co|app|us|uk|fr|es|de)(?:/\S*)?)\b', task)
        if dom_match:
            url_match = dom_match
    site_url = None
    if url_match:
        site_url = url_match.group(0)
    else:
        for name in sorted(SITE_ALIASES, key=len, reverse=True):
            if re.search(r'\b' + re.escape(name) + r'\b', low):
                site_url = SITE_ALIASES[name]
                break
    if site_url:
        url = site_url if site_url.startswith("http") else "https://" + site_url
        b_name = "default"
        for name in ["chrome", "firefox", "brave", "edge", "safari"]:
            if name in low:
                b_name = name
                break
        res = open_url_cross_platform(url, b_name)
        if res:
            return res

    target = low
    for remove in ["switch to", "go to", "focus on", "bring up", "activate",
                    "show me", "open app", "open ", "please", "can you", "the", "app",
                    "hey codec", "hey codec,", "codec"]:
        target = target.replace(remove, "")
    target = target.strip()
    if not target or len(target) < 2:
        return None

    app_name = ALIASES.get(target, None)
    if not app_name:
        for alias, full in ALIASES.items():
            if alias in target or target in alias:
                app_name = full
                break
    if not app_name:
        app_name = target.title()

    res = switch_app_cross_platform(app_name)
    return res
