"""
M.O.N.D.A.Y. — 100-Test Ruthless Adversarial & Edge-Case Test Suite
====================================================================
Exhaustive stress testing across security gating, adversarial prompts,
ML edge cases, worker agents, DAG engine, and FastAPI REST endpoints.
"""

from __future__ import annotations

import os
import sys
import pytest
from pathlib import Path
from typing import Any, Dict

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.planner import MasterPlanner
from core.security import evaluate_action_permission, classify_action_risk
from core.task_dag_engine import TaskDAGEngine
from core.tool_registry import ToolRegistry
from agents.computer_agent import ComputerAgent
from agents.comms_agent import CommunicationAgent
from agents.document_agent import DocumentAgent
from agents.browser_agent import BrowserAgent
from agents.memory_agent import MemoryAgent
from agents.coder_agent import CoderAgent
from agents.audio_summarizer_agent import AudioSummarizerAgent
from agents.voice_agent import VoiceAgent
from agents.public_api_agent import PublicApiAgent
from ml.intent_classifier import predict_intent, build_pipelines, INTENT_CLASSES
from ml.task_eta_regression import predict_eta, engineer_features, generate_action_log
from ml.memory_clustering import generate_memory_clusters
from ml.association_rules import encode_action_logs_to_transactions, mine_workflow_habits
from ml.rl_router import ContextualBanditRouter
from ml.xai_explainer import explain_command_intent


