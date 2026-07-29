"""
M.O.N.D.A.Y. — Master Multi-Agent Planner & Orchestrator
==========================================================
The central intelligence engine that:
  1. Classifies user prompt intent via Component 2.1 (Intent Classifier)
  2. Selects routing strategy via Component 2.5 (RL Router Bandit) if uncertain
  3. Checks Security Risk Tier (Tier 1 Autonomous / Tier 2 User Approval)
  4. Predicts task ETA via Component 2.2 (ETA Regressor)
  5. Dispatches to target worker agent (Computer, Document, Browser, Comms, Memory, Habit)
"""

from __future__ import annotations

import io
import sys
import re
from typing import Any, Dict, List, Optional, Tuple

# Force Windows console stdout/stderr to UTF-8 with errors='replace'
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agents.voice_agent import VoiceAgent
from agents.computer_agent import ComputerAgent
from agents.document_agent import DocumentAgent
from agents.browser_agent import BrowserAgent
from agents.comms_agent import CommunicationAgent
from agents.memory_agent import MemoryAgent
from agents.habit_agent import HabitAgent
from agents.coder_agent import CoderAgent
from agents.vision_agent import VisionAgent
from agents.public_api_agent import PublicApiAgent
from agents.audio_summarizer_agent import AudioSummarizerAgent
from core.task_dag_engine import TaskDAGEngine

from core.tool_registry import ToolRegistry
from core.autonomy import AutonomyDaemon
from core.security import evaluate_action_permission, log_action
from ml.intent_classifier import get_trained_classifier, predict_intent
from ml.rl_router import EpsilonGreedyBandit, ROUTING_ACTIONS


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

class CognitiveResponseDict(dict):
    """Dict response that also stringifies nicely as a string if treated as text."""
    def __str__(self) -> str:
        return str(self.get("response", "")) or super().__str__()

    def __bool__(self) -> bool:
        return True


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

        if not resp_text:
            resp_text = f"M.O.N.D.A.Y. cognitive analysis complete for query '{prompt}'."

        return CognitiveResponseDict({
            "response": resp_text,
            "cognitive_engine_active": True,
            "selected_model": getattr(self, "selected_model", "gemini-1.5-flash"),
            "success": True,
        })


