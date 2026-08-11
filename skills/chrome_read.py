"""Chrome Read — extract and read current page content (Cross-Platform Windows/Linux/macOS)"""
import sys
import subprocess
import asyncio
import requests

SKILL_NAME = "chrome_read"
SKILL_DESCRIPTION = "Read and extract text content from the current Chrome tab"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = [
    "read this page", "read page", "what's on this page", "whats on this page",
    "read the page", "page content", "extract page", "read website",
    "read this site", "summarize page", "summarize this page", "what does this page say"
]

def read_via_cdp():
    try:
        from codec_cdp import ChromeCDP
        async def _read():
            cdp = ChromeCDP()
            await cdp.connect(0)
            title = await cdp.get_title()
            url = await cdp.get_url()
            text = await cdp.get_page_text(5000)
            await cdp.close()
            return f"📄 **{title}**\n{url}\n\n{text}"
        return asyncio.run(_read())
    except Exception:
        return None

def run(task, app="", ctx=""):
    try:
        if sys.platform == "darwin":
            info_script = '''
tell application "Google Chrome"
    set pageTitle to title of active tab of front window
    set pageURL to URL of active tab of front window
    return pageTitle & "|SPLIT|" & pageURL
end tell
'''
            info = subprocess.run(["osascript", "-e", info_script], capture_output=True, text=True, timeout=5)
            if info.returncode == 0 and "|SPLIT|" in info.stdout:
                parts = info.stdout.strip().split("|SPLIT|")
                title = parts[0]
                url = parts[1] if len(parts) > 1 else ""

                js_code = "(function(){var b=document.body;if(!b)return 'No content found';var c=b.cloneNode(true);var r=c.querySelectorAll('script,style,nav,footer,header,.nav,.footer,.header,.sidebar,.menu,.ad,.ads,.advertisement');for(var i=0;i<r.length;i++)r[i].remove();var t=c.innerText||c.textContent||'';return t.substring(0,8000);})()"
                js_script = f'''tell application "Google Chrome"
                    set pageText to execute active tab of front window javascript "{js_code}"
                    return pageText
                end tell'''
                r = subprocess.run(["osascript", "-e", js_script], capture_output=True, text=True, timeout=15)
                if r.returncode == 0 and r.stdout.strip():
                    return f"📄 **{title}**\n{url}\n\n{r.stdout.strip()[:5000]}"

        # Cross-platform fallback via CDP
        cdp_res = read_via_cdp()
        if cdp_res:
            return cdp_res

        return "Could not extract page content. Chrome CDP debug port (9222) or Chrome window active tab required."
    except Exception as e:
        return f"Chrome read error: {e}"