class TestRuthlessAdversarialSuite:

    @pytest.fixture(scope="class")
    def _shared_planner(self):
        """One planner for the class.

        This fixture was function-scoped, so all ~106 tests below built their own
        MasterPlanner — each one loading the ML pipelines from scratch and
        starting its own AutonomyDaemon thread. That was the majority of the
        suite's runtime and left a hundred daemon threads running. Construction
        is what is being shared; per-test state is reset below, which is the same
        arrangement test_tier2_gate.py uses.
        """
        return MasterPlanner()

    @pytest.fixture(autouse=True)
    def setup_planner(self, _shared_planner):
        self.planner = _shared_planner
        # No test may inherit another's half-finished conversation.
        _shared_planner.pending_clarification = None
        yield
        _shared_planner.pending_clarification = None

    # ── Category 1: Security Risk Gating & Adversarial Inputs (15 Tests) ─────────

    def test_security_tier_2_delete_file_gated(self):
        """Verifies delete_file requires explicit user approval."""
        res = evaluate_action_permission("delete_file", "important.docx")
        assert res["requires_approval"] is True
        assert res["risk_tier"] == 2

    def test_security_tier_2_send_email_gated(self):
        """Verifies send_email requires explicit user approval."""
        res = evaluate_action_permission("send_email", "boss@company.com")
        assert res["requires_approval"] is True
        assert res["risk_tier"] == 2

    def test_security_tier_2_execute_shell_gated(self):
        """Verifies execute_shell requires explicit user approval."""
        res = evaluate_action_permission("execute_shell", "rm -rf /")
        assert res["requires_approval"] is True
        assert res["risk_tier"] == 2

    def test_security_tier_2_terminate_process_gated(self):
        """Verifies terminate_process requires explicit user approval."""
        res = evaluate_action_permission("terminate_process", "chrome.exe")
        assert res["requires_approval"] is True
        assert res["risk_tier"] == 2

    def test_security_tier_1_organize_directory_autonomous(self):
        """Verifies organize_directory is Tier 1 autonomous."""
        res = evaluate_action_permission("organize_directory", ".")
        assert res["requires_approval"] is False
        assert res["risk_tier"] == 1

    def test_security_path_traversal_gating(self):
        """Verifies path traversal attempts trigger Tier 2 gating."""
        res = evaluate_action_permission("delete_file", "../../etc/passwd")
        assert res["requires_approval"] is True

    def test_adversarial_command_injection_prompt(self):
        """Verifies MasterPlanner handles command injection strings safely."""
        res = self.planner.process_command("; shutdown /s /t 0")
        assert "execution_result" in res

    def test_adversarial_sql_injection_memory_recall(self):
        """Verifies MemoryAgent handles SQL injection strings safely."""
        mem = self.planner.memory_agent
        res = mem.recall("' OR '1'='1' -- DROP TABLE memories;")
        assert res.get("success") is True

    def test_adversarial_xss_web_search_prompt(self):
        """Verifies BrowserAgent handles XSS prompt strings cleanly."""
        browser = self.planner.browser_agent
        res = browser.web_search("<script>alert('XSS')</script>")
        assert "results" in res or "error" in res

    def test_adversarial_path_traversal_document_reading(self):
        """Verifies DocumentAgent handles path traversal cleanly."""
        doc = self.planner.document_agent
        ok, text, err = doc.read_document_text("../../../non_existent_file.pdf")
        assert ok is False
        assert "not found" in err.lower() or "failed" in err.lower()

    def test_adversarial_empty_prompt_planner(self):
        """Verifies MasterPlanner handles empty string gracefully."""
        res = self.planner.process_command("   ")
        assert res.get("success") is False
        assert "empty" in res.get("error", "").lower()

    def test_adversarial_long_prompt_500_chars(self):
        """Verifies MasterPlanner handles 500+ character long prompt."""
        long_prompt = "please " * 100 + "organize my downloads folder"
        res = self.planner.process_command(long_prompt)
        assert "execution_result" in res

    def test_adversarial_unicode_chinese_prompt(self):
        """Verifies system handles Unicode Chinese text input cleanly."""
        res = self.planner.process_command("整理我的下载文件夹")
        assert "execution_result" in res

    def test_adversarial_emoji_prompt(self):
        """Verifies system handles prompt filled with emojis."""
        res = self.planner.process_command("📁🧹 Desktop clean up 🚀")
        assert "execution_result" in res

    def test_adversarial_negative_volume_setting(self, fake_powershell):
        """Verifies ComputerAgent handles negative volume input safely."""
        comp = self.planner.computer_agent
        res = comp.set_system_volume(-50)
        assert "success" in res
        # Clamped to 0 before it reached the shell, not passed through negative.
        assert "1..0 " in fake_powershell.last_command or "1..0}" in fake_powershell.last_command \
            or "1..0 |" in fake_powershell.last_command

    # ── Category 2: Task DAG Engine & Core Systems (15 Tests) ────────────────────

    def test_dag_engine_is_multi_step_goal_positive(self):
        """Verifies multi-step compound prompt detection."""
        dag = TaskDAGEngine(self.planner)
        assert dag.is_multi_step_goal("search AI news and then summarize and save output") is True

    def test_dag_engine_is_multi_step_goal_negative(self):
        """Verifies single-step prompt detection."""
        dag = TaskDAGEngine(self.planner)
        assert dag.is_multi_step_goal("what is the weather") is False

    def test_dag_engine_build_dag_node_count(self):
        """Verifies DAG node creation count matches compound steps."""
        dag = TaskDAGEngine(self.planner)
        nodes = dag.parse_command_to_dag("organize downloads and then search news and save report")
        assert len(nodes) >= 2

    def test_dag_engine_topological_execution_order(self):
        """Verifies step indices increase monotonically."""
        dag = TaskDAGEngine(self.planner)
        nodes = dag.parse_command_to_dag("search tech news and then summarize notes and save file")
        step_indices = [n.step_id for n in nodes]
        assert step_indices == sorted(step_indices)

    def test_tool_registry_singleton_instance(self):
        """Verifies ToolRegistry registration retains tools."""
        registry = ToolRegistry()
        tools = registry.list_tools()
        assert len(tools) >= 5

    def test_tool_registry_get_tool_existing(self):
        """Verifies tool lookup for existing tool."""
        registry = ToolRegistry()
        tool = registry.get_tool("change_volume")
        assert tool is not None

    def test_tool_registry_get_tool_missing(self):
        """Verifies tool lookup returns None for missing tool."""
        registry = ToolRegistry()
        tool = registry.get_tool("non_existent_super_tool_999")
        assert tool is None

    def test_autonomy_daemon_start_stop(self):
        """Verifies autonomy daemon thread lifecycle."""
        from core.autonomy import AutonomyDaemon
        daemon = AutonomyDaemon(check_interval_seconds=1.0)
        daemon.start()
        assert daemon.running is True
        daemon.stop()
        assert daemon.running is False

    def test_autonomy_daemon_scan_downloads(self):
        """Verifies autonomy daemon downloads folder scanner."""
        from core.autonomy import AutonomyDaemon
        daemon = AutonomyDaemon()
        res = daemon.scan_and_organize_downloads()
        assert "processed" in res
        assert "message" in res

    def test_security_classify_risk_tier1(self):
        """Verifies classify_action_risk for Tier 1 action."""
        tier, desc = classify_action_risk("get_system_health")
        assert tier == 1

    def test_security_classify_risk_tier2(self):
        """Verifies classify_action_risk for Tier 2 action."""
        tier, desc = classify_action_risk("execute_shell")
        assert tier == 2

    def test_planner_pending_clarification_reset(self):
        """Verifies new command clears pending clarification state."""
        self.planner.pending_clarification = {"type": "select_email"}
        self.planner.process_command("what is the weather in Tokyo")
        assert self.planner.pending_clarification is None

    def test_planner_boot_context_scan(self):
        """Verifies boot context scanning returns non-empty dict."""
        boot = self.planner.system_boot_scan()
        assert "user" in boot

    def test_planner_voice_toggle(self):
        """Verifies voice output toggle in MasterPlanner."""
        self.planner.enable_voice = False
        assert self.planner.enable_voice is False
        self.planner.enable_voice = True
        assert self.planner.enable_voice is True

    def test_planner_direct_dispatch_fallback(self):
        """Verifies planner handles unknown random command via fallback."""
        res = self.planner.process_command("xyzzyspoon12345")
        assert res.get("execution_result") is not None

    # ── Category 3: 6 Classical ML Pipelines Edge Cases (15 Tests) ─────────────

    def test_ml_intent_classifier_predict_known(self):
        """Verifies intent prediction on standard organize command."""
        intent, conf, fallback = predict_intent(self.planner.classifier, "organize my files")
        assert intent in INTENT_CLASSES
        assert conf > 0.0

    def test_ml_intent_classifier_predict_unseen_words(self):
        """Verifies intent classifier on completely unseen gibberish."""
        intent, conf, fallback = predict_intent(self.planner.classifier, "qwertyuiop asdfghjkl")
        assert intent in INTENT_CLASSES

    def test_ml_task_eta_regressor_predict_standard(self):
        """Verifies ETA regressor output format."""
        eta = predict_eta("organize_files", "computer", step_count=2)
        assert eta > 0.0

    def test_ml_task_eta_regressor_zero_steps(self):
        """Verifies ETA regressor handles step_count=0."""
        eta = predict_eta("organize_files", "computer", step_count=0)
        assert eta >= 0.5

    def test_ml_task_eta_regressor_high_step_count(self):
        """Verifies ETA regressor handles step_count=50."""
        eta = predict_eta("complex_workflow", "coder", step_count=50)
        assert eta > 5.0

    def test_ml_memory_clustering_k_means(self):
        """Verifies K-Means memory clustering generation."""
        res = generate_memory_clusters(n_clusters=3)
        assert res.get("success") is True
        assert "clusters" in res

    def test_ml_memory_clustering_dbscan(self):
        """Verifies DBSCAN memory clustering generation."""
        res = generate_memory_clusters(n_clusters=2)
        assert len(res.get("clusters", [])) > 0

    def test_ml_association_rules_mining(self):
        """Verifies Apriori workflow habit mining."""
        df_logs = generate_action_log(n_samples=500)
        transactions = encode_action_logs_to_transactions(df_logs)
        res = mine_workflow_habits(transactions, min_support=0.01, min_confidence=0.1)
        assert res.get("success") is True

    def test_ml_association_rules_empty_transactions(self):
        """Verifies habit miner handles empty transaction list."""
        res = mine_workflow_habits([], min_support=0.1)
        assert res.get("success") is True
        assert res.get("rules_count") == 0

    def test_ml_rl_bandit_select_action(self):
        """Verifies RL bandit action index within bounds."""
        router = ContextualBanditRouter(n_arms=3)
        act = router.select_action()
        assert act in [0, 1, 2]

    def test_ml_rl_bandit_update_reward(self):
        """Verifies RL bandit reward update."""
        router = ContextualBanditRouter(n_arms=3)
        router.update(0, reward=1.0)
        assert router.pull_counts[0] == 1
        assert router.q_values[0] == 1.0

    def test_ml_rl_bandit_decay_exploration(self):
        """Verifies epsilon decay after multiple updates."""
        router = ContextualBanditRouter(n_arms=3, epsilon=1.0, epsilon_decay=0.9)
        for _ in range(10):
            act = router.select_action()
            router.update(act, 1.0)
        assert router.epsilon < 1.0

    def test_ml_xai_explainer_command_breakdown(self):
        """Verifies XAI SHAP feature explanation for prompt."""
        res = explain_command_intent("summarize pdf document")
        assert "key_influencing_features" in res
        assert len(res["key_influencing_features"]) > 0

    def test_ml_xai_explainer_empty_command(self):
        """Verifies XAI explainer handles empty command string."""
        res = explain_command_intent("")
        assert "key_influencing_features" in res

    def test_ml_pipelines_all_models_trained(self):
        """Verifies MasterPlanner pre-loads classifier."""
        assert self.planner.classifier is not None

    # ── Category 4: Worker Agents Exhaustive Verification (20 Tests) ──────────────

    def test_agent_computer_get_system_volume(self):
        """Verifies the volume query reports honestly.

        This used to assert `success is True`, which only held because the
        fallback returned a hardcoded `volume: 50` as though it were a reading —
        and the fallback was the only path that ever ran, since
        `Win32_AudioDevice` exposes no `Volume` property. Either outcome is fine
        now; what must not happen is a success carrying an invented number.
        """
        comp = self.planner.computer_agent
        res = comp.get_system_volume()
        if res.get("success"):
            assert res.get("evidence"), "a volume reading must say where it came from"
            assert isinstance(res.get("volume"), int)
        else:
            assert res.get("error") == "VOLUME_READ_UNSUPPORTED"
            assert "volume" not in res, "a failed read must not report a number"

    def test_agent_computer_battery_status(self):
        """Verifies battery status query."""
        comp = self.planner.computer_agent
        res = comp.get_battery_status()
        assert res.get("success") is True

    def test_agent_computer_network_info(self):
        """Verifies local IP network query."""
        comp = self.planner.computer_agent
        res = comp.get_network_info()
        assert res.get("success") is True
        assert "local_ip" in res

    def test_agent_document_read_txt_file(self):
        """Verifies text file reading."""
        doc = self.planner.document_agent
        txt_path = Path("data/staging/test_read.txt")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text("Hello document agent test", encoding="utf-8")
        ok, text, err = doc.read_document_text(txt_path)
        assert ok is True
        assert "Hello" in text
        try: txt_path.unlink()
        except Exception: pass

    def test_agent_document_summarize_empty_text(self):
        """Verifies document summarizer handles empty string."""
        doc = self.planner.document_agent
        res = doc.summarize_document("")
        assert res.get("success") is False

    def test_agent_browser_fetch_page_http_error(self):
        """Verifies browser agent returns error for invalid domain."""
        browser = self.planner.browser_agent
        res = browser.fetch_webpage_content("https://invalid_domain_name_123456789.org")
        assert res.get("success") is False

    @pytest.mark.network
    def test_agent_browser_research_topic(self):
        """Verifies browser research synthesis.

        NO CASSETTE YET — DuckDuckGo was returning nothing for this machine on
        2026-08-08 (the rate-limiting the README documents), and a cassette
        recorded from a challenge page would assert that the rate limit still
        applies. Record with `-m network --record-mode=once` once DDG cooperates.
        """
        browser = self.planner.browser_agent
        res = browser.research_topic("Python")
        assert res.get("success") is True

    def test_agent_comms_read_latest_email(self):
        """Verifies the inbox reader does not invent an answer.

        This used to assert `success is True`, which held only because the
        no-credentials branch returned "✓ Inbox check complete: 0 unread
        messages." — a statement about the user's mailbox made without opening
        it. Without Gmail configured the honest answer is NOT_CONFIGURED.
        """
        comms = self.planner.comms_agent
        res = comms.read_latest_email()
        if res.get("success"):
            assert res.get("evidence"), "a real inbox read must be witnessed"
        else:
            assert res.get("error") in {"NOT_CONFIGURED", "GMAIL_READ_FAILED"}
            assert "0 unread" not in res.get("message", "")

    def test_agent_comms_list_contacts(self):
        """Verifies contact list resolution."""
        comms = self.planner.comms_agent
        contacts = comms.get_contacts()
        assert isinstance(contacts, list)

    def test_agent_memory_remember_and_recall_exact(self):
        """Verifies exact key memory recall."""
        mem = self.planner.memory_agent
        mem.remember("test_key_abc", "test_val_xyz", topic="test")
        res = mem.recall("test_key_abc")
        assert res.get("success") is True
        assert len(res.get("matches", [])) > 0

    def test_agent_memory_get_proactive_suggestions(self):
        """Verifies proactive memory suggestions."""
        mem = self.planner.memory_agent
        res = mem.get_proactive_suggestions()
        assert res.get("success") is True
        assert len(res.get("suggestions", [])) > 0

    def test_agent_coder_generate_script_system_info(self):
        """Unsupported domains must fail honestly, not fabricate a compiled plugin."""
        coder = CoderAgent()
        res = coder.generate_and_execute_script("system info query")
        assert res.get("success") is False
        assert "not sure how to do that yet" in res.get("message", "")

    def test_agent_coder_generate_script_supported_domain(self):
        """A domain with a real implementation still executes."""
        coder = CoderAgent()
        res = coder.generate_and_execute_script("create a desktop folder")
        assert res.get("success") is True
        assert res.get("domain") == "desktop_folder"

    def test_agent_coder_filesystem_search(self):
        """Unsupported filesystem tasks report honestly instead of faking success."""
        coder = CoderAgent()
        res = coder.execute_filesystem_task("find txt files")
        assert res.get("success") is False
        assert "not sure how to do that yet" in res.get("message", "")

    def test_agent_audio_stop_meeting_recording(self):
        """Verifies audio summarizer meeting stop."""
        audio = AudioSummarizerAgent()
        res = audio.stop_meeting_recording_and_summarize()
        assert res.get("success") is True

    def test_agent_audio_summarize_notes(self):
        """Verifies audio summarizer file notes processing."""
        audio = AudioSummarizerAgent()
        res = audio.summarize_audio_file("Discussed project timeline and deliverables for next sprint.")
        assert res.get("success") is True

    def test_agent_voice_toggle_state(self):
        """Verifies voice agent state toggle."""
        voice = VoiceAgent(enable_voice=False)
        assert voice.enable_voice is False
        voice.set_voice_enabled(True)
        assert voice.enable_voice is True

    @pytest.mark.vcr
    def test_agent_public_api_fetch_weather(self):
        """Verifies Open-Meteo weather API call."""
        api_agent = PublicApiAgent()
        res = api_agent.get_weather("London")
        assert res.get("success") is True

    @pytest.mark.vcr
    def test_agent_public_api_fetch_crypto(self):
        """Verifies CoinGecko crypto API call."""
        api_agent = PublicApiAgent()
        res = api_agent.get_crypto_prices("bitcoin")
        assert res.get("success") is True

    @pytest.mark.network
    def test_agent_public_api_fetch_iss_location(self):
        """Verifies ISS location API call.

        NO CASSETTE YET. `api.open-notify.org` was unreachable on 2026-08-08 when
        the rest of these were recorded, and a cassette recorded from a timeout
        pins the timeout rather than the parsing. Record it the next time the
        host answers:

            py -3.12 -m pytest tests/test_100_ruthless.py -k iss_location \\
                -m network --record-mode=once

        then swap this marker for `@pytest.mark.vcr`. Until then it is opt-in, so
        an unreachable third party cannot redden the default suite.
        """
        api_agent = PublicApiAgent()
        res = api_agent.get_iss_location()
        assert res.get("success") is True

    @pytest.mark.vcr
    def test_agent_public_api_wikipedia_summary(self):
        """Verifies Wikipedia summary API call."""
        api_agent = PublicApiAgent()
        res = api_agent.get_wikipedia_summary("Artificial Intelligence")
        assert res.get("success") is True

    # ── Category 5: Extended System & API Ruthless Verification (40 Tests) ────────

    def test_agent_computer_list_running_processes(self):
        """Verifies process manager lists host system processes."""
        comp = self.planner.computer_agent
        res = comp.list_running_processes()
        assert res.get("success") is True
        assert len(res.get("top_processes", [])) > 0

    def test_agent_computer_terminate_process_tier2(self):
        """Verifies process termination requires user_approved=True."""
        comp = self.planner.computer_agent
        res = comp.terminate_process(12345, user_approved=False)
        assert res.get("requires_approval") is True

    def test_agent_document_compare_documents_diff(self):
        """Verifies document diff comparison engine."""
        doc = self.planner.document_agent
        p1 = Path("data/staging/doc1.txt")
        p2 = Path("data/staging/doc2.txt")
        p1.parent.mkdir(parents=True, exist_ok=True)
        p1.write_text("Line A\nLine B", encoding="utf-8")
        p2.write_text("Line A\nLine C", encoding="utf-8")
        res = doc.compare_documents(p1, p2)
        assert res.get("success") is True
        assert "diff" in res
        try: p1.unlink(); p2.unlink()
        except Exception: pass

    def test_agent_document_query_dataset_pandas(self):
        """Verifies pandas dataset SQL-style query."""
        doc = self.planner.document_agent
        csv_p = Path("data/staging/test_df.csv")
        csv_p.parent.mkdir(parents=True, exist_ok=True)
        csv_p.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")
        res = doc.query_dataset(csv_p, query_expr="age > 26")
        assert res.get("success") is True
        assert res.get("row_count") == 1
        try: csv_p.unlink()
        except Exception: pass

    def test_agent_browser_extract_webpage_markdown(self):
        """Verifies HTML to markdown web page converter."""
        browser = self.planner.browser_agent
        res = browser.extract_webpage_markdown("https://example.com")
        assert res.get("success") is True or "error" in res

    def test_agent_audio_inspect_audio_metadata(self):
        """Verifies audio metadata inspector."""
        audio = AudioSummarizerAgent()
        res = audio.inspect_audio_metadata("ui/mondayvoice.mp3")
        assert res.get("success") is True

    def test_agent_comms_schedule_calendar_event(self):
        """Verifies calendar event scheduling."""
        comms = self.planner.comms_agent
        res = comms.schedule_calendar_event("Project Review", "2026-08-01 10:00", 60)
        assert res.get("success") is True

    def test_agent_comms_get_upcoming_events(self):
        """Verifies querying scheduled calendar events."""
        comms = self.planner.comms_agent
        res = comms.get_upcoming_events()
        assert res.get("success") is True

    def test_agent_memory_auto_extract_and_remember(self):
        """Verifies automated NLP entity extraction and memory storage."""
        mem = self.planner.memory_agent
        res = mem.auto_extract_and_remember("I am a Data Scientist located in Seattle building Python apps.")
        assert res.get("success") is True

    def test_agent_memory_auto_store_conversation_turn(self):
        """Verifies conversation history turn logging into SQLite."""
        mem = self.planner.memory_agent
        res = mem.auto_store_conversation_turn("hello", "hi there", agent_name="MasterPlanner")
        assert res.get("success") is True

    def test_agent_coder_self_healing_execution(self):
        """Verifies coder agent reports unsupported requests rather than faking a run."""
        coder = CoderAgent()
        res = coder.generate_and_execute_script("print system datetime")
        assert res.get("success") is False
        assert "not sure how to do that yet" in res.get("message", "")

    def test_api_health_endpoint(self):
        """Verifies API server health route handler."""
        from api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json().get("status") == "ONLINE"

    def test_api_xai_explain_endpoint(self):
        """Verifies API server /xai/explain route handler."""
        from api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        res = client.get("/xai/explain?command=clean%20desktop")
        assert res.status_code == 200
        assert "key_influencing_features" in res.json()

    def test_api_agent_execute_endpoint(self):
        """Verifies API server /agent/execute route handler."""
        from api.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        res = client.post("/agent/execute", json={"command": "what is the time"})
        assert res.status_code == 200

    def test_cognitive_engine_generate_response(self):
        """Verifies TriModelCognitiveEngine generative reasoning."""
        res = self.planner.cognitive_engine.generate_cognitive_response(
            prompt="summarize workflow",
            retrieved_memories=["User prefers Python"],
            boot_context={"user": "Siddhant"}
        )
        assert "response" in res
        assert res.get("cognitive_engine_active") is True

    def test_planner_capabilities_menu(self):
        """Verifies MasterPlanner capabilities menu prompt."""
        res = self.planner.process_command("what can you do")
        assert "execution_result" in res
        assert res.get("execution_result", {}).get("success") is True

    def test_document_agent_ask_document_question(self):
        """Verifies document agent RAG passage QA engine."""
        doc = self.planner.document_agent
        txt_path = Path("data/staging/sample_doc.txt")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text("M.O.N.D.A.Y. is an advanced AI assistant built in Python.", encoding="utf-8")
        res = doc.ask_document_question("What language is M.O.N.D.A.Y built in?", document_paths=[str(txt_path)])
        assert res.get("success") is True
        try: txt_path.unlink()
        except Exception: pass

    def test_computer_agent_desktop_snapshot(self):
        """Verifies computer agent desktop environment snapshot."""
        comp = self.planner.computer_agent
        res = comp.get_desktop_environment_snapshot()
        assert res.get("success") is True

    def test_voice_agent_train_from_reference(self):
        """Verifies voice agent training from reference audio file."""
        voice = VoiceAgent()
        res = voice.train_voice("ui/mondayvoice.mp3")
        assert res.get("success") is True

    @pytest.mark.vcr
    def test_public_api_geolocation_query(self):
        """Verifies PublicApiAgent IP geolocation fetch."""
        api_agent = PublicApiAgent()
        res = api_agent.get_geolocation()
        assert res.get("success") is True

    def test_memory_agent_get_contextual_memories(self):
        """Verifies memory pre-fetching for prompt."""
        mem = self.planner.memory_agent
        res = mem.get_contextual_memories("python project")
        assert isinstance(res, list)

    def test_security_override_tier2_user_approved(self):
        """Verifies Tier 2 gating override when user_approved=True."""
        res = evaluate_action_permission("delete_file", "test.txt", user_approved=True)
        assert res["requires_approval"] is False

    def test_autonomy_daemon_scan_logs(self):
        """Verifies autonomy daemon log scanner."""
        from core.autonomy import AutonomyDaemon
        daemon = AutonomyDaemon()
        res = daemon.scan_and_organize_downloads()
        assert "processed" in res

    def test_task_dag_engine_execute_dag(self):
        """Verifies multi-step DAG execution pipeline."""
        dag = TaskDAGEngine(self.planner)
        res = dag.execute_dag("search python news and then summarize notes", user_approved=True)
        assert res.get("success") is True

    def test_coder_agent_generate_script_filesystem(self):
        """Verifies script generation for file search."""
        coder = CoderAgent()
        res = coder.generate_and_execute_script("list files in current directory")
        assert res.get("success") is True

    @pytest.mark.network
    def test_browser_agent_deep_research(self):
        """Verifies browser agent deep research topic aggregation.

        NO CASSETTE YET — same DuckDuckGo rate limit as
        `test_agent_browser_research_topic`.
        """
        browser = self.planner.browser_agent
        res = browser.research_topic("Machine Learning")
        assert res.get("success") is True

    def test_comms_agent_read_contacts(self):
        """Verifies communication agent contact retrieval."""
        comms = self.planner.comms_agent
        res = comms.get_contacts()
        assert len(res) >= 0

    def test_document_agent_read_pdf_fallback(self):
        """Verifies document agent PDF reading fallback logic."""
        doc = self.planner.document_agent
        ok, text, err = doc.read_document_text("data/staging/non_existent.pdf")
        assert ok is False

    def test_audio_summarizer_inspect_metadata_missing(self):
        """Verifies audio inspector on missing file."""
        audio = AudioSummarizerAgent()
        res = audio.inspect_audio_metadata("data/staging/non_existent.mp3")
        assert res.get("success") is False

    def test_voice_cloner_synthesize_speech_empty(self):
        """Verifies voice cloner handles empty text."""
        from ml.voice_cloner import MondayVoiceModel
        cloner = MondayVoiceModel()
        res = cloner.synthesize_speech("")
        assert res.get("success") is False

    @pytest.mark.vcr
    def test_public_api_fetch_weather_empty_city(self):
        """Verifies weather API handles empty city string."""
        api_agent = PublicApiAgent()
        res = api_agent.fetch_weather("")
        assert res.get("success") is True

    def test_memory_agent_remember_empty_key(self):
        """Verifies memory agent handles empty key gracefully."""
        mem = self.planner.memory_agent
        res = mem.remember("", "value")
        assert res.get("success") is False

    def test_computer_agent_set_volume_valid(self, fake_powershell):
        """Verifies valid volume setting."""
        comp = self.planner.computer_agent
        res = comp.set_system_volume(50)
        assert res.get("success") is True
        assert res["evidence"]["kind"] == "process_exit"
        assert res["evidence"]["returncode"] == 0

    def test_tool_registry_list_tools_format(self):
        """Verifies ToolRegistry output schema."""
        registry = ToolRegistry()
        tools = registry.list_tools()
        assert isinstance(tools, (list, dict))

    @pytest.mark.network
    def test_planner_process_command_search(self):
        """Verifies search command processing in MasterPlanner.

        Marked `network` even though nothing here calls out directly. "search
        current AI news" classifies as `desktop_automation` at 0.33 confidence,
        which routes to CoderAgent, which writes a `web_scraper` script and runs
        it in a **subprocess** — and a subprocess is outside the reach of
        `--block-network`, which only patches sockets in this interpreter. The
        script then blocks on a live fetch until CoderAgent's 20s timeout, twice
        (`max_retries=2`), so this single test cost 40s of the suite's runtime
        and was the last live-network dependency in the default selection.

        The routing itself is the real defect and is not fixed here — see
        UPGRADE_PLAN.md §1.2. The marker stops it distorting the suite meanwhile.
        """
        res = self.planner.process_command("search current AI news")
        assert res.get("execution_result") is not None

    def test_planner_process_command_organize(self):
        """Verifies organize command processing in MasterPlanner."""
        res = self.planner.process_command("organize files")
        assert res.get("execution_result") is not None

    def test_planner_process_command_calendar(self):
        """Verifies calendar command processing in MasterPlanner."""
        res = self.planner.process_command("schedule a meeting tomorrow at 10am")
        assert res.get("execution_result") is not None

    def test_planner_process_command_weather(self):
        """Verifies weather command processing in MasterPlanner."""
        res = self.planner.process_command("what is the weather in Paris")
        assert res.get("execution_result") is not None

    def test_planner_process_command_email(self):
        """Verifies draft email command processing in MasterPlanner."""
        res = self.planner.process_command("draft email to john@example.com hello")
        assert res.get("execution_result") is not None

    def test_full_system_harness_benchmark_clean(self):
        """Verifies system harness benchmark execution."""
        from harness import run_system_harness
        res = run_system_harness()
        assert res.get("status") == "clean"

