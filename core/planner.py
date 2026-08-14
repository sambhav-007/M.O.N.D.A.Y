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

from core.router import Router
from core.skills_builtin import build_builtin_registry
from core.tool_registry import ToolRegistry
from core.autonomy import AutonomyDaemon
from core.security import evaluate_action_permission, log_action
from ml.intent_classifier import get_trained_classifier, predict_intent
from ml.rl_router import EpsilonGreedyBandit, ROUTING_ACTIONS


# ── Tier-2 confirmation vocabulary (PRD §9) ──────────────────────────────────
# Shared by every gated action so "yes" means the same thing everywhere. An
# answer that is neither affirmative nor negative is deliberately NOT treated as
# either: the gate re-asks. Guessing in an irreversible path is the one failure
# mode this whole mechanism exists to prevent.
_AFFIRMATIVE = {
    "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "confirm",
    "confirmed", "approve", "approved", "go", "go ahead", "do it", "proceed",
    "send", "send it", "send the mail", "send the email", "send mail",
    "send email",
}
_NEGATIVE = {
    "no", "n", "nope", "cancel", "stop", "abort", "don't", "dont", "not now",
    "later", "discard", "nevermind", "never mind", "reject", "deny",
}


# ── /help ────────────────────────────────────────────────────────────────────
# Matched exactly, never as a substring. The previous intercept tested
# `"help" in cmd_lower`, so "help me summarize sample.pdf" printed the menu
# instead of summarising the file.
HELP_TRIGGERS = {
    "/help", "/?", "help", "help me", "?", "commands", "list commands",
    "capabilities", "features", "what can you do", "what can u do",
    "what can you perform", "what are your features", "show help", "menu",
}


def is_help_request(command: str) -> bool:
    """True only for a bare help request, not for a task that mentions help."""
    raw = (command or "").lower().strip()
    if raw in HELP_TRIGGERS:          # checked first so bare "?" and "/?" survive
        return True
    return raw.strip(".!?") in HELP_TRIGGERS


def build_help_text() -> str:
    """
    The capability list shown by /help.

    Deliberately describes only what the code actually does. Anything that needs
    setup is labelled rather than omitted or overstated — a help menu that
    promises features the system does not have is worse than no help menu.
    """
    from core.security import TIER_2_IMPLEMENTED

    # Lines are kept under 72 characters so the whole menu fits inside the CLI's
    # bordered panel on an 80-column terminal without re-wrapping, which would
    # break the two-column alignment.
    gated = ", ".join(sorted(TIER_2_IMPLEMENTED))
    return f"""🤖 M.O.N.D.A.Y. — what I can do

Type these in plain English. Every example below works as written.

🖥️  APPS & SYSTEM
   open notepad             launch an app (web fallback)
   screenshot               capture the screen to data/staging
   health                   live CPU / RAM / disk
   battery                  charge level and power status
   set volume to 40         also: mute, volume
   my ip                    local network details
   what time is it          also: what is the date
   kill <process>           ⚠️ Tier 2 — I ask first

📁  FILES & DOCUMENTS
   organize <folder path>   sort a folder by file type
   summarize report.pdf     summarise a PDF or text file

🌐  WEB & KNOWLEDGE
   search <anything>        live web search, with sources
   research <topic>         multi-source synthesised report
   what is the capital of France     looked up, not guessed

🧠  MEMORY
   remember my prof is Dr. Gupta     store a fact
   recall prof              retrieve it later
   proactive                suggestions from 2.3 + 2.4

📧  COMMUNICATION
   send mail to a@b.com subject "Hi" body "Hello"
        ⚠️ Tier 2 — I draft it, show you, then ask. Reply 'send'
        to deliver or 'cancel' to keep it as a draft.
   message 9876543210 saying hi      ⚠️ Tier 2 — I show you the
                                     message and ask; say 'yes' and
                                     I send it. 10 digits is fine,
                                     I'll assume +91
   papa's number is 9876543210       saves a contact, then just say
                                     "message papa saying hi"
   schedule meeting tomorrow 3pm     add a calendar event
   notify me the build finished      desktop notification

📊  LIVE INFO
   weather in Delhi · bitcoin price · where am i · iss location

🗣️  VOICE
   speak hello world        say something out loud
   Spacebar (in the app)    push-to-talk

🔍  DIAGNOSTICS
   history                  the action audit log
   /help                    this menu

🔒  SAFETY — how approval works
   Reversible actions (Tier 1) run straight away and are logged.
   Irreversible ones (Tier 2) stop and ask first, with an ETA from
   the regression model: "Est. 12s — approve?". Nothing irreversible
   happens without your explicit yes.
   Currently gated: {gated}.

🎓  THE ML INSIDE (course components)
   2.1 intent classifier    routes your command
   2.2 ETA regression       supplies the "Est. 12s"
   2.3 memory clustering    groups what you save
   2.4 association rules    finds repeated habits
   2.5 RL router            learns which route works
   2.6 XAI                  explains 2.1 and 2.2

⚙️  NEEDS SETUP (inactive right now)
   Sending email needs SMTP_USER / SMTP_PASSWORD in .env
   (for Gmail, an App Password).
   Screen vision needs a Gemini API key.
   Spoken replies use gTTS, which needs the network."""


# ── Multi-turn state handling ────────────────────────────────────────────────
# The clarification steps that authorise something irreversible. A clarification
# on this list may only be resolved by an explicit answer; anything that clears
# it has to say so out loud.
_APPROVAL_STEPS = frozenset({"confirm_action", "confirm_send"})

# Words that mark a reply as a new topic rather than an answer to the question
# still on the table. Deliberately broad: a false positive here abandons a
# clarification (recoverable, and now announced), while a false negative feeds a
# genuine new command into a resolver that will misread it.
_NEW_TOPIC_MARKERS = (
    "screen", "where", "weather", "who", "what", "search", "open",
    "capabilities", "tell me", "how", "show", "bitcoin", "crypto",
)


# ── Speech ───────────────────────────────────────────────────────────────────
# Replies are written to be read on screen: multi-line reports, bullet lists,
# file paths, tick marks. Reading all of that aloud is slow and unpleasant —
# a health check spoke three lines of percentages, and a web result spoke an
# entire article. The screen keeps the full answer; the voice gets the gist.
_SPEECH_MAX_CHARS = 180
_DECORATION = re.compile(r"[✓✅⚠️❌🤖📧🎙️📝🌍🌤️🛸💰📚🔍💡🧠⚡🖥️📊🗣️🔒🎓⚙️📁🌐↩️•·►]")
_BULLET_LINE = re.compile(r"^\s*[•\-*]\s*")


