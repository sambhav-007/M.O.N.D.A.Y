"""
M.O.N.D.A.Y. — Real Multimodal Screen Vision Agent
===================================================
Provides real-time screen awareness by capturing active desktop screenshots,
converting to Base64 payloads, and evaluating visual content via Multimodal
Gemini 1.5/2.5 Flash Vision API or active window inspection.
"""

from __future__ import annotations

import os
import sys
import json
import base64
import ctypes
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from core.contracts import AgentResult, FileRead, FileWritten, HttpResponse
from core.security import log_action

try:
    from PIL import Image, ImageGrab, ImageStat
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def load_gemini_api_key() -> Optional[str]:
    """Dynamically locates and loads GEMINI_API_KEY from environment or .env files."""
    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"]:
        val = os.environ.get(k)
        if val and len(val.strip()) > 10:
            return val.strip()

    # Search project directories for .env files
    possible_env_files = [
        Path(".env"),
        Path("../.env"),
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path("c:/Users/Siddhant/Desktop/PROJECT_MONDAY/.env"),
        Path("c:/Users/Siddhant/Desktop/PROJECT_MONDAY/monday-site/.env"),
        Path("c:/Users/Siddhant/Desktop/PROJECT_MONDAY/M.O.N.D.A.Y/.env"),
    ]

    for env_path in possible_env_files:
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                            key_val = line.split("=", 1)[1].strip('"\'')
                            if key_val and len(key_val) > 10:
                                os.environ["GEMINI_API_KEY"] = key_val
                                return key_val
            except Exception:
                pass
    return None


class VisionAgent:
    """Real Multimodal Computer Vision & Screen Awareness Agent."""

    def __init__(self) -> None:
        self.name = "VisionAgent"
        self.api_key = load_gemini_api_key()

    def get_active_window_title(self) -> str:
        """Retrieves the title of the currently active foreground window on OS."""
        if sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                if buff.value:
                    return buff.value
            except Exception:
                pass
            try:
                ps_cmd = "(Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -First 1).MainWindowTitle"
                res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True, timeout=3)
                if res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        return "M.O.N.D.A.Y. Console Active Window"

    def capture_active_screen(self) -> Dict[str, Any]:
        """Captures screenshot of active screen and saves to scratch directory."""
        if not PIL_AVAILABLE:
            return AgentResult.not_configured(
                "Screen capture", needs="the Pillow package"
            ).as_dict()

        try:
            try:
                screenshot = ImageGrab.grab()
            except Exception as grab_err:
                # This used to fall back to `Image.new("RGB", (1920, 1080),
                # color=(15, 15, 25))` — a blank dark rectangle — and then report
                # "✓ Screen captured (1920x1080)" and hand its base64 to the
                # vision analyser. Every downstream answer about "what's on my
                # screen" would then describe an image that was never on it.
                return AgentResult.failed(
                    f"I couldn't capture the screen: {grab_err}",
                    error="SCREEN_CAPTURE_FAILED",
                ).as_dict()

            out_dir = Path("data") / "scratch"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "active_screen.png"
            screenshot.save(out_path, format="PNG")

            # Convert screenshot to Base64
            with open(out_path, "rb") as f:
                base64_data = base64.b64encode(f.read()).decode("utf-8")

            log_action("capture_screen", str(out_path), 1, "success", self.name)
            return AgentResult.ok(
                f"✓ Screen captured ({screenshot.width}x{screenshot.height}).",
                evidence=FileWritten(
                    path=str(out_path), bytes_written=out_path.stat().st_size
                ),
                data={
                    "path": str(out_path),
                    "width": screenshot.width,
                    "height": screenshot.height,
                    "base64": base64_data,
                },
            ).as_dict()
        except Exception as e:
            return AgentResult.failed(
                f"Screen capture failed: {e}", error="SCREEN_CAPTURE_FAILED"
            ).as_dict()

    def _query_multimodal_api(self, prompt: str, base64_img: str) -> Optional[str]:
        """
        Sends Base64 screenshot payload and user prompt to real Multimodal Gemini Vision API endpoint.
        """
        api_key = self.api_key or load_gemini_api_key()
        if not api_key:
            return None

        # Call Gemini 1.5 Flash Vision REST API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": f"You are M.O.N.D.A.Y. Multimodal Vision Engine. Examine this active screen screenshot image and answer the user query in detail: '{prompt}'"},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64_img
                        }
                    }
                ]
            }]
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts:
                        return parts[0].get("text")
        except Exception:
            pass
        return None

    def analyze_screen_context(self, user_query: str) -> Dict[str, Any]:
        """
        Captures active screen, encodes Base64 payload, inspects active window,
        and returns live Multimodal Gemini Vision API analysis.
        """
        capture_res = self.capture_active_screen()
        if not capture_res.get("success"):
            return capture_res

        screen_path = capture_res.get("path")
        base64_img = capture_res.get("base64", "")
        width = capture_res.get("width", 1920)
        height = capture_res.get("height", 1080)
        win_title = self.get_active_window_title()

        # Step 1: Query Real Multimodal Gemini Vision API Endpoint
        api_response = self._query_multimodal_api(user_query, base64_img)
        if api_response:
            msg = f"✓ Screen Vision Analysis (Gemini Multimodal) for '{user_query}':\n  • Active Foreground Window: \"{win_title}\"\n  • Analysis: {api_response.strip()}"
            log_action("analyze_screen_context", user_query, 1, "success", self.name, {"image": screen_path, "mode": "gemini_multimodal_vision"})
            return AgentResult.ok(
                msg,
                evidence=HttpResponse(
                    status=200,
                    url="generativelanguage.googleapis.com/gemini-1.5-flash",
                ),
                data={
                    "query": user_query,
                    "image_path": screen_path,
                    "multimodal_llm": True,
                },
            ).as_dict()

        # Step 2: no vision model — report what can actually be observed.
        #
        # This branch used to be headed "✓ Screen Vision Analysis" and end with
        # "Visual Inspection: Onscreen content identified under active title",
        # having identified no content whatsoever. It reads the window title from
        # the OS and computes mean pixel brightness; nothing looks at what is on
        # the screen. Asked "what's the error on my screen", it answered with a
        # luminance figure dressed as an analysis. Without a Gemini key there is
        # no vision here, and saying so is more useful than a confident
        # non-answer.
        try:
            img = Image.open(screen_path)
            stat = ImageStat.Stat(img)
            brightness = sum(stat.mean) / len(stat.mean)
            aspect_ratio = round(width / height, 2)
            detail = (
                f"  • Active window title: \"{win_title}\"\n"
                f"  • Dimensions: {width}x{height} (aspect {aspect_ratio})\n"
                f"  • Mean brightness: {brightness:.1f}/255"
            )
        except Exception:
            detail = f"  • Active window title: \"{win_title}\" ({width}x{height})"

        vision_desc = (
            f"I captured the screen but can't read what's on it — that needs a "
            f"Gemini API key (GEMINI_API_KEY in .env). Here's what I can tell you "
            f"about it:\n{detail}\n"
            f"  • Saved to: {screen_path}"
        )

        log_action("analyze_screen_context", user_query, 1, "partial", self.name, {"image": screen_path, "mode": "active_window_only"})
        return AgentResult.ok(
            vision_desc,
            evidence=FileRead(path=str(screen_path), bytes_read=len(base64_img)),
            data={
                "query": user_query,
                "image_path": screen_path,
                "active_window": win_title,
                "vision_model_used": False,
            },
        ).as_dict()
