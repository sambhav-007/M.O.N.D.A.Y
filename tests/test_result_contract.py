"""
The result contract — `core/contracts.py`.

Two things are checked here, and the second matters more than the first.

1. `AgentResult` refuses to represent an unwitnessed success. That is the
   mechanism.
2. The handlers that have actually been migrated really do go through it. A
   contract nothing routes through proves nothing, which is the failure mode a
   guard test is most prone to.

The tools exercised below are read-only or fail closed — nothing here changes
system state, sends anything, or writes outside a temp directory.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.contracts import (
    AgentResult,
    FileWritten,
    HttpResponse,
    KeypressSent,
    ProcessExit,
    SystemQuery,
)
from core.tool_registry import ToolRegistry


# ── The mechanism ────────────────────────────────────────────────────────────
def test_success_without_evidence_is_unrepresentable():
    """The whole point: `{"success": True}` with nothing behind it cannot be built."""
    with pytest.raises(ValidationError, match="requires evidence"):
        AgentResult(success=True, message="✓ Done")


def test_failure_without_an_error_code_is_unrepresentable():
    """Callers branch on `error`, so a failure has to carry one."""
    with pytest.raises(ValidationError, match="requires an `error` code"):
        AgentResult(success=False, message="something went wrong")


def test_ok_requires_evidence_as_a_keyword():
    """`evidence` is keyword-only so it cannot be passed by accident or omitted."""
    with pytest.raises(TypeError):
        AgentResult.ok("done", ProcessExit(command="x", returncode=0))  # type: ignore[misc]


@pytest.mark.parametrize(
    "evidence",
    [
        ProcessExit(command="powershell", returncode=0),
        HttpResponse(status=200, url="https://example.invalid"),
        FileWritten(path="out.json", bytes_written=12),
        SystemQuery(source="psutil"),
        KeypressSent(key="ENTER", target_hint="WhatsApp"),
    ],
)
def test_every_evidence_variant_describes_itself(evidence):
    """`describe()` is what the audit log and the API show; none may be blank."""
    assert evidence.describe().strip()


def test_as_dict_matches_the_shape_callers_already_read():
    """
    Migration only stays cheap if `as_dict()` is a drop-in for the dicts the API,
    the UI and the existing tests consume: `success`, `message`, `error`, and
    payload keys flattened to the top level.
    """
    d = AgentResult.ok(
        "✓ Fetched.",
        evidence=HttpResponse(status=200, url="https://example.invalid"),
        data={"temperature": 21.4},
    ).as_dict()

    assert d["success"] is True
    assert d["message"] == "✓ Fetched."
    assert d["temperature"] == 21.4       # flattened, not nested under "data"
    assert "error" not in d               # absent rather than None
    assert d["evidence"]["kind"] == "http_response"
    assert d["evidence_summary"] == "HTTP 200 from https://example.invalid"


def test_unsupported_and_not_configured_are_different_answers():
    """
    "I can't do this at all" and "this works but isn't set up here" send the user
    to different places. Collapsing them into one cheerful success is how
    `read_latest_email` came to report an empty inbox it had never opened.
    """
    assert AgentResult.unsupported("fly").as_dict()["error"] == "NOT_IMPLEMENTED"
    assert (
        AgentResult.not_configured("Reading email", needs="OAuth").as_dict()["error"]
        == "NOT_CONFIGURED"
    )


# ── The migrated handlers ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def registry():
    return ToolRegistry()


def _assert_contract(result: dict, label: str):
    assert isinstance(result, dict), f"{label} did not return a dict"
    assert "success" in result, f"{label} has no success key"
    assert result.get("message"), f"{label} returned no message"
    if result["success"]:
        assert result.get("evidence"), (
            f"{label} claims success with no evidence — it must either witness "
            f"what it did or report the real outcome"
        )
        assert result.get("evidence_summary", "").strip()
    else:
        assert result.get("error"), f"{label} failed without an error code"


@pytest.mark.parametrize(
    "tool,kwargs",
    [
        ("list_processes", {"limit": 3}),          # succeeds: reads psutil
        ("toggle_smart_light", {}),                # fails: no IoT implementation
        ("read_latest_email", {}),                 # fails: Gmail not configured
        ("convert_csv_to_json", {"csv_path": "does_not_exist_xyz.csv"}),
        ("compare_files", {"file1": "nope_a.txt", "file2": "nope_b.txt"}),
        ("query_csv_json", {"filepath": "does_not_exist_xyz.csv"}),
    ],
)
def test_registry_tools_honour_the_contract(registry, tool, kwargs):
    _assert_contract(registry.execute_tool(tool, **kwargs), tool)


def test_convert_csv_to_json_witnesses_the_file_it_wrote(registry, tmp_path):
    """A success path, so the evidence has to name something that really exists."""
    csv = tmp_path / "rows.csv"
    csv.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    out = tmp_path / "rows.json"

    result = registry.execute_tool(
        "convert_csv_to_json", csv_path=str(csv), output_json_path=str(out)
    )

    _assert_contract(result, "convert_csv_to_json")
    assert result["success"] is True
    assert result["evidence"]["kind"] == "file_written"
    assert out.exists(), "evidence claims a file was written that is not there"
    assert result["evidence"]["bytes_written"] == out.stat().st_size


# ── Every agent, not just the registry ───────────────────────────────────────
# A migration is only as good as the check that it happened. Each call below is
# read-only or fails closed: nothing sends, deletes, spends, or writes outside a
# temp directory, and the network is blocked for the whole suite.
def test_all_agent_modules_import_the_contract():
    """
    A file that never imports `AgentResult` cannot be honouring it. This is a
    crude check and deliberately so — it fails loudly the moment a tenth agent
    is added without going through the contract.
    """
    import importlib
    import pkgutil

    import agents

    unmigrated = []
    for mod in pkgutil.iter_modules(agents.__path__):
        module = importlib.import_module(f"agents.{mod.name}")
        source = open(module.__file__, encoding="utf-8").read()
        if "AgentResult" not in source:
            unmigrated.append(mod.name)

    assert not unmigrated, (
        f"these agents still return raw dicts: {unmigrated}. Route them through "
        f"core.contracts.AgentResult — an unmigrated file is exactly where the "
        f"next fabricated success will live."
    )


def test_agent_calls_that_should_refuse_all_do(planner_agents):
    """
    The refusal paths, exercised for real. Each of these used to report success.
    """
    checks = [
        ("audio.start_meeting_recording", planner_agents["audio"].start_meeting_recording(), "NOT_IMPLEMENTED"),
        ("audio.stop_meeting_recording", planner_agents["audio"].stop_meeting_recording_and_summarize(), "NOT_IMPLEMENTED"),
        ("comms.read_latest_email", planner_agents["comms"].read_latest_email(), None),
        ("coder.unsupported_domain", planner_agents["coder"].generate_and_execute_script("negotiate world peace"), "NOT_IMPLEMENTED"),
    ]
    for label, result, expected_error in checks:
        _assert_contract(result, label)
        assert result["success"] is False, f"{label} should refuse"
        if expected_error:
            assert result["error"] == expected_error, f"{label}: {result['error']}"


def test_agent_read_paths_carry_evidence(planner_agents, tmp_path):
    """The success paths, exercised for real — each must witness what it read."""
    doc = tmp_path / "notes.txt"
    doc.write_text(
        "The quarterly review is on Friday at ten. "
        "Attendance is expected from the whole team.\n"
        "Budget questions should go to finance beforehand.\n",
        encoding="utf-8",
    )

    results = {
        "document.summarize": planner_agents["document"].summarize_document(str(doc)),
        "memory.recall": planner_agents["memory"].recall("nothing_matches_this_xyz"),
        "habit.detect": planner_agents["habit"].detect_habits_and_suggest(),
        "audio.summarize": planner_agents["audio"].summarize_audio_file(str(doc)),
    }
    for label, result in results.items():
        _assert_contract(result, label)


@pytest.fixture(scope="module")
def planner_agents():
    from agents.audio_summarizer_agent import AudioSummarizerAgent
    from agents.coder_agent import CoderAgent
    from agents.comms_agent import CommunicationAgent
    from agents.document_agent import DocumentAgent
    from agents.habit_agent import HabitAgent
    from agents.memory_agent import MemoryAgent

    return {
        "audio": AudioSummarizerAgent(),
        "coder": CoderAgent(),
        "comms": CommunicationAgent(),
        "document": DocumentAgent(),
        "habit": HabitAgent(),
        "memory": MemoryAgent(),
    }


# ── The specific fabrications this phase removed ─────────────────────────────
def test_smart_light_no_longer_invents_a_device(registry):
    """
    It used to return `success: True` and "✓ Smart Home IoT: Turned 'Living Room
    Light' ON." having done no I/O at all — no protocol, no address, no device.
    """
    res = registry.execute_tool("toggle_smart_light", device_name="Kitchen", state="on")
    assert res["success"] is False
    assert res["error"] == "NOT_IMPLEMENTED"
    assert "✓" not in res["message"]


def test_read_latest_email_no_longer_invents_a_message(registry):
    """
    It used to check whether `data/google_token.json` existed and, if it did,
    return a hardcoded subject and sender as though fetched from the inbox.
    """
    res = registry.execute_tool("read_latest_email")
    assert res["success"] is False
    assert res["error"] in {"NOT_CONFIGURED", "GMAIL_READ_FAILED"}
    assert "Project Monday Status Update" not in res["message"]


def test_change_volume_delegates_instead_of_ignoring_its_argument(registry):
    """
    The old copy never interpolated `level` into its PowerShell command, so 20%
    and 90% did the same thing and both reported the level they were asked for.
    It now delegates to the implementation that actually steps to a level, so the
    two functions cannot drift apart again.
    """
    tool = registry.get_tool("change_volume")
    assert tool is not None
    source = tool["func"].__doc__ or ""
    assert "set_system_volume" in source, "change_volume should delegate, not reimplement"