def spoken_form(result: Dict[str, Any]) -> str:
    """Reduces a reply to something worth hearing.

    A handler may set `data["speech"]` to say exactly what it wants spoken.
    Otherwise the first meaningful line is used, stripped of decoration and
    capped — the rest stays on screen where it can be read at a glance.
    """
    if not isinstance(result, dict):
        return ""

    explicit = result.get("speech")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()[:_SPEECH_MAX_CHARS]

    message = str(result.get("message") or "")
    lines = [ln.strip() for ln in message.splitlines() if ln.strip()]
    if not lines:
        return ""

    headline = _DECORATION.sub("", lines[0]).strip()
    headline = _BULLET_LINE.sub("", headline).strip()

    # A heading with the substance underneath it ("Live Weather Forecast for
    # Delhi:") is not worth speaking on its own — take the first detail too.
    if headline.endswith(":") and len(lines) > 1:
        detail = _BULLET_LINE.sub("", _DECORATION.sub("", lines[1])).strip()
        headline = f"{headline.rstrip(':')}. {detail}"

    if len(headline) > _SPEECH_MAX_CHARS:
        cut = headline[:_SPEECH_MAX_CHARS]
        headline = cut[: cut.rfind(" ")] if " " in cut else cut
        headline = headline.rstrip(" ,;:") + "…"
    return headline


def _prepend_notice(result: Dict[str, Any], notice: str) -> Dict[str, Any]:
    """Puts `notice` in front of a result's message without disturbing the rest.

    Used to surface a cancelled approval gate on the reply to whatever the user
    typed instead of answering it.
    """
    if not notice or not isinstance(result, dict):
        return result
    result["cancelled_pending_approval"] = True
    existing = result.get("message")
    result["message"] = f"{notice}\n\n{existing}" if existing else notice
    return result