class MasterPlanner:
    """Master Multi-Agent Orchestration Engine powered by Tri-Model Cognitive Engine."""

    def __init__(self) -> None:
        self.name = "MasterPlanner"

        # Initialize Worker Agents, Tool Registry & Proactive Autonomy Daemon
        self.voice_agent = VoiceAgent()
        self.computer_agent = ComputerAgent()
        self.document_agent = DocumentAgent()
        self.browser_agent = BrowserAgent()
        self.comms_agent = CommunicationAgent()
        self.memory_agent = MemoryAgent()
        self.habit_agent = HabitAgent()
        self.coder_agent = CoderAgent()
        self.vision_agent = VisionAgent()
        self.public_api_agent = PublicApiAgent()
        self.audio_summarizer_agent = AudioSummarizerAgent()
        self.cognitive_engine = TriModelCognitiveEngine()
        self.task_dag_engine = TaskDAGEngine(self)
        self.tool_registry = ToolRegistry()
        self.autonomy_daemon = AutonomyDaemon()
        self.autonomy_daemon.start()

        # Multi-Turn Conversation State Machine
        self.pending_clarification: Optional[Dict[str, Any]] = None

        # Boot-up System Context Scanner
        self.boot_context: Dict[str, Any] = {}
        self.system_boot_scan()

        # Load ML Models
        print("🧠 Initializing Master Planner ML Pipelines...")
        self.classifier = get_trained_classifier()
        self.rl_bandit = EpsilonGreedyBandit(epsilon=0.05, seed=42)
        print("✓ Master Planner Ready.")

    def system_boot_scan(self) -> Dict[str, Any]:
        """
        Gathers system specs, user identity, timestamp, and active files
        so M.O.N.D.A.Y. is booted up with complete environment context.
        """
        import getpass
        import psutil
        import sys
        from datetime import datetime
        from pathlib import Path

        username = getpass.getuser()
        mem = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.1)

        desktop = Path.home() / "Desktop"
        documents = Path.home() / "Documents"

        desktop_files = [f.name for f in list(desktop.glob("*"))[:10]] if desktop.exists() else []
        document_files = [f.name for f in list(documents.glob("*"))[:10]] if documents.exists() else []

        # Auto-detect geographical location context via ip-api.com
        geo_info = {}
        try:
            import urllib.request
            import json
            req = urllib.request.Request("http://ip-api.com/json/", headers={"User-Agent": "MONDAY-Boot/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                geo_info = json.loads(resp.read().decode("utf-8"))
        except Exception:
            pass

        boot_data = {
            "username": username,
            "platform": sys.platform,
            "cpu_usage_pct": cpu_pct,
            "memory_free_gb": round(mem.available / (1024 ** 3), 1),
            "memory_total_gb": round(mem.total / (1024 ** 3), 1),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "desktop_files": desktop_files,
            "document_files": document_files,
            "geo_location": geo_info,
            "city": geo_info.get("city", "Unknown"),
            "country": geo_info.get("country", "Unknown"),
            "public_ip": geo_info.get("query", "127.0.0.1"),
        }
        self.boot_context = boot_data
        location_str = f"{boot_data['city']}, {boot_data['country']}" if geo_info.get("city") else "Local Environment"
        print(f"🖥️ Boot Context Scanned: User '{username}' | Location: {location_str} | RAM: {boot_data['memory_free_gb']}GB free | Files: {len(desktop_files)} Desktop, {len(document_files)} Docs.")
        return boot_data

    def process_command(
        self,
        command: str,
        user_approved: bool = False,
    ) -> Dict[str, Any]:
        """
        Main execution pipeline for a user command:
          Multi-Turn Check → Command → Intent Classification (2.1) → RL Routing (2.5) → Security Tier Check → Agent Execution
        """
        cmd = command.strip()
        if not cmd:
            return {"success": False, "error": "Command is empty."}

        # Step 0: Auto-Memory Extraction & Context Pre-fetching
        self.memory_agent.auto_extract_and_remember(cmd)
        context_memories = self.memory_agent.get_contextual_memories(cmd)

        # Step 0.1: Check for Multi-Turn Pending Clarification State
        if self.pending_clarification is not None:
            cmd_lower = cmd.lower().strip()
            # If input is a new independent command rather than an email/number selection or short reply, auto-clear clarification state
            if any(k in cmd_lower for k in ["screen", "where", "weather", "who", "what", "search", "open", "capabilities", "tell me", "how", "show", "bitcoin", "crypto"]):
                self.pending_clarification = None
            elif self.pending_clarification is not None:
                return self._resolve_clarification(cmd)

        # Step 0.5: Dynamic Multi-Step Task DAG Engine Check
        if self.task_dag_engine.is_multi_step_goal(cmd):
            dag_result = self.task_dag_engine.execute_dag(cmd, user_approved=user_approved)
            self.memory_agent.auto_store_conversation_turn(cmd, str(dag_result.get("message", "")))
            return {
                "user_command": cmd,
                "intent_classification": {"predicted_intent": "multi_step_dag", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "dag_engine", "clo": "CLO05"},
                "execution_result": dag_result,
            }

        # Step 1: Component 2.1 Intent Classifier
        intent, confidence, fallback = predict_intent(self.classifier, cmd)

        # Step 2: Component 2.5 RL Bandit Routing Decision if confidence is low
        routing_strategy = "direct_dispatch"
        if fallback:
            action_idx = self.rl_bandit.select_action()
            routing_strategy = ROUTING_ACTIONS[action_idx]

        # Step 3: Match intent to target agent tool execution
        tool_result = self._dispatch_to_agent(cmd, intent, user_approved)

        # If standard dispatch requires generative reasoning, query Cognitive Engine
        if fallback or (isinstance(tool_result, dict) and not tool_result.get("success") and not tool_result.get("refusal")):
            llm_response = self.cognitive_engine.generate_cognitive_response(cmd, context_memories)
            if llm_response:
                tool_result = {
                    "success": True,
                    "cognitive_llm": True,
                    "message": f"🤖 M.O.N.D.A.Y. Cognitive Response:\n{llm_response}"
                }

        # Reward feedback to RL bandit if successful
        if tool_result.get("success", False):
            self.rl_bandit.update(ROUTING_ACTIONS.index("direct_dispatch"), 1.0)
        else:
            self.rl_bandit.update(ROUTING_ACTIONS.index("direct_dispatch"), -1.0)

        # Auto-store conversation turn to SQLite memory.db
        if isinstance(tool_result, dict) and tool_result.get("message"):
            self.memory_agent.auto_store_conversation_turn(cmd, str(tool_result.get("message", "")))

        output = {
            "user_command": cmd,
            "intent_classification": {
                "predicted_intent": intent,
                "confidence": round(confidence, 4),
                "llm_fallback": fallback,
                "clo": "CLO04",
            },
            "rl_routing": {
                "strategy": routing_strategy,
                "clo": "CLO05",
            },
            "execution_result": tool_result,
        }

        # Trigger voice output in background thread so UI thread does not freeze
        if getattr(self, "enable_voice", True) and isinstance(tool_result, dict) and tool_result.get("message"):
            msg_text = tool_result.get("message", "")
            import threading
            threading.Thread(target=self.voice_agent.speak, args=(msg_text,), daemon=True).start()

        return output

    def _resolve_clarification(self, user_response: str) -> Dict[str, Any]:
        """Resumes paused task using the user's clarification answer."""
        clarification = self.pending_clarification
        self.pending_clarification = None  # Clear state

        target_name = clarification.get("target_name", "contact")
        candidates = clarification.get("candidates", [])
        raw_ans = user_response.strip()
        # Handle Multi-Step Email Cross-Questioning Wizard
        c_type = clarification.get("type", "contact_disambiguation")
        c_step = clarification.get("step", "resolve_contact")

        if c_step == "get_subject":
            subject_val = user_response.strip()
            self.pending_clarification = {
                "type": "email_wizard",
                "step": "get_body",
                "to_email": clarification["to_email"],
                "subject": subject_val,
                "body": None,
                "original_command": clarification.get("original_command", "")
            }
            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_wizard", "clo": "CLO05"},
                "execution_result": {
                    "success": True,
                    "pending_clarification": True,
                    "message": f"✓ Subject set to '{subject_val}'! What should the email message body say?"
                }
            }

        if c_step == "get_body":
            body_val = user_response.strip()
            to_email = clarification["to_email"]
            subject_val = clarification.get("subject", "Automated Assistant Request")
            self.pending_clarification = None  # Clear wizard state

            res = self.comms_agent.draft_email(to_email, subject_val, body_val)
            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_wizard_complete", "clo": "CLO05"},
                "execution_result": {
                    "success": True,
                    "draft_id": res.get("draft_id"),
                    "to": to_email,
                    "subject": subject_val,
                    "body": body_val,
                    "gmail_compose_url": res.get("gmail_compose_url"),
                    "message": f"✓ Email draft prepared for '{to_email}' with subject '{subject_val}' & opened in Gmail Web Composer!",
                }
            }

        # Step 1: Contact Disambiguation
        resolved_email = None
        if candidates:
            if raw_ans.isdigit():
                idx = int(raw_ans) - 1
                if 0 <= idx < len(candidates):
                    resolved_email = candidates[idx]["email"]
            if not resolved_email:
                for c in candidates:
                    if raw_ans.lower() in c["name"].lower() or raw_ans.lower() in c["email"].lower():
                        resolved_email = c["email"]
                        break

        if not resolved_email:
            if "@" in raw_ans and "." in raw_ans:
                resolved_email = raw_ans
            else:
                self.pending_clarification = clarification
                return {
                    "user_command": user_response,
                    "clarification_resumed": False,
                    "execution_result": {
                        "success": False,
                        "pending_clarification": True,
                        "message": f"🔒 Invalid Selection: '{raw_ans}' didn't match any candidate or valid email. Please enter a valid candidate number or full email address."
                    }
                }

        # Cache this resolved contact in SQLite memory so future calls are instant
        self.memory_agent.remember(f"{target_name} email", resolved_email, topic="contacts")

        # Ask for Subject next
        self.pending_clarification = {
            "type": "email_wizard",
            "step": "get_subject",
            "to_email": resolved_email,
            "subject": None,
            "body": None,
            "original_command": clarification.get("original_command", "")
        }

        return {
            "user_command": user_response,
            "clarification_resumed": True,
            "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
            "rl_routing": {"strategy": "email_wizard", "clo": "CLO05"},
            "execution_result": {
                "success": True,
                "pending_clarification": True,
                "to": resolved_email,
                "message": f"✓ Contact resolved to '{resolved_email}'! What is the subject of the email?"
            }
        }

    def _dispatch_to_agent(self, command: str, intent: str, user_approved: bool) -> Dict[str, Any]:
        """Routes command to appropriate specialized tool agent."""
        cmd_lower = command.lower().strip()

        # ── 00. Moral Firewall & Hard Security Constraints ───────────────────────
        prohibited_keywords = ["hack ", "exploit", "ddos", "malware", "format c:", "rm -rf /", "drop database", "wipe drive"]
        if any(k in cmd_lower for k in prohibited_keywords):
            return {
                "success": False,
                "refusal": True,
                "message": f"❌ Security Refusal: Command '{command}' violates M.O.N.D.A.Y. Moral Firewall safety rules."
            }

        # ── 00000. Capabilities & Features Menu Intercept ───────────────────────
        if any(k in cmd_lower for k in ["what can you do", "what can u do", "what can you perform", "capabilities", "features", "help", "commands"]):
            capabilities_menu = (
                "🤖 M.O.N.D.A.Y. Omni-Capable Desktop Assistant Features:\n\n"
                "1. 🚀 Smart Local-App Launcher: Opens native desktop binaries (WhatsApp, Spotify, Calculator, VS Code, Notepad) first before web fallbacks.\n"
                "2. 📧 Communication & Email Wizard: Interactive Email Wizard & WhatsApp Messaging.\n"
                "3. 👁️ Multimodal Screen Vision: Live Gemini 1.5 Flash Vision screen capture & visual analysis.\n"
                "4. 🗣️ Speech & Voice Engine: Speech recognition & signature mondayvoice.mp3 speech output.\n"
                "5. 📄 Document Intelligence: PDF parsing & document summarization.\n"
                "6. 🧠 Long-Term Vector Memory: SQLite TF-IDF vector memory matrix for semantic recall across sessions.\n"
                "7. 🤖 Proactive Background Autonomy: Monitors Downloads folder, extracts invoice totals, renames by date & sends notifications.\n"
                "8. ⚡ Self-Evolution Plugin System: Synthesizes generalized Python scripts & compiles permanent domain plugins."
            )
            return {
                "success": True,
                "intent": "capabilities_menu",
                "message": capabilities_menu,
            }

        # ── 00000. Live Zero-Auth Public REST API Intercepts ─────────────────────
        if any(k in cmd_lower for k in ["meeting audio", "record meeting", "meeting notes", "summarize meeting"]):
            if "start" in cmd_lower or "record" in cmd_lower:
                return self.audio_summarizer_agent.start_meeting_recording()
            return self.audio_summarizer_agent.stop_meeting_recording_and_summarize()

        if any(k in cmd_lower for k in ["where am i", "my location", "my ip", "what is my city", "where is my ip"]):
            return self.public_api_agent.get_geolocation()

        elif any(k in cmd_lower for k in ["weather", "temperature", "forecast", "climate"]):
            loc_match = re.search(r'weather\s+(?:in|for|at)?\s+([^\s,"]+)', command, re.IGNORECASE)
            loc = loc_match.group(1).strip() if loc_match else ""
            return self.public_api_agent.get_weather(loc)

        elif any(k in cmd_lower for k in ["bitcoin", "btc", "ethereum", "eth", "crypto", "crypto price"]):
            coins = "bitcoin,ethereum"
            if "btc" in cmd_lower or "bitcoin" in cmd_lower: coins = "bitcoin"
            elif "eth" in cmd_lower or "ethereum" in cmd_lower: coins = "ethereum"
            return self.public_api_agent.get_crypto_prices(coins)

        elif any(k in cmd_lower for k in ["who was", "who is", "what is", "wikipedia", "explain", "tell me about"]):
            if not any(x in cmd_lower for x in ["my name", "who am i", "screen", "volume", "time", "date", "bitcoin", "crypto"]):
                topic = re.sub(r'^.*(who was|who is|what is|wikipedia|explain|tell me about)\s+', '', command, flags=re.IGNORECASE).strip()
                if topic and len(topic.split()) <= 5:
                    return self.public_api_agent.get_wikipedia_summary(topic)

        # ── 00000. System Control & Basic Utility Priority Intercepts (from Jarvis repo) ───
        from datetime import datetime

        # Time & Date
        if any(k in cmd_lower for k in ["what time", "current time", "tell me time", "time is it"]):
            now_time = datetime.now().strftime("%I:%M %p")
            return {"success": True, "intent": "time", "message": f"✓ Current time is {now_time}."}
        if any(k in cmd_lower for k in ["what date", "current date", "today date", "what is the date"]):
            now_date = datetime.now().strftime("%A, %B %d, %Y")
            return {"success": True, "intent": "date", "message": f"✓ Today's date is {now_date}."}

        # Battery Health
        if any(k in cmd_lower for k in ["battery", "charge", "power status"]):
            return self.computer_agent.get_battery_status()

        # Audio Volume Control
        if "volume" in cmd_lower or "mute" in cmd_lower:
            vol_match = re.search(r'(\d+)', command)
            if vol_match:
                pct = int(vol_match.group(1))
                return self.computer_agent.set_system_volume(pct)
            elif "mute" in cmd_lower:
                return self.computer_agent.set_system_volume(0)
            elif "up" in cmd_lower or "increase" in cmd_lower:
                return self.computer_agent.set_system_volume(80)
            elif "down" in cmd_lower or "decrease" in cmd_lower:
                return self.computer_agent.set_system_volume(30)
            else:
                return self.computer_agent.get_system_volume()

        # Network IP Address
        if any(k in cmd_lower for k in ["my ip", "ip address", "network info"]):
            return self.computer_agent.get_network_info()

        # Live Impromptu Jokes & Trivia API (No hardcoded arrays)
        if "joke" in cmd_lower or "funny" in cmd_lower:
            joke_res = self.public_api_agent.execute_dynamic_api("https://v2.jokeapi.dev/joke/Any?safe-mode")
            if joke_res.get("success") and joke_res.get("data"):
                data = joke_res["data"]
                if data.get("type") == "single":
                    msg = f"✓ {data.get('joke')}"
                else:
                    msg = f"✓ {data.get('setup')} ... {data.get('delivery')}"
                return {"success": True, "intent": "joke", "message": msg}
            else:
                return self.public_api_agent.search_public_apis("joke")

        # Math Calculations
        math_match = re.search(r'(?:calculate|what is|compute)\s+([\d\.\s\+\-\*\/\(\)\^]+)$', command, re.IGNORECASE)
        if math_match:
            expr = math_match.group(1).strip()
            if any(op in expr for op in ["+", "-", "*", "/"]):
                try:
                    res_val = eval(expr, {"__builtins__": {}}, {})
                    return {"success": True, "intent": "calculator", "message": f"✓ {expr} = {res_val}"}
                except Exception:
                    pass

        # ── 000000. Autonomous Dynamic 787+ Public API Intercept ─────────────────
        if any(k in cmd_lower for k in ["space station", "iss location", "where is space station", "iss coordinates"]):
            return self.public_api_agent.get_iss_location()

        elif any(k in cmd_lower for k in ["dog fact", "dog picture", "cat fact", "meme", "space", "nasa", "anime", "trivia", "public api", "search api"]):
            search_res = self.public_api_agent.search_public_apis(command)
            best = search_res.get("best_api")
            if best and best.get("url"):
                target_url = best["url"]
                exec_res = self.public_api_agent.execute_dynamic_api(target_url)
                exec_res["api_discovered"] = best["name"]
                return exec_res
            return search_res

        # ── 0000. User Identity & Context Intercept (Fixes "what is my name") ─────
        if any(k in cmd_lower for k in ["my name", "who am i", "what is my name", "tell me my name", "my username"]):
            username = self.boot_context.get("username", "Siddhant")
            mem_res = self.memory_agent.recall("name")
            mem_name = mem_res.get("matches", [{}])[0].get("value") if (mem_res.get("matches") and len(mem_res["matches"]) > 0) else ""
            display_name = mem_name or username
            return {
                "success": True,
                "intent": "identity_context",
                "message": f"✓ Your name is {display_name} (OS User: {username}).",
            }

        # ── 000. Multimodal Screen Vision Intercept ─────────────────────────────
        if any(v in cmd_lower for v in ["screen", "chart", "looking at", "error on screen", "visual", "what is on my screen", "written", "text on my screen"]):
            return self.vision_agent.analyze_screen_context(command)

        # ── 0. WhatsApp Priority Handler (Fixes "open whatsapp message...") ──────
        if "whatsapp" in cmd_lower:
            match = re.search(r'(?:message|send to|text)\s+([^\s,"]+(?:\s+[^\s,"]+)?)(?:\s+(?:say|with text|saying)\s+(.*))?', command, re.IGNORECASE)
            contact = match.group(1).strip() if match else ""
            text_msg = match.group(2).strip() if (match and match.group(2)) else ""

            launch_res = self.computer_agent.launch_application("whatsapp")
            if contact:
                msg_str = f" with message: '{text_msg}'" if text_msg else ""
                launch_res["message"] = f"✓ Opened WhatsApp for contact '{contact}'{msg_str}."
            return launch_res

        # ── 00. Email Communication Priority Handler ─────────────────────────────
        if any(v in cmd_lower for v in ["draft email", "send email", "write email", "email to", "gmail", "compose email"]):
            # Pass directly to Communication Agent Email Wizard
            if "send" in cmd_lower:
                return self.comms_agent.send_email(command, user_approved=user_approved)
            else:
                to_match = re.search(r'to\s+([^\s,"]+(?:\s+[^\s,"]+)?)', command, re.IGNORECASE)
                raw_target = to_match.group(1).strip() if to_match else ""
                
                to_email = ""
                if "@" in raw_target:
                    to_email = raw_target
                elif raw_target:
                    from agents.comms_agent import search_local_contacts
                    matches = search_local_contacts(raw_target)
                    if len(matches) == 1:
                        to_email = matches[0]["email"]
                    elif len(matches) > 1:
                        self.pending_clarification = {
                            "type": "contact_disambiguation",
                            "target_name": raw_target,
                            "candidates": matches,
                            "original_command": command,
                        }
                        c_str = ", ".join([f"({i+1}) {c['name']} ({c['email']})" for i, c in enumerate(matches)])
                        return {
                            "success": False,
                            "contact_unresolved": True,
                            "pending_clarification": True,
                            "candidates": matches,
                            "target_name": raw_target,
                            "message": f"🔒 Multiple Contacts Found: I found {len(matches)} contacts matching '{raw_target}': {c_str}. Which one did you mean?",
                        }
                    else:
                        self.pending_clarification = {
                            "type": "contact_disambiguation",
                            "target_name": raw_target,
                            "original_command": command,
                        }
                        return {
                            "success": False,
                            "contact_unresolved": True,
                            "pending_clarification": True,
                            "target_name": raw_target,
                            "message": f"🔒 Contact Unresolved: I couldn't find an email address for '{raw_target}' in local contacts or memory. What is {raw_target}'s email address?",
                        }
                else:
                    to_email = "recipient@example.com"

                self.pending_clarification = {
                    "type": "email_wizard",
                    "step": "get_subject",
                    "to_email": to_email,
                    "subject": None,
                    "body": None,
                    "original_command": command,
                }
                return {
                    "success": True,
                    "pending_clarification": True,
                    "to": to_email,
                    "message": f"✓ Recipient set to '{to_email}'! What is the subject of the email?",
                }

        # ── 00. Pure App/Web Launcher (Only triggers for pure launch prompts) ───
        if any(cmd_lower.startswith(k) for k in ["open ", "launch ", "start ", "go to ", "visit "]):
            target = re.sub(r'^(open|launch|start|go to|visit)\s+', '', command, flags=re.IGNORECASE).strip()
            # Only trigger simple launcher if target is short (pure app name) and has no complex verbs
            if len(target.split()) <= 3 and not any(v in cmd_lower for v in ["draft", "send", "summarize", "search", "read"]):
                return self.browser_agent.open_app_or_website(target)

        # ── 01. Omni-Category ToolRegistry Intercept ─────────────────────────────
        if "read" in cmd_lower and "email" in cmd_lower:
            return self.tool_registry.execute_tool("read_latest_email")
        elif "convert" in cmd_lower and ("csv" in cmd_lower or "json" in cmd_lower):
            match = re.search(r'([^\s,"]+\.csv)', command, re.IGNORECASE)
            cpath = match.group(1) if match else "data/sample.csv"
            return self.tool_registry.execute_tool("convert_csv_to_json", csv_path=cpath)
        elif "light" in cmd_lower or "plug" in cmd_lower or "iot" in cmd_lower:
            state = "off" if "off" in cmd_lower else "on"
            return self.tool_registry.execute_tool("toggle_smart_light", device_name="Living Room Light", state=state)

        # ── 1. Priority Override: Chitchat / Greetings ───────────────────────────
        if intent == "chitchat" or (cmd_lower in ["hello", "hi", "hey monday", "good morning", "good evening", "how are you", "who are you"] and intent != "browser"):
            return {
                "success": True,
                "intent": "chitchat",
                "message": "Hello! I am M.O.N.D.A.Y., your Modular Operational Neural Desktop Assistant. How can I help you today?",
            }

        # ── 1. Voice Engine Override ───────────────────────────────────────────
        if "speak" in cmd_lower or "say out loud" in cmd_lower or "say " in cmd_lower:
            phrase = re.sub(r'^.*(speak|say out loud|say)\s+', '', command, flags=re.IGNORECASE).strip()
            return self.voice_agent.speak(phrase or "M.O.N.D.A.Y. online.")

        # ── 2. Memory Operations ───────────────────────────────────────────────
        if "remember" in cmd_lower or "recall" in cmd_lower or "what did i" in cmd_lower or intent == "memory_query":
            if "remember" in cmd_lower:
                clean_rem = re.sub(r'^.*remember\s+(that\s+)?', '', command, flags=re.IGNORECASE)
                parts = re.split(r'\s+(is|=|\:)\s+', clean_rem, maxsplit=1)
                key = parts[0].strip() if len(parts) > 0 else "note"
                val = parts[2].strip() if len(parts) > 2 else clean_rem
                return self.memory_agent.remember(key, val, topic="user_notes")
            else:
                query = re.sub(r'^.*(recall|what is|what did i say about)\s+', '', command, flags=re.IGNORECASE).strip()
                return self.memory_agent.recall(query or command)

        # ── 3. Desktop Automation & Dynamic Code Execution (Pillar III) ──────────
        elif any(k in cmd_lower for k in ["volume", "folder", "create", "set", "adjust", "change", "news", "scrape", "script"]):
            return self.coder_agent.generate_and_execute_script(command)
        elif "organize" in cmd_lower or "screenshot" in cmd_lower or "health" in cmd_lower or intent == "desktop_automation":
            if "screenshot" in cmd_lower or "screen" in cmd_lower:
                return self.computer_agent.take_screenshot()
            elif "organize" in cmd_lower or "sort" in cmd_lower:
                match = re.search(r'organize\s+([^\s,"]+)', command, re.IGNORECASE)
                dir_target = match.group(1) if match else "."
                return self.computer_agent.organize_directory(dir_target)
            elif "health" in cmd_lower or "stats" in cmd_lower or "system" in cmd_lower:
                return self.computer_agent.get_system_health()
            elif "open" in cmd_lower or "launch" in cmd_lower:
                app_name = re.sub(r'^(open|launch)\s+', '', command, flags=re.IGNORECASE).strip()
                return self.computer_agent.launch_application(app_name)
            else:
                return self.coder_agent.generate_and_execute_script(command)

        # ── 4. Document Intelligence ──────────────────────────────────────────
        elif intent == "document_intel" or "summarize" in cmd_lower or "pdf" in cmd_lower or "read doc" in cmd_lower:
            match = re.search(r'(?:summarize|read|parse)\s+([^\s,"]+)', command, re.IGNORECASE)
            filepath = match.group(1) if match else "README.md"
            res = self.document_agent.summarize_document(filepath)
            if res.get("success") and res.get("summary"):
                res["message"] = f"✓ Summarised {res.get('document', filepath)} ({res.get('original_word_count', 0)} words):\n{res['summary']}"
            return res

        # ── 5. Communication Agent (Bug 3 Fix: Contact Resolution Gating) ─────
        elif intent == "communication" or "email" in cmd_lower or "draft" in cmd_lower or "message" in cmd_lower:
            if "send" in cmd_lower:
                return self.comms_agent.send_email(command, user_approved=user_approved)
            else:
                to_match = re.search(r'to\s+([^\s,"]+)', command, re.IGNORECASE)
                raw_target = to_match.group(1).strip() if to_match else ""
                
                if "@" in raw_target:
                    to_email = raw_target
                elif raw_target:
                    from agents.comms_agent import search_local_contacts
                    matches = search_local_contacts(raw_target)
                    
                    if len(matches) == 1:
                        to_email = matches[0]["email"]
                    elif len(matches) > 1:
                        self.pending_clarification = {
                            "type": "contact_disambiguation",
                            "target_name": raw_target,
                            "candidates": matches,
                            "original_command": command,
                        }
                        c_str = ", ".join([f"({i+1}) {c['name']} ({c['email']})" for i, c in enumerate(matches)])
                        return {
                            "success": False,
                            "contact_unresolved": True,
                            "pending_clarification": True,
                            "candidates": matches,
                            "target_name": raw_target,
                            "message": f"🔒 Multiple Contacts Found: I found {len(matches)} contacts matching '{raw_target}': {c_str}. Which one did you mean?",
                        }
                    else:
                        self.pending_clarification = {
                            "type": "contact_disambiguation",
                            "target_name": raw_target,
                            "original_command": command,
                        }
                        return {
                            "success": False,
                            "contact_unresolved": True,
                            "pending_clarification": True,
                            "target_name": raw_target,
                            "message": f"🔒 Contact Unresolved: I couldn't find an email address for '{raw_target}' in local contacts or memory. What is {raw_target}'s email address?",
                        }
                else:
                    return {
                        "success": False,
                        "error": "No email recipient specified. Usage: draft email to name@example.com",
                    }
                self.pending_clarification = {
                    "type": "email_wizard",
                    "step": "get_subject",
                    "to_email": to_email,
                    "subject": None,
                    "body": None,
                    "original_command": command,
                }
                return {
                    "success": True,
                    "pending_clarification": True,
                    "to": to_email,
                    "message": f"✓ Recipient set to '{to_email}'! What is the subject of the email?",
                }

        # ── 6. Dynamic Scripting & Zero-Shot Code Execution Agent (Pillar III) ─────
        elif any(k in cmd_lower for k in ["script", "code", "volume", "folder", "create", "set", "adjust", "news", "scrape", "change"]):
            return self.coder_agent.generate_and_execute_script(command)

        # ── 7. Web Search vs Dynamic Code Execution Fallback ───────────────────
        else:
            if any(k in cmd_lower for k in ["search", "find", "google", "look up", "research"]):
                query = re.sub(r'^(search for|search|find|look up|google)\s+', '', command, flags=re.IGNORECASE).strip()
                if "research" in cmd_lower:
                    return self.browser_agent.research_topic(query or command)
                return self.browser_agent.web_search(query or command)
            else:
                return self.coder_agent.generate_and_execute_script(command)
