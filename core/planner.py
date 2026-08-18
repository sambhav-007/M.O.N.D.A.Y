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

import sys
import re
from collections import deque
from typing import Any, Deque, Dict, List, Optional

#: How many prior messages stage 3 sees — six is three exchanges. Enough for
#: "and tell mum too" and short enough that a 3B model's context is spent on the
#: tool schema (~12 KB) rather than on last week's small talk.
MAX_CONTEXT_MESSAGES = 6

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

from core.cognitive import CognitiveResponseDict, TriModelCognitiveEngine
from core.contacts import ContactMixin
from core.contracts import AgentResult, ModelAnswered
from core.email_flow import EmailMixin
from core.help import (
    HELP_TRIGGERS,
    PROHIBITED_KEYWORDS,
    build_help_text,
    is_help_request,
)
from core.llm import LlmStage
from core.router import Router
from core.skills_builtin import build_builtin_registry
from core.tier2 import Tier2Mixin, parse_confirmation
from core.tool_registry import ToolRegistry
from core.autonomy import AutonomyDaemon
from core.security import log_action
from core.speech import to_speech
from ml.intent_classifier import get_trained_classifier, predict_intent
from ml.rl_router import EpsilonGreedyBandit, ROUTING_ACTIONS

# Re-exported, not merely imported. `cli.py`, `api/main.py` and six test modules
# import these from here, and they were defined here until the substring chain
# was removed and this file became a coordinator. Keeping the names importable
# from `core.planner` means the move cost no call site anything.
#
# `TriModelCognitiveEngine` is now *only* a re-export: `CoderAgent` and
# `DocumentAgent` reach it through this module for code synthesis and document
# Q&A, which are generation, not routing. The planner itself no longer holds an
# instance — see Step 3 of `process_command` for why there is exactly one
# language model in the routing path.
__all__ = [
    "MasterPlanner", "CognitiveResponseDict", "TriModelCognitiveEngine",
    "HELP_TRIGGERS", "PROHIBITED_KEYWORDS", "build_help_text",
    "is_help_request", "parse_confirmation", "spoken_form",
]


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
_DECORATION = re.compile(r"[✓✅⚠️❌🤖📧🎙️📝🌍🌤️🛸💰📚🔍💡🧠⚡🖥️📊🗣️🔒🎓⚙️📁🌐↩️💭•·►]")
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


