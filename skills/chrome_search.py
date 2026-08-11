"""Chrome Search — search Google (Cross-Platform Windows/Linux/macOS)"""
import urllib.parse
from skills.chrome_open import open_in_chrome_cross_platform

SKILL_NAME = "chrome_search"
SKILL_DESCRIPTION = "Search Google in Chrome for any query"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = [
    "search google", "google search", "look up", "google for",
    "find online", "search online"
]

def run(task, app="", ctx=""):
    try:
        task_lower = task.lower()
        query = task
        triggers_sorted = sorted([
            "search google for", "google search for", "search for", "look up",
            "google for", "search the web for", "web search for", "find online",
            "search online for", "search google", "google search", "search the web",
            "web search", "search online"
        ], key=len, reverse=True)

        for trigger in triggers_sorted:
            if trigger in task_lower:
                idx = task_lower.index(trigger) + len(trigger)
                query = task[idx:].strip()
                break

        if not query or len(query) < 2:
            return "What would you like me to search for?"

        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}"

        open_in_chrome_cross_platform(url)
        return f"Searching Google for: {query}"
    except Exception as e:
        return f"Chrome search error: {e}"