def parse_confirmation(answer: str) -> str:
    """
    Classifies a reply to a Tier-2 confirmation prompt.

    Returns "yes", "no", or "unclear". Anything not clearly affirmative or
    clearly negative is "unclear" — the caller must re-ask rather than assume.
    """
    a = (answer or "").lower().strip().strip(" .!?")
    if a in _AFFIRMATIVE:
        return "yes"
    if a in _NEGATIVE:
        return "no"
    # A comma after the answer is punctuation, not meaning: "no, cancel that" is
    # as clear a decline as "no cancel that", but the prefix test below is
    # whitespace-delimited and "no," failed it. Such a reply then fell through to
    # "unclear" and, if it also contained a new-topic word, the gate was released
    # as an abandonment instead of recorded as a decision. Commas only — the
    # apostrophe in "don't" is load-bearing.
    a = a.replace(",", " ")
    # Allow natural prefixes ("yes please", "cancel that") but never a bare
    # substring match, so "don't send it" cannot read as affirmative.
    if a.startswith(("yes ", "yeah ", "confirm", "approve", "go ahead", "do it", "proceed")):
        return "yes"
    if a.startswith(("no ", "cancel", "stop", "abort", "don't", "dont", "never")):
        return "no"
    return "unclear"


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

        # Phase 3: the skill router. Built after the agents exist, because the
        # skills bind to them. `last_routing_decision` is exposed so the API and
        # the tests can see *how* a command was routed, not just what came back —
        # the old chain gave no way to tell whether the classifier had been
        # involved at all.
        self.router = Router(build_builtin_registry(self))
        self.last_routing_decision = None
        self.autonomy_daemon = AutonomyDaemon()
        self.autonomy_daemon.start()

        # Multi-Turn Conversation State Machine
        self.pending_clarification: Optional[Dict[str, Any]] = None

        # Tier-2 executor registry (PRD §9). A gated action parks its *name* and
        # arguments in pending_clarification, never a callable — the state has to
        # stay plain data so it can be logged and inspected, and so nothing can
        # smuggle an arbitrary function into the approval path. Only actions in
        # this table can ever be resumed by a confirmation.
        self._tier2_executors: Dict[str, Any] = {
            "terminate_process": self._exec_terminate_process,
            "send_whatsapp": self._exec_send_whatsapp,
        }

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
            "user": username,
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

        # /help is answerable at any time and changes nothing, so it is handled
        # before the multi-turn check. A pending confirmation stays armed: asking
        # what the options are must not silently drop a Tier-2 prompt, nor count
        # as an answer to it.
        if is_help_request(cmd):
            result = {"success": True, "intent": "help_menu", "message": build_help_text()}
            if self.pending_clarification is not None:
                result["pending_clarification"] = True
                result["message"] += "\n\n(You still have a pending confirmation — answer it above.)"
            return {
                "user_command": cmd,
                "intent_classification": {
                    "predicted_intent": "help_menu", "confidence": 1.0,
                    "llm_fallback": False, "clo": "CLO04",
                },
                "rl_routing": {"strategy": "help_intercept", "clo": "CLO05"},
                "execution_result": result,
            }

        # Step 0: Auto-Memory Extraction & Context Pre-fetching
        self.memory_agent.auto_extract_and_remember(cmd)
        context_memories = self.memory_agent.get_contextual_memories(cmd)

        # Step 0.1: Check for Multi-Turn Pending Clarification State
        abandon_notice = ""
        if self.pending_clarification is not None:
            cmd_lower = cmd.lower().strip()
            pending = self.pending_clarification
            is_gate = pending.get("step") in _APPROVAL_STEPS

            # A clear yes/no is an answer to the question that was asked, even
            # when it also contains a word from the new-topic list below. "yes,
            # show me" used to read as a brand-new command, which dropped an
            # armed Tier-2 gate on the floor.
            if is_gate and parse_confirmation(cmd) != "unclear":
                return self._resolve_clarification(cmd)

            # If input is a new independent command rather than an email/number selection or short reply, auto-clear clarification state
            if any(k in cmd_lower for k in _NEW_TOPIC_MARKERS):
                self.pending_clarification = None
                # Dropping a low-stakes clarification (which email did you mean?)
                # quietly is fine — the user moved on. Dropping an approval gate
                # quietly is not: they were asked whether to send something and
                # the answer silently became "no" with nothing said. It fails
                # closed, which is the right direction, but it must be audible or
                # a later "yes" answers a question that no longer exists.
                if is_gate:
                    abandon_notice = self._announce_cancelled_gate(pending)
            else:
                return self._resolve_clarification(cmd)

        # Step 0.5: Dynamic Multi-Step Task DAG Engine Check
        if self.task_dag_engine.is_multi_step_goal(cmd):
            dag_result = self.task_dag_engine.execute_dag(cmd, user_approved=user_approved)
            self.memory_agent.auto_store_conversation_turn(cmd, str(dag_result.get("message", "")))
            dag_result = _prepend_notice(dag_result, abandon_notice)
            return {
                "user_command": cmd,
                "intent_classification": {"predicted_intent": "multi_step_dag", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "dag_engine", "clo": "CLO05"},
                "execution_result": dag_result,
            }

        # Step 1: Component 2.1 Intent Classifier
        intent, confidence, fallback = predict_intent(self.classifier, cmd)

        # Step 2: Component 2.5 RL Bandit Routing Decision if confidence is low
        # `routed_arm` is the arm that must be credited in step 4. When the
        # classifier is confident the bandit is not consulted at all, and the
        # outcome is evidence about direct dispatch; when it is not, the arm the
        # bandit actually pulled is the one the outcome describes.
        routed_arm = ROUTING_ACTIONS.index("direct_dispatch")
        routing_strategy = "direct_dispatch"
        if fallback:
            routed_arm = self.rl_bandit.select_action()
            routing_strategy = ROUTING_ACTIONS[routed_arm]

        # Step 3: Match intent to target agent tool execution
        tool_result = self._dispatch_to_agent(cmd, intent, user_approved, confidence)

        # If standard dispatch requires generative reasoning, query Cognitive Engine
        if fallback or (isinstance(tool_result, dict) and not tool_result.get("success") and not tool_result.get("refusal")):
            llm_response = self.cognitive_engine.generate_cognitive_response(cmd, context_memories)
            if llm_response:
                tool_result = {
                    "success": True,
                    "cognitive_llm": True,
                    "message": f"🤖 M.O.N.D.A.Y. Cognitive Response:\n{llm_response}"
                }

        # Step 4: Reward feedback to the arm that was actually pulled.
        # This used to hardcode `ROUTING_ACTIONS.index("direct_dispatch")` on both
        # branches, so every reward landed on one arm no matter which was
        # selected. The other three arms were never updated, their Q-values never
        # left zero, and `get_policy()`'s argmax was therefore decided by array
        # initialisation rather than by anything the bandit had observed —
        # component 2.5 could not learn. Credit `routed_arm` or it learns nothing.
        self.rl_bandit.update(routed_arm, 1.0 if tool_result.get("success", False) else -1.0)

        tool_result = _prepend_notice(tool_result, abandon_notice)

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

        # Trigger voice output in background thread so UI thread does not freeze.
        # Speaks a short form, not the whole reply — see `spoken_form`.
        if getattr(self, "enable_voice", True) and isinstance(tool_result, dict) and tool_result.get("message"):
            speech = spoken_form(tool_result)
            if speech:
                import threading
                threading.Thread(target=self.voice_agent.speak, args=(speech,), daemon=True).start()

        return output

    def _announce_cancelled_gate(self, pending: Dict[str, Any]) -> str:
        """Records and describes an approval gate abandoned for a new command.

        Nothing was executed — the gate fails closed. The user still has to be
        told, because from their side they asked for something irreversible, were
        asked to confirm, and would otherwise never hear that it did not happen.
        """
        action = (
            pending.get("action_name")
            or ("send_email" if pending.get("step") == "confirm_send" else "pending action")
        )
        target = pending.get("target") or pending.get("recipient") or ""
        described = f"{action} → {target}" if target else str(action)

        log_action(str(action), str(target) or "unknown", 2, "cancelled_new_command",
                   "planner", {"reason": "user issued a new command instead of answering"})

        return (
            f"↩️ Cancelled the pending approval ({described}) — you asked for "
            f"something else instead. Nothing was sent or run."
        )

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

        if c_step == "confirm_action":
            return self._resolve_tier2_approval(clarification, raw_ans)

        if c_step == "get_contact_number":
            return self._resolve_contact_number(clarification, raw_ans)

        if c_step == "confirm_send":
            verdict = parse_confirmation(raw_ans)

            to_email = clarification["to_email"]
            subject = clarification.get("subject", "(no subject)")
            body = clarification.get("body", "")
            draft_id = clarification.get("draft_id")

            if verdict == "yes":
                result = self._send_confirmed_email(to_email, subject, body, draft_id)
            elif verdict == "no":
                result = {
                    "success": True,
                    "delivered": False,
                    "cancelled": True,
                    "to": to_email,
                    "draft_id": draft_id,
                    "message": f"Cancelled — nothing was sent. The draft for {to_email} is still saved.",
                }
            else:
                # Before giving up: the reply may be an edit rather than an
                # answer. Someone shown "(no subject)" naturally types
                # `subject: hello body: hii`, and answering that with "I didn't
                # catch that" strands them — the draft cannot be corrected and
                # the only ways out are sending it empty or cancelling.
                edit = self._parse_email_command(user_response)
                if edit["subject"] or edit["body"]:
                    subject = edit["subject"] or subject
                    body = edit["body"] or body
                    draft_res = self.comms_agent.draft_email(to_email, subject, body)
                    draft_id = draft_res.get("draft_id", draft_id)
                    self.pending_clarification = {
                        **clarification,
                        "subject": subject,
                        "body": body,
                        "draft_id": draft_id,
                    }
                    preview = body if len(body) <= 160 else body[:160] + "…"
                    result = {
                        "success": True,
                        "pending_clarification": True,
                        "awaiting_send_confirmation": True,
                        "updated": True,
                        "to": to_email,
                        "subject": subject,
                        "body": body,
                        "draft_id": draft_id,
                        "message": (
                            f"📧 Draft updated.\n"
                            f"  To      : {to_email}\n"
                            f"  Subject : {subject}\n"
                            f"  Body    : {preview}\n\n"
                            f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
                        ),
                    }
                else:
                    # Genuinely unrecognised: re-arm rather than guess about a send.
                    self.pending_clarification = clarification
                    result = {
                        "success": False,
                        "pending_clarification": True,
                        "awaiting_send_confirmation": True,
                        "message": (
                            f"I didn't catch that. Reply 'send' to deliver the email to "
                            f"{to_email}, 'cancel' to keep it as a draft, or give me the "
                            f'missing parts, e.g. subject "Hi" body "Hello".'
                        ),
                    }

            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_send_confirm", "clo": "CLO05"},
                "execution_result": result,
            }

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

            # Hand straight over to the send confirmation instead of stopping
            # at a draft the user then has no way to send.
            self.pending_clarification = {
                "type": "email_send_confirm",
                "step": "confirm_send",
                "to_email": to_email,
                "subject": subject_val,
                "body": body_val,
                "draft_id": res.get("draft_id"),
                "original_command": clarification.get("original_command", ""),
            }
            preview = body_val if len(body_val) <= 160 else body_val[:160] + "…"
            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_wizard_complete", "clo": "CLO05"},
                "execution_result": {
                    "success": True,
                    "pending_clarification": True,
                    "awaiting_send_confirmation": True,
                    "draft_id": res.get("draft_id"),
                    "to": to_email,
                    "subject": subject_val,
                    "body": body_val,
                    "gmail_compose_url": res.get("gmail_compose_url"),
                    "message": (
                        f"📧 Draft ready.\n"
                        f"  To      : {to_email}\n"
                        f"  Subject : {subject_val}\n"
                        f"  Body    : {preview}\n\n"
                        f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
                    ),
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

    # Openers that mark a request for a fact rather than an action.
    _QUESTION_OPENERS = (
        "what ", "what's ", "whats ", "who ", "who's ", "whos ", "when ",
        "where ", "why ", "which ", "how ",
    )

    # Questions about the user's own stored data belong to the memory agent, and
    # questions about M.O.N.D.A.Y. itself belong to chitchat. Never web-search these.
    _QUESTION_EXCLUSIONS = (
        "what did i", "what do i", "what have i", "what was i", "what are my",
        "what is my", "what's my", "whats my", "who am i", "my name", "my notes",
        "my to-do", "my todo", "my tasks", "recall", "remember", "i saved",
        "i mentioned", "i told you", "who are you", "your name", "are you an ai",
        "how are you", "what can you do",
    )

    # "send mail to a@b.com subject: "Hi" body: "There"" and friends. Quotes may
    # be straight or curly; subject/body may also run unquoted to the next keyword.
    _EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    # The separator is optional when the value is quoted, so both
    # `subject: "Hi"` and `subject "Hi"` work. Unquoted values still require a
    # ':' or '=' — otherwise "subject" would swallow the rest of the sentence.
    _SUBJECT_RE = re.compile(
        r'subject\s*(?:[:=]\s*)?["“‘\']([^"”’\']*)["”’\']'
        r'|subject\s*[:=]\s*([^"\n]+?)(?=\s+(?:body|message|content)\b|$)',
        re.IGNORECASE,
    )
    _BODY_RE = re.compile(
        r'(?:body|message|content)\s*(?:[:=]\s*)?["“‘\']([^"”’\']*)["”’\']'
        r'|(?:body|message|content)\s*[:=]\s*([^"\n]+?)$',
        re.IGNORECASE,
    )

    def _parse_email_command(self, command: str) -> Dict[str, str]:
        """Pulls recipient, subject and body out of a free-form email command.

        Returns a dict with 'recipient' (an address, or a bare name to resolve
        against contacts), 'subject' and 'body' — each '' when absent.
        """
        recipient = ""
        addr = self._EMAIL_RE.search(command)
        if addr:
            recipient = addr.group(0)
        else:
            # "to <name>" — stop before the subject/body keywords.
            name = re.search(
                r'\bto\s+([^\n,]+?)(?=\s+(?:subject|body|message|content)\b|$)',
                command, re.IGNORECASE,
            )
            if name:
                recipient = name.group(1).strip()

        def _first(match) -> str:
            if not match:
                return ""
            return (match.group(1) or match.group(2) or "").strip()

        return {
            "recipient": recipient,
            "subject": _first(self._SUBJECT_RE.search(command)),
            "body": _first(self._BODY_RE.search(command)),
        }

    # ── Tier-2 approval gate (PRD §9) ────────────────────────────────────────
    def require_tier2_approval(
        self,
        action_name: str,
        target: str,
        executor: str,
        executor_kwargs: Dict[str, Any],
        original_command: str,
        task_type: str = "desktop_automation",
        agent: str = "computer",
        step_count: int = 1,
        detail_lines: Optional[List[str]] = None,
        question: str = "Approve? Reply 'yes' to proceed, or 'no' to cancel.",
    ) -> Dict[str, Any]:
        """
        Blocks an irreversible action and asks the user first.

        This is the generic form of the draft → confirm → send sequence that the
        email path proved out. It deliberately takes no `user_approved`
        parameter: approval for a Tier-2 action can only come from an explicit
        confirming turn, never from a flag on the original request. `ui/index.html`
        used to post `user_approved: true` on *every* command, which meant a flag
        the user never set was answering a question they were never asked.

        Component 2.2's ETA regression supplies the "Est. Ns" in the prompt,
        which is the production role the PRD assigns it.
        """
        if executor not in self._tier2_executors:
            return {
                "success": False,
                "error": "UNKNOWN_TIER2_EXECUTOR",
                "message": f"Refusing to gate an unregistered action '{executor}'.",
            }

        perm = evaluate_action_permission(
            action_name,
            target,
            task_type=task_type,
            agent=agent,
            step_count=step_count,
            user_approved=False,
        )
        eta = perm.get("predicted_eta_seconds", 3.0)

        self.pending_clarification = {
            "type": "tier2_approval",
            "step": "confirm_action",
            "action_name": action_name,
            "target": target,
            "executor": executor,
            "executor_kwargs": executor_kwargs,
            "predicted_eta_seconds": eta,
            "original_command": original_command,
        }

        log_action(action_name, target, 2, "awaiting_approval", "planner",
                   {"predicted_eta_seconds": eta})

        details = "\n".join(f"  {line}" for line in (detail_lines or []))
        if details:
            details = "\n" + details
        return {
            "success": True,
            "pending_clarification": True,
            "awaiting_tier2_approval": True,
            "risk_tier": 2,
            "action_name": action_name,
            "target": target,
            "predicted_eta_seconds": eta,
            "message": (
                f"⚠️ {action_name} → {target} · can't be undone · est. {int(eta)}s"
                f"{details}\n{question}"
            ),
            # The voice gets the decision, not the form. Reading out the action
            # name, target, ETA and instructions took longer than the action.
            "speech": f"{action_name.replace('_', ' ')} to {target}. Shall I?",
        }

    def _resolve_tier2_approval(
        self, clarification: Dict[str, Any], user_response: str
    ) -> Dict[str, Any]:
        """Runs, cancels, or re-asks a pending Tier-2 action."""
        action_name = clarification.get("action_name", "unknown_action")
        target = clarification.get("target", "")
        verdict = parse_confirmation(user_response)

        if verdict == "yes":
            executor = self._tier2_executors.get(clarification.get("executor", ""))
            if executor is None:
                result = {
                    "success": False,
                    "error": "UNKNOWN_TIER2_EXECUTOR",
                    "message": f"Cannot execute '{action_name}' — no registered handler.",
                }
            else:
                result = executor(**clarification.get("executor_kwargs", {}))
                result.setdefault("approved_by_user", True)
                result.setdefault("risk_tier", 2)
        elif verdict == "no":
            log_action(action_name, target, 2, "cancelled_by_user", "planner")
            result = {
                "success": True,
                "executed": False,
                "cancelled": True,
                "risk_tier": 2,
                "action_name": action_name,
                "message": f"Cancelled — {action_name} was not performed on {target}.",
            }
        else:
            # Neither yes nor no. Re-arm and ask again; never infer approval.
            self.pending_clarification = clarification
            result = {
                "success": False,
                "pending_clarification": True,
                "awaiting_tier2_approval": True,
                "risk_tier": 2,
                "message": (
                    f"I didn't catch that. Reply 'yes' to approve {action_name} "
                    f"on {target}, or 'no' to cancel."
                ),
            }

        return {
            "user_command": user_response,
            "clarification_resumed": True,
            "intent_classification": {
                "predicted_intent": "tier2_confirmation",
                "confidence": 1.0,
                "llm_fallback": False,
                "clo": "CLO04",
            },
            "rl_routing": {"strategy": "tier2_approval", "clo": "CLO05"},
            "execution_result": result,
        }

    def _exec_terminate_process(self, process: str) -> Dict[str, Any]:
        """Approved executor for terminate_process. Only reachable post-approval."""
        return self.computer_agent.terminate_process(process, user_approved=True)

    def _exec_send_whatsapp(self, phone: str, text: str) -> Dict[str, Any]:
        """Approved executor for send_whatsapp. Only reachable post-approval."""
        return self.comms_agent.send_whatsapp_now(phone, text)

    def _resolve_contact_number(
        self, clarification: Dict[str, Any], reply: str
    ) -> Dict[str, Any]:
        """
        Takes the number the user just supplied, saves it, and resumes the
        message they originally asked for.
        """
        name = clarification.get("name", "that contact")
        pending_text = clarification.get("pending_text", "")

        # Accept a bare number, or a full "papa's number is +91..." restatement.
        phone = self.comms_agent.normalise_phone(reply)
        if not phone:
            restated = self._SAVE_NUMBER_RE.match(reply or "")
            if restated:
                phone = self.comms_agent.normalise_phone(restated.group("phone"))
                # Only let a restatement rename the contact if it names a real
                # person. "the number is +91..." must stay attached to whoever we
                # were already asking about, not be saved as "the's number".
                restated_name = self._clean_contact_name(restated.group("name"))
                if restated_name:
                    name = restated_name
        if not phone:
            phone = self.comms_agent.extract_phone(reply)

        if not phone:
            if parse_confirmation(reply) == "no":
                return self._wrap_contact_result(reply, {
                    "success": True, "cancelled": True,
                    "message": f"Alright — nothing sent, and I haven't saved a number for {name}.",
                })
            self.pending_clarification = clarification  # re-arm, don't guess
            return self._wrap_contact_result(reply, {
                "success": False,
                "pending_clarification": True,
                "awaiting_contact_number": True,
                "message": (
                    f"That didn't look like a phone number. What's {name}'s number? "
                    f"(10 digits is fine — I'll assume +91, or say 'cancel')"
                ),
            })

        self.memory_agent.remember(f"{name}'s number", f"+{phone}", topic="contacts")

        if not pending_text:
            return self._wrap_contact_result(reply, {
                "success": True,
                "contact": name,
                "phone": phone,
                "message": f"✓ Saved {name}'s number as +{phone}.",
            })

        result = self._ask_to_send_whatsapp(
            phone,
            pending_text,
            clarification.get("original_command", ""),
            source=f"just saved for {name}",
        )
        result["message"] = f"✓ Saved {name}'s number as +{phone}.\n\n" + result["message"]
        return self._wrap_contact_result(reply, result)

    def _wrap_contact_result(self, reply: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_command": reply,
            "clarification_resumed": True,
            "intent_classification": {
                "predicted_intent": "communication", "confidence": 1.0,
                "llm_fallback": False, "clo": "CLO04",
            },
            "rl_routing": {"strategy": "contact_number_prompt", "clo": "CLO05"},
            "execution_result": result,
        }

    # ── Saving a contact's phone number ──────────────────────────────────────
    # "papa number is +919996624322", "remember bhumi's number is 9876543210",
    # "save papa 9876543210". Without this, every one of those fell through to
    # chitchat and answered with a greeting, so a number could only ever be
    # taught by hitting the exact `remember X's number is Y` phrasing.
    _SAVE_NUMBER_RE = re.compile(
        r'^\s*(?:remember|save|store|set|add)?\s*'
        r'(?P<name>[A-Za-z][\w .\-]{0,40}?)'
        r"(?:'s|s')?\s+"
        r'(?:phone\s+|mobile\s+|cell\s+|whats\s?app\s+|contact\s+)?'
        r'(?:number|num|no\.?)\s*'
        r'(?:is|=|:|-)?\s*'
        r'(?P<phone>\+?\s*[\d][\d\s\-().]{5,24})\s*$',
        re.IGNORECASE,
    )

    # Words that are never a person. "the number is +91…" must not be filed
    # under "the's number".
    _NON_NAMES = {
        "the", "my", "a", "an", "this", "that", "his", "her", "their", "its",
        "your", "our", "there", "here", "it", "whatsapp", "phone", "mobile",
        "contact", "number",
    }

    def _clean_contact_name(self, raw: str) -> str:
        """Returns a usable contact name, or '' if it is filler."""
        name = (raw or "").strip().strip(",:;\"'")
        name = re.sub(
            r'^(?:remember|save|store|set|add|the|my|his|her|their)\s+',
            "", name, flags=re.IGNORECASE,
        ).strip()
        return "" if not name or name.lower() in self._NON_NAMES else name

    def _handle_save_contact_number(self, command: str) -> Optional[Dict[str, Any]]:
        """Stores '<name>'s number' when the command reads like one. Else None."""
        match = self._SAVE_NUMBER_RE.match(command or "")
        if not match:
            return None

        name = self._clean_contact_name(match.group("name"))
        phone = self.comms_agent.normalise_phone(match.group("phone"))

        if not phone:
            return {
                "success": False,
                "error": "BAD_PHONE",
                "message": (
                    f"'{match.group('phone').strip()}' doesn't look like a valid "
                    f"number. Indian mobiles are 10 digits (9876543210); for other "
                    f"countries include the code (+1 555 123 4567)."
                ),
            }
        if not name:
            # "the number is ..." — a number with nobody to attach it to.
            return {
                "success": False,
                "error": "NO_CONTACT_NAME",
                "phone": phone,
                "message": (
                    f"Whose number is +{phone}? Try: papa's number is +{phone}"
                ),
            }

        key = f"{name}'s number"
        self.memory_agent.remember(key, f"+{phone}", topic="contacts")
        return {
            "success": True,
            "intent": "save_contact_number",
            "contact": name,
            "phone": phone,
            "message": (
                f"✓ Saved {name}'s number as +{phone}.\n"
                f"  You can now say: message {name} saying hello"
            ),
        }

    # ── WhatsApp helpers ─────────────────────────────────────────────────────
    def _resolve_phone_number(self, target: str) -> Dict[str, Any]:
        """
        Turns "+919876543210" or a remembered name into a WhatsApp number.

        Contact lookup (`search_local_contacts`) carries emails only — there is no
        phone field — so names are resolved from the memory store instead:
        "remember bhumi's number is +91..." then "message bhumi saying hi".
        """
        direct = self.comms_agent.normalise_phone(target)
        if direct:
            return {"phone": direct, "source": "given directly"}

        name = (target or "").strip().lower()
        if not name:
            return {"phone": None, "error": "NO_TARGET", "message": "Who should I message?"}

        try:
            recalled = self.memory_agent.recall(target, limit=8)
        except Exception:
            recalled = {"matches": []}

        # `recall` is a TF-IDF similarity search, so it happily returns loosely
        # related rows — including stored conversation transcripts. Picking a
        # recipient out of those is how "send message to +917988280245" once
        # opened a chat with a number lifted from an unrelated saved turn. A row
        # is only accepted as a contact record when ALL of the following hold.
        for match in recalled.get("matches", []):
            key = str(match.get("key", ""))
            key_l = key.lower()
            value = str(match.get("value", ""))

            # 1. Not a conversation transcript or other machine-written record.
            if key_l.startswith(("turn_", "conversation", "session_", "log_")):
                continue
            # 2. The key must actually name the person asked for.
            if name not in key_l:
                continue
            # 3. The key must read like a contact record, not an arbitrary fact
            #    that happens to mention them.
            if not any(w in key_l for w in ("number", "phone", "mobile", "cell", "whatsapp", "contact")):
                continue
            # 4. The value must be a phone number, or contain an explicit +… one.
            phone = self.comms_agent.normalise_phone(value) or self.comms_agent.extract_phone(value)
            if phone:
                return {"phone": phone, "source": f"remembered as '{key}'"}

        return {
            "phone": None,
            "error": "NO_NUMBER",
            "message": (
                f"I don't have a phone number for '{target}'. Either give it "
                f"directly (message +919876543210 saying hi) or teach me first: "
                f"remember {target}'s number is +919876543210"
            ),
        }

    # "message/text +91… " — a literal phone number after a messaging verb.
    _WHATSAPP_PHONE_RE = re.compile(
        r'\b(?:message|msg|text|send to)\s+\+?\d[\d\s\-()]{7,}', re.IGNORECASE
    )
    # A messaging verb followed by a bare name — only routed to WhatsApp when
    # that name turns out to have a saved number. See the guard at the call site.
    _WA_NAME_VERB_RE = re.compile(
        r'^\s*(?:message|msg|text)\s+[A-Za-z]', re.IGNORECASE
    )

    # Leading verbs and filler stripped before the target is read. Done stepwise
    # rather than as one regex: "send whatsapp to bhumi saying hi", "open whatsapp
    # and message bhumi hi" and "message +91… saying hi" are all natural phrasings,
    # and a single pattern that covers them is unreadable and fragile.
    _WA_PREFIX_RE = re.compile(
        r'^\s*(?:please\s+)?(?:open|send|shoot|fire|write|start)?\s*'
        r'(?:a\s+)?(?:whats\s?app|whatsapp)?\s*(?:and\s+)?'
        r'(?:message|msg|text|send)?\s*(?:on\s+)?(?:whats\s?app|whatsapp)?\s*'
        r'(?:to\s+)?',
        re.IGNORECASE,
    )
    _WA_LEADING_PHONE_RE = re.compile(r'^\+?\s*\d[\d\s\-()]{6,}\d')
    # "papa on WhatsApp hello" puts the app name in the middle. Without removing
    # it the message body came out as "on WhatsApp hello".
    _WA_MIDDLE_APP_RE = re.compile(
        r'\s*\b(?:on|in|via|through|over|using)\s+whats\s?app\b\s*', re.IGNORECASE
    )
    _WA_CONNECTOR_RE = re.compile(
        r'^(?:saying|say|that\s+says|that|with\s+text|:|-)\s+', re.IGNORECASE
    )

    # "... to +917988280245" / "... to bhumi" at the END of the command. English
    # puts the recipient last as often as first ("send message "Hi" to +91…"),
    # and reading only the leading form made "message" itself the recipient.
    _WA_TRAILING_TARGET_RE = re.compile(
        r'\s+to\s+(?P<target>\+?[\d][\d\s\-().]{6,20}|[^\s,"]+)\s*$', re.IGNORECASE
    )
    _WA_QUOTED_RE = re.compile(r'["“‘\']([^"”’\']+)["”’\']')

    def _parse_whatsapp_command(self, command: str) -> Tuple[str, str]:
        """
        Returns (target, text). Either may be '' when absent.

        Handles both orders, because both are natural:
            message +919876543210 saying hi          target first
            send message "Hi" to +919876543210       target last
        """
        work = (command or "").strip()
        # Drop a mid-sentence "on WhatsApp" so it cannot become message text.
        work = self._WA_MIDDLE_APP_RE.sub(" ", work).strip()

        # 1. A trailing "to <target>" is the recipient — take it before anything
        #    else, so it cannot be mistaken for part of the message.
        target = ""
        trailing = self._WA_TRAILING_TARGET_RE.search(work)
        if trailing:
            target = trailing.group("target").strip()
            work = work[:trailing.start()].strip()

        rest = self._WA_PREFIX_RE.sub("", work, count=1).strip()

        # 2. A quoted span is the message, wherever it sits.
        quoted = self._WA_QUOTED_RE.search(rest)
        if quoted:
            text = quoted.group(1).strip()
            leftover = (rest[:quoted.start()] + " " + rest[quoted.end():]).strip()
            if not target:
                target = self._WA_CONNECTOR_RE.sub("", leftover, count=1).strip()
            return self._clean_wa_target(target), text

        if not rest:
            return self._clean_wa_target(target), ""

        # 3. Otherwise: leading target, then the message.
        if not target:
            phone_match = self._WA_LEADING_PHONE_RE.match(rest)
            if phone_match:
                target = phone_match.group(0).strip()
                rest = rest[phone_match.end():].strip()
            else:
                parts = rest.split(None, 1)
                target = parts[0]
                rest = parts[1].strip() if len(parts) > 1 else ""

        text = self._WA_CONNECTOR_RE.sub("", rest, count=1).strip()
        return self._clean_wa_target(target), text

    # Filler that must never be treated as a recipient. "message" reaching the
    # contact lookup is what let an unrelated saved transcript supply a number.
    _WA_NON_TARGETS = {
        "message", "msg", "text", "send", "whatsapp", "whats", "app", "a", "the",
        "and", "on", "to", "saying", "say", "that", "with", "please", "open",
    }

    def _clean_wa_target(self, target: str) -> str:
        target = (target or "").strip().strip(",:;\"'")
        return "" if target.lower() in self._WA_NON_TARGETS else target

    def _handle_whatsapp(self, command: str, cmd_lower: str) -> Dict[str, Any]:
        """
        Routes a WhatsApp request.

        Preparing a message is Tier 1 — it opens the chat with the text typed and
        nothing leaves the machine. Actually sending it is Tier 2 and goes through
        the approval gate, because it is irreversible and outward-facing.
        """
        target, text = self._parse_whatsapp_command(command)
        if not target:
            res = self.computer_agent.launch_application("whatsapp")
            if res.get("success"):
                res["message"] = (
                    "✓ Opened WhatsApp. To have me prepare a message, try: "
                    "message +919876543210 saying hello"
                )
            return res

        # A target that is clearly meant to be a number, but is not a valid one,
        # deserves to be told so — "I don't have a phone number for '79828 0245'"
        # reads as if it were a contact name we failed to look up.
        if (
            re.fullmatch(r'[\d\s\-+().]{4,}', target or "")
            and not self.comms_agent.normalise_phone(target)
        ):
            digits = re.sub(r'\D', '', target)
            return {
                "success": False,
                "error": "BAD_PHONE",
                "requested_contact": target,
                "message": (
                    f"'{target.strip()}' isn't a valid number — I count {len(digits)} "
                    f"digits. Indian mobiles are 10 digits (9876543210, I'll add +91); "
                    f"for other countries include the code (+1 555 123 4567)."
                ),
            }

        resolved = self._resolve_phone_number(target)
        if not resolved.get("phone"):
            # Park the request so the next message can supply the number and the
            # original instruction resumes. Previously the user was told to run a
            # `remember ...` command and then retype the whole thing.
            self.pending_clarification = {
                "type": "contact_number_prompt",
                "step": "get_contact_number",
                "name": target,
                "pending_text": text,
                "original_command": command,
            }
            return {
                "success": False,
                "error": resolved.get("error", "NO_NUMBER"),
                "requested_contact": target,
                "pending_clarification": True,
                "awaiting_contact_number": True,
                "message": (
                    f"I don't have a phone number for '{target}'.\n"
                    f"  What's their number? (10 digits is fine — I'll assume +91)"
                ),
            }
        phone = resolved["phone"]

        # Any message with text goes through the approval gate and is then sent
        # for real. Leaving the user to press Enter themselves was needless: they
        # had already said what to send and to whom, so the only thing worth
        # asking is whether to go ahead — which is exactly what Tier 2 is for.
        if text:
            return self._ask_to_send_whatsapp(
                phone, text, command, source=resolved.get("source", "")
            )

        # No message text — nothing to send, so just open the chat (Tier 1).
        return self.comms_agent.open_whatsapp_chat(phone, "")

    def _ask_to_send_whatsapp(
        self, phone: str, text: str, command: str, source: str = ""
    ) -> Dict[str, Any]:
        """Puts a WhatsApp message through the Tier-2 gate before sending it."""
        # Only worth showing when the number came from somewhere the user might
        # want to double-check. "given directly" is just an echo of what they typed.
        origin = [f"Number  : +{phone} — {source}"] if source and source != "given directly" else []
        return self.require_tier2_approval(
            action_name="send_whatsapp",
            target=f"+{phone}",
            executor="send_whatsapp",
            executor_kwargs={"phone": phone, "text": text},
            original_command=command,
            task_type="communication",
            agent="comms",
            detail_lines=[f'Message : "{text}"'] + origin + [
                "I'll open the chat and send it — keep that window focused.",
            ],
            question="Send it? Reply 'yes' to send now, or 'no' to cancel.",
        )

    def _handle_send_email(self, command: str, user_approved: bool) -> Dict[str, Any]:
        """Parses a 'send mail ...' command and runs the draft → send sequence.

        Previously the whole raw command was handed to send_email() as the
        recipient, so errors read "Cannot send email to 'send mail to a@b.com
        subject: ...'" and neither subject nor body was ever captured.
        """
        parsed = self._parse_email_command(command)
        recipient = parsed["recipient"]

        if not recipient:
            return {
                "success": False,
                "error": "NO_RECIPIENT",
                "message": (
                    "I couldn't find a recipient in that command. Try: "
                    'send mail to name@example.com subject: "Hi" body: "Hello"'
                ),
            }

        # A bare name has to be resolved against real contacts first.
        if "@" not in recipient:
            from agents.comms_agent import search_local_contacts
            matches = search_local_contacts(recipient)
            if len(matches) == 1:
                recipient = matches[0]["email"]
            elif len(matches) > 1:
                self.pending_clarification = {
                    "type": "contact_disambiguation",
                    "target_name": recipient,
                    "candidates": matches,
                    "original_command": command,
                }
                c_str = ", ".join(
                    f"({i+1}) {c['name']} ({c['email']})" for i, c in enumerate(matches)
                )
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "pending_clarification": True,
                    "candidates": matches,
                    "target_name": recipient,
                    "message": f"🔒 Multiple Contacts Found: {c_str}. Which one did you mean?",
                }
            else:
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "target_name": recipient,
                    "message": (
                        f"🔒 Contact Unresolved: no email address found for "
                        f"'{recipient}'. Give me the address directly."
                    ),
                }

        # "send mail to someone@example.com" with no subject or body used to jump
        # straight to "Send it? (no subject), empty body" — offering to send an
        # empty email, and leaving the user no way to supply the missing parts.
        # Collect them first instead; the wizard ends at the same confirmation.
        if not parsed["subject"] and not parsed["body"]:
            self.pending_clarification = {
                "type": "email_wizard",
                "step": "get_subject",
                "to_email": recipient,
                "subject": None,
                "body": None,
                "original_command": command,
            }
            return {
                "success": True,
                "pending_clarification": True,
                "awaiting_subject": True,
                "to": recipient,
                "message": (
                    f"📧 Composing an email to {recipient}.\n"
                    f"What should the subject be?\n\n"
                    f"(Or give it all at once: send mail to {recipient} "
                    f'subject "Hi" body "Hello")'
                ),
            }

        subject = parsed["subject"] or "(no subject)"
        body = parsed["body"] or ""

        # Persist the draft before the Tier-2 send, so a composed message
        # survives an unconfigured or failing transport.
        draft_res = self.comms_agent.draft_email(recipient, subject, body)

        # Sending is irreversible, so ALWAYS confirm — deliberately ignoring
        # `user_approved` here. The UI posts user_approved=true on every command,
        # so honouring it would silently fire the mail off the first message.
        # _resolve_clarification performs the send only on an explicit yes.
        self.pending_clarification = {
            "type": "email_send_confirm",
            "step": "confirm_send",
            "to_email": recipient,
            "subject": subject,
            "body": body,
            "draft_id": draft_res.get("draft_id"),
            "original_command": command,
        }
        preview = body if len(body) <= 160 else body[:160] + "…"
        return {
            "success": True,
            "pending_clarification": True,
            "awaiting_send_confirmation": True,
            "to": recipient,
            "subject": subject,
            "body": body,
            "draft_id": draft_res.get("draft_id"),
            "message": (
                f"📧 Draft ready.\n"
                f"  To      : {recipient}\n"
                f"  Subject : {subject}\n"
                f"  Body    : {preview}\n\n"
                f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
            ),
        }

    def _send_confirmed_email(
        self, recipient: str, subject: str, body: str, draft_id: Optional[str]
    ) -> Dict[str, Any]:
        """Performs the approved Tier-2 send and annotates the result."""
        send_res = self.comms_agent.send_email(
            recipient, user_approved=True, subject=subject, body=body
        )
        send_res["to"] = recipient
        send_res["subject"] = subject
        send_res["body"] = body
        if draft_id:
            send_res["draft_id"] = draft_id
        return send_res

    def _is_knowledge_question(self, cmd_lower: str, intent: str) -> bool:
        """True for general-knowledge questions that should be answered from the web."""
        if intent in ("memory_query", "document_intel", "communication"):
            return False
        if any(x in cmd_lower for x in self._QUESTION_EXCLUSIONS):
            return False
        return cmd_lower.startswith(self._QUESTION_OPENERS) or cmd_lower.endswith("?")

    def _dispatch_to_agent(
        self,
        command: str,
        intent: str,
        user_approved: bool,
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
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

        # ── 00000. /help — capability menu ──────────────────────────────────────
        if is_help_request(command):
            return {
                "success": True,
                "intent": "help_menu",
                "message": build_help_text(),
            }

        # ── 0. The skill router (Phase 3) ────────────────────────────────────────
        # Runs before the substring chain below, which it is progressively
        # replacing. A command the router can place is handled by a declared
        # skill with typed slots; everything else falls through unchanged, so
        # migration is incremental and each step is independently verifiable.
        #
        # The firewall and /help stay in front of it deliberately: a refusal and
        # the capability menu must not depend on a pattern matching.
        decision = self.router.route(command, intent=intent, confidence=confidence)
        self.last_routing_decision = decision
        if decision.routed:
            # `_command` carries the original text alongside the captured slots.
            # A few handlers need it to delegate to logic that parses the whole
            # command itself — contact saving, whose four validation guards must
            # not be reimplemented (handoff.md §9.2). Underscored so it can never
            # collide with a slot name.
            result = decision.skill.handler(_command=command, **decision.slots)
            if isinstance(result, dict):
                result.setdefault("routed_by", decision.stage)
                result.setdefault("skill", decision.skill.name)
            return result

        # ── 00000. Audit log & proactive suggestions ────────────────────────────
        # cli.py handled these itself, so they worked in the terminal but fell
        # through to "I'm not sure how to do that yet" in the app. /help offers
        # them, so they have to work on every surface.
        if cmd_lower.strip(".!?") in ("history", "log", "audit", "action history", "audit log"):
            from core.security import get_action_history
            entries = get_action_history(limit=10)
            if not entries:
                return {"success": True, "intent": "audit_log", "entries": [],
                        "message": "The action audit log is empty."}
            lines = [
                f"  {e.get('timestamp','')[:19].replace('T',' ')}  "
                f"T{e.get('tier','?')}  {e.get('action','')}  →  "
                f"{str(e.get('target',''))[:40]}  [{e.get('status','')}]"
                for e in entries
            ]
            return {
                "success": True,
                "intent": "audit_log",
                "entries": entries,
                "message": "🔍 Recent actions (newest last):\n" + "\n".join(lines),
            }

        if cmd_lower.strip(".!?") in ("proactive", "suggestions", "proactive suggestions"):
            sug_mem = self.memory_agent.get_proactive_suggestions()
            sug_hab = self.habit_agent.detect_habits_and_suggest()
            mem = [s.get("prompt") for s in sug_mem.get("suggestions", []) if s.get("prompt")]
            hab = [h.get("prompt") for h in sug_hab.get("suggestions", []) if h.get("prompt")]
            parts = ["🧠 Memory topics (Component 2.3 — clustering):"]
            parts += [f"  • {m}" for m in mem] or ["  (nothing yet — save a few memories first)"]
            parts.append("\n⚡ Workflow habits (Component 2.4 — association mining):")
            parts += [f"  • {h}" for h in hab] or ["  (no repeated patterns detected yet)"]
            return {
                "success": True,
                "intent": "proactive_suggestions",
                "memory_suggestions": mem,
                "habit_suggestions": hab,
                "message": "\n".join(parts),
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
                    wiki_res = self.public_api_agent.get_wikipedia_summary(topic)
                    if wiki_res.get("success"):
                        return wiki_res
                    # Phrasal topics ("the capital of France") have no Wikipedia
                    # page. Fall through to the knowledge-question web search.

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
        # Saving a contact number has to be checked before the WhatsApp and
        # chitchat branches: "papa number is +919996624322" mentions no app and
        # otherwise lands in chitchat, which answered it with a greeting.
        saved = self._handle_save_contact_number(command)
        if saved is not None:
            return saved

        # Either the user named WhatsApp, or they asked to message a literal
        # phone number — "message +919876543210 saying hi" has no other sensible
        # destination, and it is what /help tells them to type. A bare name
        # ("message bhumi") stays out of this: it is too easily an email.
        if "whatsapp" in cmd_lower or self._WHATSAPP_PHONE_RE.search(command):
            return self._handle_whatsapp(command, cmd_lower)

        # "message papa saying good morning" — no app named and no literal
        # number, but if that name has a saved WhatsApp number the intent is not
        # ambiguous. Without this the command fell through to chitchat and was
        # answered with a greeting. Guarded tightly: a messaging verb, no email
        # address, and the name must already resolve to a number (which is a
        # memory lookup, so it must not run on every command).
        if self._WA_NAME_VERB_RE.match(command) and "@" not in command:
            probe_target, _ = self._parse_whatsapp_command(command)
            if probe_target and self._resolve_phone_number(probe_target).get("phone"):
                return self._handle_whatsapp(command, cmd_lower)

        # ── 00. Email Communication Priority Handler ─────────────────────────────
        # "mail"/"mail to" matter: without them "send mail to a@outlook.com" fell
        # through to the chitchat block and got a greeting. It only ever appeared
        # to work because "gmail" happens to be a substring of a Gmail address.
        #
        # Bare "gmail" was in this list and is gone. It matched "open gmail",
        # which reached here ~70 lines before the launcher and answered a request
        # to open a website with "✓ Recipient set to 'recipient@example.com'!
        # What is the subject of the email?". Nothing is lost: every real email
        # phrasing containing it ("send a gmail to bob@x.com") also contains
        # "mail to", and the launcher now owns "open gmail" outright — the
        # `open_app_or_website` skill matches it in stage 1, ahead of this block.
        if any(v in cmd_lower for v in ["draft email", "send email", "write email",
                                        "email to", "compose email",
                                        "send mail", "mail to", "draft mail",
                                        "write mail", "compose mail"]):
            # Pass directly to Communication Agent Email Wizard
            if "send" in cmd_lower:
                return self._handle_send_email(command, user_approved)
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

        # ── 1. Voice Engine Override ───────────────────────────────────────────
        # An explicit "say X" / "speak X" directive outranks the chitchat
        # classification below ("say hello world" must speak, not greet).
        # Anchored to the start: a bare "say " substring also matches
        # "what did I say about X", which belongs to the memory agent.
        if re.match(r'^(speak|say)\b', cmd_lower) or "say out loud" in cmd_lower:
            phrase = re.sub(r'^(speak|say out loud|say)\s+', '', command, flags=re.IGNORECASE).strip()
            return self.voice_agent.speak(phrase or "M.O.N.D.A.Y. online.")

        # ── 2. Knowledge Questions → live web search ─────────────────────────────
        # General-knowledge questions share vocabulary with greetings, so the
        # classifier lands them in chitchat and the user gets a canned greeting.
        # Answer them from the web instead. Runs after the math / identity /
        # public-API intercepts above, which handle their own question forms.
        if self._is_knowledge_question(cmd_lower, intent):
            query = re.sub(r'^(hey\s+monday|monday)[,\s]+', '', command, flags=re.IGNORECASE).strip()
            query = query.rstrip("?").strip()
            search_res = self.browser_agent.web_search(query, num_results=3)
            results = search_res.get("results", [])
            if results:
                top = results[0]
                return {
                    "success": True,
                    "intent": "knowledge_question",
                    "query": query,
                    "sources_consulted": len(results),
                    "results": results,
                    "message": f"✓ {top['snippet']}\n\nSource: {top['title']} — {top['url']}",
                }
            return {
                "success": False,
                "intent": "knowledge_question",
                "query": query,
                "error": search_res.get("error", "NO_WEB_RESULTS"),
                "message": f"I couldn't find a web answer for '{query}'.",
            }

        # ── 3. Priority Override: Chitchat / Greetings ───────────────────────────
        if intent == "chitchat" or (cmd_lower in ["hello", "hi", "hey monday", "good morning", "good evening", "how are you", "who are you"] and intent != "browser"):
            return {
                "success": True,
                "intent": "chitchat",
                "message": "Hello! I am M.O.N.D.A.Y., your Modular Operational Neural Desktop Assistant. How can I help you today?",
            }

        # ── 4. Memory Operations ───────────────────────────────────────────────
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
            elif re.match(r'^(kill|terminate|force\s+close|end)\s+', cmd_lower):
                # Killing a process loses unsaved work, so it is Tier 2 and must
                # be approved in its own turn (PRD §9). Note "close" alone is not
                # matched: it is far too easy to say by accident.
                proc_name = re.sub(
                    r'^(kill|terminate|force\s+close|end)\s+', "", command, flags=re.IGNORECASE
                ).strip()
                proc_name = re.sub(r'\s+(process|app|application|task)$', "", proc_name, flags=re.IGNORECASE).strip()
                if not proc_name:
                    return {
                        "success": False,
                        "error": "NO_PROCESS",
                        "message": "Which process should I terminate?",
                    }
                return self.require_tier2_approval(
                    action_name="terminate_process",
                    target=proc_name,
                    executor="terminate_process",
                    executor_kwargs={"process": proc_name},
                    original_command=command,
                    task_type="desktop_automation",
                    agent="computer",
                    detail_lines=["Unsaved work in this process will be lost."],
                )
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
                return self._handle_send_email(command, user_approved)
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