def _event_sink(on_event: Optional[Any]) -> Any:
    """Wraps a progress callback so callers never have to check for None.

    Also swallows anything the sink raises. A consumer that has gone away — a
    browser that closed the connection mid-answer — must not turn into a failed
    command on the server, and must certainly not lose a Tier-2 gate that was
    about to be armed.
    """
    if on_event is None:
        return lambda kind, payload=None: None

    def emit(kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        try:
            on_event(kind, payload or {})
        except Exception:  # noqa: BLE001
            pass

    return emit


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


class MasterPlanner(EmailMixin, ContactMixin, Tier2Mixin):
    """Master Multi-Agent Orchestration Engine.

    What is left in this class is coordination: boot context, the multi-turn
    state machine, and the pipeline in `process_command` — classify (2.1), route
    (2.5 when uncertain), dispatch, credit the arm that was pulled.

    Everything that decides *what a command means* moved out when the substring
    chain was deleted. Routing is declared in `core/skills_builtin.py` and the
    tranche modules beside it; the domain parsing that survives it — email,
    contacts, WhatsApp, the Tier-2 gate — is in the three mixins above, moved
    unchanged so that the ~74 tests covering it keep testing the same code.

    Mixins rather than helper objects, deliberately: the skills call
    `planner._handle_whatsapp`, `planner._resolve_phone_number` and
    `planner._handle_send_email`, and so do the tests. Composition would have
    meant rewriting every one of those call sites in the same change that moved
    the code, which is how a refactor stops being verifiable.
    """

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
        self.task_dag_engine = TaskDAGEngine(self)
        self.tool_registry = ToolRegistry()

        # Phase 3: the skill router. Built after the agents exist, because the
        # skills bind to them. `last_routing_decision` is exposed so the API and
        # the tests can see *how* a command was routed, not just what came back —
        # the old chain gave no way to tell whether the classifier had been
        # involved at all.
        # Stage 3 is constructed unconditionally and *probes* lazily, so a
        # machine with no Ollama pays nothing for it beyond one refused socket
        # connection on the first unrouted command.
        registry = build_builtin_registry(self)
        self.router = Router(registry, llm=LlmStage(registry))
        self.last_routing_decision = None
        self.autonomy_daemon = AutonomyDaemon()
        self.autonomy_daemon.start()

        # Multi-Turn Conversation State Machine
        self.pending_clarification: Optional[Dict[str, Any]] = None

        # Off unless a surface with no other voice turns it on — see the note
        # at the end of `process_command`. `cli.py` does; the UI does not,
        # because the browser speaks for it.
        self.enable_voice: bool = False

        # Recent turns, for stage 3 only. `auto_store_conversation_turn` already
        # persists every exchange, but that store is a TF-IDF corpus searched by
        # similarity — useful for "what did I say about the demo", useless for
        # "and tell mum too", which needs the *last* turn rather than a similar
        # one. This is the short-term half, and it is deliberately in memory:
        # conversation context should not survive a restart, because a command
        # resolved against a week-old turn is a bug, not a feature.
        self.recent_turns: Deque[Dict[str, str]] = deque(maxlen=MAX_CONTEXT_MESSAGES)

        # Tier-2 executor registry (PRD §9). A gated action parks its *name* and
        # arguments in pending_clarification, never a callable — the state has to
        # stay plain data so it can be logged and inspected, and so nothing can
        # smuggle an arbitrary function into the approval path. Only actions in
        # this table can ever be resumed by a confirmation.
        self._tier2_executors: Dict[str, Any] = {
            "terminate_process": self._exec_terminate_process,
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
        on_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Main execution pipeline for a user command:
          Multi-Turn Check → Command → Intent Classification (2.1) → RL Routing (2.5) → Security Tier Check → Agent Execution

        `on_event(kind, payload)` reports progress as it happens, for the
        streaming endpoint. It defaults to None, and when it is None this method
        behaves exactly as it did — the streaming surface is the *same* pipeline
        observed, not a second one implemented. A parallel streaming path would
        have to agree with this one about the Tier-2 gate, the clarification
        state machine and the RL credit, and two implementations that must agree
        is the defect this repository has found in its own code five times.

        Kinds emitted: `classified` (2.1's verdict), `routing` (which stage and
        which skill), `token` (a fragment of a model-written answer, as it is
        produced). The final result is the return value, not an event.
        """
        emit = _event_sink(on_event)
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
        emit("classified", {
            "intent": intent, "confidence": round(float(confidence), 4),
            "llm_fallback": bool(fallback),
        })

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

        # Step 3: Match intent to target agent tool execution.
        #
        # There used to be a second language model directly below this call: if
        # the classifier had fallen back, *or* the dispatch had failed for any
        # reason short of a refusal, a hosted Gemini call was made and its reply
        # replaced `tool_result` with `{"success": True, "cognitive_llm": True}`.
        # Four things were wrong with it, and only the absence of an API key on
        # this machine kept them theoretical — which is a fact about the machine,
        # not about the code:
        #
        # 1. **It reported generated text as work done.** No evidence, no
        #    `generated` flag, `success: True`. `CognitiveResponseDict.__bool__`
        #    was fixed for exactly this failure once already; the caller simply
        #    reintroduced it one level up.
        # 2. **`fallback or …` did not require the dispatch to have failed.** A
        #    command that matched a pattern and did real work — with real
        #    evidence — had its result discarded whenever component 2.1 happened
        #    to be unsure, which is precisely when the *pattern* was carrying the
        #    routing.
        # 3. **It swallowed the stage-3 proposal gate.** `_propose_llm_skill`
        #    returns success=False by design, so "shall I?" was overwritten by an
        #    unrelated answer while `pending_clarification` stayed armed — and
        #    the next "yes" would answer a question the user never saw.
        # 4. **It left the machine.** Stage 3 is local; this was not.
        #
        # Stage 3 inside the router is now the only language model in the routing
        # path: it runs last, answers with `ModelAnswered` evidence, cannot reach
        # Tier 2, and proposes rather than performs anything that is not a read.
        tool_result = self._dispatch_to_agent(
            cmd, intent, user_approved, confidence, emit=emit,
            memories=context_memories,
        )

        # Step 4: Reward feedback to the arm that was actually pulled.
        # This used to hardcode `ROUTING_ACTIONS.index("direct_dispatch")` on both
        # branches, so every reward landed on one arm no matter which was
        # selected. The other three arms were never updated, their Q-values never
        # left zero, and `get_policy()`'s argmax was therefore decided by array
        # initialisation rather than by anything the bandit had observed —
        # component 2.5 could not learn. Credit `routed_arm` or it learns nothing.
        self.rl_bandit.update(routed_arm, 1.0 if tool_result.get("success", False) else -1.0)

        tool_result = _prepend_notice(tool_result, abandon_notice)

        # What to say out loud, decided once, here, for every surface. The UI
        # used to speak `message` verbatim, so a scraped search result was read
        # to the end and a Tier-2 prompt was recited including "can't be undone ·
        # est. 1s". A handler that knows its own spoken form sets `speech`
        # itself; `to_speech` respects that and otherwise shortens the message.
        if isinstance(tool_result, dict):
            tool_result["speech"] = to_speech(
                str(tool_result.get("message", "")), tool_result
            )

        # Auto-store conversation turn to SQLite memory.db
        if isinstance(tool_result, dict) and tool_result.get("message"):
            self.memory_agent.auto_store_conversation_turn(cmd, str(tool_result.get("message", "")))
            self._remember_turn(cmd, str(tool_result.get("message", "")))

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

        # ── Who speaks, decided once ─────────────────────────────────────────
        # `enable_voice` defaults to **False**, and that default is the whole
        # point. The desktop UI speaks in the browser — it has the reply, and it
        # has barge-in, echo suppression and a wake word that were verified on
        # the real machine (handoff.md, 2026-08-14). If the backend also spoke,
        # every reply would be said twice, which is the exact defect that took
        # three attempts to kill and was only "fixed" the last time by accident:
        # gTTS and pyttsx3 were both absent, so the backend had no voice to
        # double with.
        #
        # Phase 7 gives the backend a real voice, so the accident is over and
        # the rule has to be explicit. `cli.py` sets `enable_voice = True`
        # because a terminal has no browser to speak for it; the API and the app
        # leave it off and let the UI talk.
        if getattr(self, "enable_voice", False) and isinstance(tool_result, dict) and tool_result.get("message"):
            speech = spoken_form(tool_result)
            if speech:
                import threading
                threading.Thread(target=self.voice_agent.speak, args=(speech,), daemon=True).start()

        return output

    #: A reply longer than this is truncated before it enters the context. A
    #: `history` listing or a web-search result can be thousands of characters,
    #: and spending a 3B model's context on the *text of an answer it already
    #: gave* crowds out the tool schema, which is the part it needs.
    MAX_CONTEXT_REPLY_CHARS = 300

    def _remember_turn(self, command: str, reply: str) -> None:
        """Adds one exchange to the short-term context stage 3 sees."""
        self.recent_turns.append({"role": "user", "content": command})
        trimmed = reply.strip()
        if len(trimmed) > self.MAX_CONTEXT_REPLY_CHARS:
            trimmed = trimmed[: self.MAX_CONTEXT_REPLY_CHARS].rstrip() + "…"
        self.recent_turns.append({"role": "assistant", "content": trimmed})

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
        """Resumes a paused task using the user's answer.

        Three kinds of pause exist, and each is owned by the module that created
        it: a Tier-2 approval gate, a request for a contact's phone number, and
        an email conversation. This method decides which, and nothing else — the
        200 lines of email steps that used to sit inline are in `EmailMixin`,
        next to the code that opens them.
        """
        clarification = self.pending_clarification
        self.pending_clarification = None  # cleared before dispatch; each
        # resolver re-arms it if the answer was not usable.

        raw_ans = user_response.strip()
        c_step = clarification.get("step", "resolve_contact")

        if c_step == "confirm_action":
            return self._resolve_tier2_approval(clarification, raw_ans)
        if c_step == "confirm_llm_skill":
            return self._resolve_llm_proposal(clarification, raw_ans)
        if c_step == "get_contact_number":
            return self._resolve_contact_number(clarification, raw_ans)
        return self._resolve_email_clarification(clarification, user_response)


    def _answer_unrouted(self, command: str, intent: str, decision: Any) -> Dict[str, Any]:
        """The honest answer when no skill claimed the command.

        This is all that remains of a ~520-line `if/elif` chain, and what it
        does *not* do is the point. The chain's final `else` was::

            return self.coder_agent.generate_and_execute_script(command)

        so every command nothing else recognised was handed to a code generator
        that wrote a Python script and ran it under `subprocess`. "search
        current AI news" classified `desktop_automation` at **0.33** and reached
        it, producing a live web fetch that `--block-network` cannot see and a
        20-second timeout in the test suite (handoff.md, Phase 1 note 1). A
        guess that weak must not reach code execution, and now nothing does:
        `CoderAgent` is reachable only from the `create_desktop_folder` skill,
        which requires an explicit pattern match.

        `routing_reason` is carried through so an unrecognised command can be
        diagnosed without re-running it — the chain gave no way to tell *why*
        something fell through.
        """
        return AgentResult.failed(
            f"I'm not sure how to do that yet: \"{command}\".\n"
            f"  Type /help to see what I can do.",
            error="NO_SKILL_MATCHED",
            data={
                "intent": intent,
                "routing_reason": getattr(decision, "reason", ""),
                "speech": "I'm not sure how to do that yet.",
            },
        ).as_dict()

    def _propose_llm_skill(self, command: str, decision: Any) -> Dict[str, Any]:
        """Asks before running a skill the language model guessed at.

        Deliberately *not* routed through `require_tier2_approval`: that gate
        exists for irreversible actions, its executor table is a closed list of
        names on purpose, and widening it to "any skill" to reuse the prompt
        would dissolve the property that makes it trustworthy. This is a
        different question with a different answer — *did I understand you?*
        rather than *may I do something you cannot undo?*
        """
        slots = {k: v for k, v in (decision.slots or {}).items() if v not in (None, "")}
        detail = ", ".join(f"{k}={v}" for k, v in sorted(slots.items()))
        described = decision.skill.description or decision.skill.name.replace("_", " ")

        self.pending_clarification = {
            "type": "llm_proposal",
            "step": "confirm_llm_skill",
            "skill": decision.skill.name,
            "slots": slots,
            "original_command": command,
        }
        return AgentResult.failed(
            f"💭 I think you mean: **{described}**"
            + (f" ({detail})" if detail else "")
            + "\n  I worked that out rather than recognising it, so — shall I? "
              "Reply 'yes' or 'no'.",
            error="AWAITING_LLM_CONFIRMATION",
            data={
                "intent": "llm_proposal",
                "awaiting_llm_confirmation": True,
                "pending_clarification": True,
                "proposed_skill": decision.skill.name,
                "slots": slots,
                "routing_reason": decision.reason,
                "speech": f"Did you mean {described}?",
            },
        ).as_dict()

    def _resolve_llm_proposal(
        self, clarification: Dict[str, Any], reply: str
    ) -> Dict[str, Any]:
        """Runs, cancels, or re-asks a skill stage 3 proposed."""
        name = clarification.get("skill", "")
        verdict = parse_confirmation(reply)

        if verdict == "no":
            result = {
                "success": True,
                "executed": False,
                "cancelled": True,
                "proposed_skill": name,
                "message": f"Alright — I haven't run {name.replace('_', ' ')}.",
            }
        elif verdict == "yes":
            skill = self.router.registry.get(name)
            # Re-checked at resume, not only at proposal. The pending state is
            # plain data and a resume is a second entry point; the registry is
            # the authority both times.
            if skill is None or not skill.llm_reachable:
                result = AgentResult.failed(
                    f"I can't run '{name}' that way.", error="SKILL_NOT_RUNNABLE"
                ).as_dict()
            else:
                result = skill.handler(
                    _command=clarification.get("original_command", ""),
                    **clarification.get("slots", {}),
                )
                if isinstance(result, dict):
                    result.setdefault("routed_by", "llm_confirmed")
                    result.setdefault("skill", skill.name)
        else:
            self.pending_clarification = clarification  # re-arm, never infer
            result = {
                "success": False,
                "pending_clarification": True,
                "awaiting_llm_confirmation": True,
                "message": (
                    f"I didn't catch that. Reply 'yes' to run "
                    f"{name.replace('_', ' ')}, or 'no' to drop it."
                ),
            }

        return {
            "user_command": reply,
            "clarification_resumed": True,
            "intent_classification": {
                "predicted_intent": "llm_proposal", "confidence": 1.0,
                "llm_fallback": True, "clo": "CLO04",
            },
            "rl_routing": {"strategy": "llm_confirmation", "clo": "CLO05"},
            "execution_result": result,
        }

    def _answer_from_model(self, decision: Any) -> Dict[str, Any]:
        """Presents a stage-3 text answer, at exactly its real strength.

        The evidence is `ModelAnswered` and nothing stronger: a local model
        replied. That is not a lookup, not a check, and not an action — and the
        distinction is the whole reason the variant exists.

        `CognitiveResponseDict.__bool__` is the cautionary tale. It returned
        `True` unconditionally, so every failed dispatch was overwritten with a
        fabricated "🤖 Cognitive Response" success, including when no key was
        configured and no model had been asked anything at all. The prefix here
        is deliberate: a reader can tell a generated answer from an observed one
        without inspecting the evidence, and a reader who does inspect it finds
        the same claim.
        """
        return AgentResult.ok(
            f"💭 {decision.answer}",
            evidence=ModelAnswered(model=decision.model, host="local"),
            data={
                "intent": "llm_answer",
                "generated": True,
                "model": decision.model,
                "routing_reason": decision.reason,
                # The tick-mark stripping in `core/speech.py` would otherwise
                # read the 💭 out as decoration; the answer is already short.
                "speech": decision.answer,
            },
        ).as_dict()

    def _dispatch_to_agent(
        self,
        command: str,
        intent: str,
        user_approved: bool,
        confidence: float = 0.0,
        emit: Optional[Any] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Chooses a skill for the command and runs it.

        This method was ~520 lines of substring tests: `if "volume" in
        cmd_lower`, `elif "eth" in cmd_lower`, forty-odd branches deep, with
        `intent` — the output of component 2.1 — not consulted until roughly
        line 190 of it. Whichever branch appeared first won, so ordering was
        load-bearing and invisible, and a published 0.929 macro-F1 described a
        model that decided almost nothing.

        Every one of those branches is now a declared skill with declared
        patterns (`core/skills_builtin.py` and the tranche modules beside it),
        and this is the whole of the dispatch: refuse, help, route, run.
        """
        cmd_lower = command.lower().strip()

        # ── 1. Moral firewall ────────────────────────────────────────────────
        # In front of the router on purpose: a refusal must not depend on a
        # pattern matching. Substring tests are the right tool here — this is
        # the one place where matching part of a command is what is wanted.
        if any(k in cmd_lower for k in PROHIBITED_KEYWORDS):
            return {
                "success": False,
                "refusal": True,
                "message": (
                    f"❌ Security Refusal: Command '{command}' violates "
                    f"M.O.N.D.A.Y. Moral Firewall safety rules."
                ),
            }

        # ── 2. /help ─────────────────────────────────────────────────────────
        # Also in front, for the same reason: the capability menu is what the
        # user asks for when nothing else is working.
        if is_help_request(command):
            return {
                "success": True,
                "intent": "help_menu",
                "message": build_help_text(),
            }

        # ── 3. The router ────────────────────────────────────────────────────
        emit = _event_sink(emit)
        decision = self.router.route(
            command, intent=intent, confidence=confidence, emit=emit,
            history=list(self.recent_turns), memories=memories,
        )
        self.last_routing_decision = decision
        emit("routing", decision.as_dict())

        if not decision.routed:
            # Stage 3 may answer instead of choosing a skill. Presented as
            # generated text with `ModelAnswered` evidence — never as work done.
            if decision.stage == "llm_answer" and decision.answer:
                return self._answer_from_model(decision)
            return self._answer_unrouted(command, intent, decision)

        # A guess may answer, but it may not act. Stage 3 selected this skill
        # from a language model's reading of the command, and a model that picks
        # wrongly picks *plausibly* wrongly: asked to "shut down chrome for me
        # right now", a 3B selected `open_app_or_website` and MONDAY launched
        # Chrome — the opposite of the request, done without asking. The Tier-2
        # gate was not violated (nothing irreversible was reached) and that was
        # not enough, because "reversible" and "wanted" are different
        # properties.
        #
        # So a stage-3 selection of a skill that does anything but read is
        # proposed rather than performed. Patterns are exact and are unaffected.
        if decision.stage == "llm" and not decision.skill.read_only:
            return self._propose_llm_skill(command, decision)

        # `_command` carries the original text alongside the captured slots.
        # Several handlers need it to delegate to logic that parses the whole
        # command itself — contact saving, whose four validation guards must not
        # be reimplemented (handoff.md §9.2), and the email and WhatsApp
        # parsers, which are the best-tested code in the repo. Underscored so it
        # can never collide with a slot name.
        result = decision.skill.handler(_command=command, **decision.slots)
        if isinstance(result, dict):
            result.setdefault("routed_by", decision.stage)
            result.setdefault("skill", decision.skill.name)
        return result
