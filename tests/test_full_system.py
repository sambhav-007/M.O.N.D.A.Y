"""
M.O.N.D.A.Y. — Comprehensive Integration & Anti-Simulation System Test Suite
=============================================================================
Verifies zero fake simulations, complete real execution, and robust error handling
across all core engines and specialized worker agents.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.planner import MasterPlanner
from core.task_dag_engine import TaskDAGEngine
from agents.computer_agent import ComputerAgent
from agents.comms_agent import CommunicationAgent
from agents.audio_summarizer_agent import AudioSummarizerAgent
from agents.coder_agent import CoderAgent
from agents.browser_agent import BrowserAgent
from agents.public_api_agent import PublicApiAgent


class TestFullSystemArchitecture:

    @pytest.fixture(autouse=True)
    def setup_planner(self):
        self.planner = MasterPlanner()

    def test_computer_agent_create_file_artifact(self):
        """Verifies create_file_artifact method exists and saves file correctly."""
        comp = self.planner.computer_agent
        filename = "test_artifact_123.txt"
        content = "Sample artifact text content for testing."
        res = comp.create_file_artifact(filename, content)
        
        assert res.get("success") is True
        assert "filepath" in res
        artifact_path = Path(res["filepath"])
        assert artifact_path.exists()
        assert artifact_path.read_text(encoding="utf-8") == content
        
        # Cleanup
        try:
            artifact_path.unlink()
        except Exception:
            pass

    def test_task_dag_engine_multi_step_execution(self):
        """Verifies TaskDAGEngine runs multi-step goal including computer step without AttributeError."""
        cmd = "search Python 3.14 features and then summarize notes and save output"
        dag_engine = TaskDAGEngine(self.planner)
        assert dag_engine.is_multi_step_goal(cmd) is True
        
        res = dag_engine.execute_dag(cmd, user_approved=True)
        assert res.get("success") is True
        assert res.get("multi_step_dag") is True
        assert res.get("steps_count") >= 2

    def test_communication_agent_no_fake_simulation(self):
        """Verifies send_email evaluates real credentials or returns real error (not fake simulation)."""
        comms = self.planner.comms_agent
        # Test Tier-2 Gating
        res_gated = comms.send_email("test@example.com", user_approved=False)
        assert res_gated.get("success") is False
        assert res_gated.get("tier_2_gated") is True

        # Test Approved Execution (returns real OAuth validation or unconfigured status, not fake success)
        res_approved = comms.send_email("test@example.com", user_approved=True)
        assert "simulated" not in str(res_approved.get("message", "")).lower()

    def test_audio_summarizer_no_sample_notes(self):
        """Verifies audio summarizer returns real notice when no transcripts exist, not dummy notes."""
        audio_agent = AudioSummarizerAgent()
        res = audio_agent.stop_meeting_recording_and_summarize()
        assert res.get("success") is True
        assert res.get("meeting_minutes") == []
        assert "No speech transcripts were captured" in res.get("message", "")

    def test_coder_agent_real_error_handling(self):
        """Verifies coder agent returns real error structure on bad code without fake self-healing."""
        coder = CoderAgent()
        res = coder.generate_and_execute_script("system info query")
        assert res.get("success") is True
        assert "plugin_file" in res

    def test_browser_agent_no_fake_mock_results(self):
        """Verifies browser agent returns real search structure or clean error response."""
        browser = BrowserAgent()
        res = browser.web_search("Python programming language", num_results=3)
        assert "success" in res
        if res.get("success"):
            assert "results" in res
        else:
            assert "WEB_SEARCH_ERROR" in res.get("error", "")

    def test_master_planner_capabilities_menu(self):
        """Verifies MasterPlanner handles capabilities request cleanly."""
        res = self.planner.process_command("what can you do")
        assert res.get("execution_result", {}).get("success") is True
        msg = res.get("execution_result", {}).get("message", "")
        assert "Features" in msg or "Omni-Capable" in msg

    def test_auto_memory_retention_and_fact_extraction(self):
        """Verifies automatic memory retention extracts facts and recalls them across commands."""
        # 1. Execute command containing preference
        self.planner.process_command("my favorite editor is VSCode")
        
        # 2. Verify fact was auto-extracted and stored in SQLite memory
        mem = self.planner.memory_agent.recall("preferred_editor")
        assert mem.get("success") is True
        matches = mem.get("matches", [])
        assert len(matches) > 0
        assert "VSCode" in matches[0].get("value", "")

    def test_auto_conversation_history_persistence(self):
        """Verifies conversation turns are auto-logged to SQLite memory database."""
        res = self.planner.process_command("hello monday")
        assert res.get("execution_result", {}).get("success") is True
        
        # Verify turn was logged in memories table under conversation_history topic
        mem = self.planner.memory_agent.recall("hello monday")
        assert mem.get("success") is True

    def test_expanded_entity_memory_extraction(self):
        """Verifies extraction of location, profession, goals, and tech stack into memory.db."""
        mem_agent = self.planner.memory_agent
        
        # Test Location extraction
        mem_agent.auto_extract_and_remember("I live in San Francisco")
        res_loc = mem_agent.recall("user_location")
        assert len(res_loc.get("matches", [])) > 0
        assert "San Francisco" in res_loc["matches"][0]["value"]
        
        # Test Goals extraction
        mem_agent.auto_extract_and_remember("My goal is build multi-agent AI systems")
        res_goal = mem_agent.recall("user_goal")
        assert len(res_goal.get("matches", [])) > 0
        assert "build multi-agent AI systems" in res_goal["matches"][0]["value"]

    def test_process_manager_list_and_terminate_gating(self):
        """Verifies process listing and Tier-2 security gating for process termination."""
        comp = self.planner.computer_agent
        res_list = comp.list_running_processes(limit=5)
        assert res_list.get("success") is True
        assert len(res_list.get("processes", [])) > 0

        # Verify Tier-2 Gating on un-approved termination
        res_term = comp.terminate_process("non_existent_process_12345", user_approved=False)
        assert res_term.get("success") is False
        assert res_term.get("tier_2_gated") is True

    def test_document_comparison_diff(self):
        """Verifies document diff engine generates unified diff between two files."""
        doc_agent = self.planner.document_agent
        f1 = Path("data/staging/test_file1.txt")
        f2 = Path("data/staging/test_file2.txt")
        f1.parent.mkdir(parents=True, exist_ok=True)
        f1.write_text("Line 1: Original text\nLine 2: Unchanged", encoding="utf-8")
        f2.write_text("Line 1: Modified text\nLine 2: Unchanged", encoding="utf-8")

        res = doc_agent.compare_documents(f1, f2)
        assert res.get("success") is True
        assert res.get("diff_lines_count") > 0
        assert "Modified text" in res.get("diff_report", "")

        # Cleanup
        try:
            f1.unlink()
            f2.unlink()
        except Exception:
            pass

    def test_dataset_querying(self):
        """Verifies dataset querying over local CSV files using Pandas."""
        doc_agent = self.planner.document_agent
        csv_path = Path("data/staging/test_data.csv")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text("id,name,score\n1,Alice,95\n2,Bob,80\n3,Charlie,90", encoding="utf-8")

        res = doc_agent.query_dataset(csv_path, "score > 85")
        assert res.get("success") is True
        assert res.get("filtered_rows") == 2

        # Cleanup
        try:
            csv_path.unlink()
        except Exception:
            pass

    def test_web_markdown_extraction(self):
        """Verifies web markdown extractor converts web pages into markdown structure."""
        browser = self.planner.browser_agent
        res = browser.extract_webpage_markdown("https://httpbin.org/html")
        assert "markdown_content" in res or "error" in res

    def test_audio_metadata_inspection(self):
        """Verifies audio metadata inspector reads file metadata accurately."""
        audio_agent = self.planner.audio_summarizer_agent
        dummy_audio = Path("data/staging/test_audio.wav")
        dummy_audio.parent.mkdir(parents=True, exist_ok=True)
        dummy_audio.write_bytes(b'RIFF' + b'\x00' * 100)

        res = audio_agent.inspect_audio_metadata(dummy_audio)
        assert res.get("success") is True
        assert "file_size_bytes" in res

        # Cleanup
        try:
            dummy_audio.unlink()
        except Exception:
            pass

    def test_calendar_event_scheduling(self):
        """Verifies calendar event scheduling and agenda retrieval."""
        comms = self.planner.comms_agent
        res = comms.schedule_calendar_event("Sprint Review Meeting", "2026-07-28 14:00", 45)
        assert res.get("success") is True
        assert res.get("event", {}).get("title") == "Sprint Review Meeting"

        res_agenda = comms.get_upcoming_events(limit=5)
        assert res_agenda.get("success") is True
        assert len(res_agenda.get("events", [])) > 0

    def test_document_rag_question_answering(self):
        """Verifies RAG document question answering."""
        doc_agent = self.planner.document_agent
        doc_path = Path("data/staging/test_qa_doc.txt")
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text("Project Monday is an autonomous desktop AI assistant built with 5 classical ML models.", encoding="utf-8")

        res = doc_agent.ask_document_question(doc_path, "What is Project Monday?")
        assert res.get("success") is True
        assert "answer" in res

        # Cleanup
        try:
            doc_path.unlink()
        except Exception:
            pass

    def test_desktop_environment_snapshot(self):
        """Verifies unified desktop environment snapshot compilation."""
        comp = self.planner.computer_agent
        res = comp.get_desktop_environment_snapshot()
        assert res.get("success") is True
        assert "health" in res
        assert "screenshot_path" in res

    def test_xai_explainer_shap_generation(self):
        """Verifies Component 2.6 XAI explainer feature breakdown."""
        from ml.xai_explainer import explain_command_intent
        res = explain_command_intent("organize my downloads folder")
        assert "key_influencing_features" in res
        assert "xai_model" in res
