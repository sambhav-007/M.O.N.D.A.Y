"""
M.O.N.D.A.Y. — the optional LLM layer.

`CognitiveResponseDict.__bool__` is the part worth reading. It used to return
`True` unconditionally, so `if llm_response:` was always taken and **every
failed dispatch** was overwritten with a fabricated "🤖 Cognitive Response"
success — including when no API key was configured and nothing had been asked
of any model. It is falsy now unless an LLM actually answered.

Extracted from `core/planner.py`; re-exported there for existing imports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

class CognitiveResponseDict(dict):
    """Dict response that also stringifies nicely as a string if treated as text.

    Truthiness reports whether a real model actually answered. Callers use
    ``if llm_response:`` to decide whether to prefer the cognitive answer over
    their own fallback, so an unconfigured engine must be falsy — otherwise a
    placeholder string silently overwrites genuine agent results.
    """
    def __str__(self) -> str:
        return str(self.get("response", "")) or super().__str__()

    def __bool__(self) -> bool:
        return bool(self.get("success", True))


class TriModelCognitiveEngine:
    """
    Tri-Model Cognitive Engine: Dynamic routing matrix & generative reasoning across models:
      • Vision & Fast Voice IO: gemini-1.5-pro / gemini-2.5-flash (Google)
      • Complex OS Scripting & Deep Web Browser Automation: claude-3-5-sonnet (Anthropic)
      • Conversational Memory & Empathy: gpt-4o (OpenAI)
    """

    def __init__(self) -> None:
        self.matrix = {
            "vision_voice": "gemini-1.5-pro",
            "os_scripting_browser": "claude-3-5-sonnet",
            "memory_empathy": "gpt-4o",
        }

    def route_cognitive_request(self, prompt: str, intent: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Routes prompt to optimal cognitive engine model based on intent matrix."""
        p_lower = prompt.lower()
        if any(k in p_lower for k in ["screen", "visual", "look", "image", "voice", "speech"]):
            selected_model = self.matrix["vision_voice"]
            provider = "Google Generative AI"
        elif any(k in p_lower for k in ["script", "code", "browser", "automation", "scrape", "deep research"]):
            selected_model = self.matrix["os_scripting_browser"]
            provider = "Anthropic Claude"
        else:
            selected_model = self.matrix["memory_empathy"]
            provider = "OpenAI"

        return {
            "selected_model": selected_model,
            "provider": provider,
            "intent": intent,
            "prompt": prompt,
            "status": "routed",
        }

    def generate_cognitive_response(
        self,
        prompt: str,
        context_memories: Optional[List[Dict[str, Any]]] = None,
        retrieved_memories: Optional[List[Any]] = None,
        boot_context: Optional[Dict[str, Any]] = None,
    ) -> CognitiveResponseDict:
        """Queries generative Gemini API endpoint or cognitive engine for zero-shot reasoning."""
        from agents.vision_agent import load_gemini_api_key
        api_key = load_gemini_api_key()

        memories = retrieved_memories or context_memories or []
        mem_context_str = ""
        if memories:
            mem_items = []
            for m in memories:
                if isinstance(m, dict):
                    mem_items.append(f"• {m.get('key', 'info')}: {m.get('value', m)}")
                else:
                    mem_items.append(f"• {m}")
            mem_context_str = "\nRelevant User Memory Context:\n" + "\n".join(mem_items)

        resp_text = None
        if api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            sys_prompt = f"You are M.O.N.D.A.Y., an advanced autonomous desktop AI assistant.{mem_context_str}\nUser Query: '{prompt}'"
            payload = {"contents": [{"parts": [{"text": sys_prompt}]}]}

            try:
                import json, urllib.request
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts:
                            resp_text = parts[0].get("text", "").strip()
            except Exception:
                pass

        # No key, or the call failed/returned nothing. Say so — do NOT emit a
        # placeholder that reads like an answer, and do not report success.
        llm_backed = bool(resp_text)
        if not resp_text:
            reason = "no Gemini API key is configured" if not api_key else "the model call failed"
            resp_text = (
                f"I can't reason freeform about '{prompt}' because {reason}. "
                "Set GEMINI_API_KEY to enable the cognitive engine."
            )

        return CognitiveResponseDict({
            "response": resp_text,
            "cognitive_engine_active": True,
            "llm_backed": llm_backed,
            "selected_model": getattr(self, "selected_model", "gemini-1.5-flash"),
            "success": llm_backed,
        })
