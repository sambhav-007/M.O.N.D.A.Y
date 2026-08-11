"""Chrome Open — open URLs and new tabs (Cross-Platform Windows/Linux/macOS)"""
import sys
import os
import subprocess
import webbrowser

SKILL_NAME = "chrome_open"
SKILL_DESCRIPTION = "Open URLs and websites in Google Chrome"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = [
    "open chrome", "open url", "open website", "open page", "go to", "browse to",
    "navigate to", "open tab", "new tab", "open youtube",
    "open gmail", "open github"
]

SHORTCUTS = {
    "gmail": "https://mail.google.com",
    "calendar": "https://calendar.google.com",
    "drive": "https://drive.google.com",
    "youtube": "https://youtube.com",
    "github": "https://github.com",
    "reddit": "https://reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "google": "https://google.com",
    "docs": "https://docs.google.com",
    "sheets": "https://sheets.google.com",
    "slack": "https://app.slack.com",
    "notion": "https://notion.so",
    "linkedin": "https://linkedin.com",
    "news": "https://news.google.com",
    "maps": "https://maps.google.com",
}

def open_in_chrome_cross_platform(url):
    safe_url = url.replace('"', '').replace('\\', '').replace("'", '')
    if not safe_url.startswith(('http://', 'https://', 'file://')):
        safe_url = 'https://' + safe_url

    if sys.platform == "darwin":
        r = subprocess.run(["open", "-a", "Google Chrome", safe_url], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return f"Opened {safe_url} in Chrome."
    elif sys.platform == "win32":
        try:
            os.system(f'start chrome "{safe_url}"')
            return f"Opened {safe_url} in Chrome."
        except Exception:
            webbrowser.open(safe_url)
            return f"Opened {safe_url} in default browser."
    else:
        try:
            subprocess.run(["google-chrome", safe_url], capture_output=True, timeout=10)
            return f"Opened {safe_url} in Chrome."
        except Exception:
            webbrowser.open(safe_url)
            return f"Opened {safe_url} in browser."

    webbrowser.open(safe_url)
    return f"Opened {safe_url}."

def run(task, app="", ctx=""):
    try:
        task_lower = task.lower()
        url = ""

        for word in task.split():
            if word.startswith("http://") or word.startswith("https://"):
                url = word
                break
            if "." in word and len(word) > 4 and " " not in word:
                url = "https://" + word
                break

        if not url:
            for name, shortcut_url in SHORTCUTS.items():
                if name in task_lower:
                    url = shortcut_url
                    break

        if not url:
            return open_in_chrome_cross_platform("https://google.com")

        return open_in_chrome_cross_platform(url)
    except Exception as e:
        return f"Chrome open error: {e}"
