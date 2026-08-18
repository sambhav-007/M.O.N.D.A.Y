"""
`/agent/stream` — the same pipeline, reported as it happens.

`/agent/execute` answers once, at the end. That is fine for a `psutil` reading
and wrong for anything slow: loading the local model takes a minute or more on a
cold start, and the UI aborted after **15 seconds**, so every first LLM-routed
command was cancelled before it could answer and the user saw "Execution request
timed out".

The property these tests exist to hold is not "events are emitted" — it is that
**streaming is the same pipeline observed, not a second one implemented.** A
parallel streaming path would have to agree with `process_command` about the
Tier-2 gate, the multi-turn clarification state machine and the RL credit, and
two implementations that must agree is the defect this repository has found in
its own code repeatedly (the email wizard existed twice, ~130 lines apart, with
different behaviour in each copy).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.planner import MasterPlanner


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


def _frames(response) -> List[Tuple[str, Dict[str, Any]]]:
    """Parses an SSE body into (event, payload) pairs."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    name, data = "message", ""
    for line in response.text.splitlines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data += line[5:].strip()
        elif not line:
            if data:
                out.append((name, json.loads(data)))
            name, data = "message", ""
    if data:
        out.append((name, json.loads(data)))
    return out


# ── The events ───────────────────────────────────────────────────────────────
def test_the_stream_reports_the_pipeline_in_order(client):
    res = client.post("/agent/stream", json={"command": "what time is it"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    kinds = [k for k, _ in _frames(res)]
    assert kinds[0] == "classified", "2.1's verdict should arrive first"
    assert "routing" in kinds
    assert kinds[-1] == "result", "the final payload must close the stream"


def test_the_classification_event_carries_what_the_model_decided(client):
    frames = dict(_frames(client.post("/agent/stream", json={"command": "battery"})))
    classified = frames["classified"]
    assert classified["intent"]
    assert 0.0 <= classified["confidence"] <= 1.0
    assert isinstance(classified["llm_fallback"], bool)


def test_the_routing_event_names_the_stage_and_the_skill(client):
    frames = dict(_frames(client.post("/agent/stream", json={"command": "what time is it"})))
    routing = frames["routing"]
    assert routing["stage"] == "pattern"
    assert routing["skill"] == "tell_time"


# ── The same pipeline, not a second one ──────────────────────────────────────
def test_the_streamed_result_is_identical_to_the_executed_one(client):
    """The claim the whole design rests on.

    Timestamps differ between two runs of a clock command, so this compares a
    command whose answer is stable.
    """
    command = {"command": "how many files are on my desktop"}
    streamed = dict(_frames(client.post("/agent/stream", json=command)))["result"]
    executed = client.post("/agent/execute", json=command).json()

    assert streamed["execution_result"]["message"] == executed["execution_result"]["message"]
    assert streamed["execution_result"]["skill"] == executed["execution_result"]["skill"]
    assert streamed["intent_classification"] == executed["intent_classification"]


def test_the_tier2_gate_still_arms_through_the_stream(client):
    """Streaming must not become a way around the confirmation.

    The gate lives in `process_command`, which the stream calls rather than
    reimplements — so this is a regression test for the *architecture*, not for
    the gate itself.
    """
    frames = dict(_frames(client.post("/agent/stream", json={"command": "kill notepad"})))
    result = frames["result"]["execution_result"]
    assert result.get("awaiting_tier2_approval") is True
    assert result.get("risk_tier") == 2
    assert result.get("executed") is not True

    # And it resolves normally on the next turn, also through the stream.
    after = dict(_frames(client.post("/agent/stream", json={"command": "no"})))
    assert after["result"]["execution_result"].get("cancelled") is True


def test_an_empty_command_streams_a_result_not_a_crash(client):
    frames = dict(_frames(client.post("/agent/stream", json={"command": "   "})))
    assert "result" in frames


# ── The sink itself ──────────────────────────────────────────────────────────
def test_process_command_is_unchanged_without_a_sink(planner):
    """The default is no observation and no behaviour change."""
    with_sink = planner.process_command("battery", on_event=lambda k, p: None)
    without = planner.process_command("battery")
    assert with_sink["execution_result"]["success"] == without["execution_result"]["success"]
    assert with_sink["intent_classification"]["predicted_intent"] == \
        without["intent_classification"]["predicted_intent"]


def test_a_sink_that_raises_cannot_break_the_command(planner):
    """A browser that closed mid-answer must not fail the command on the server —
    and must certainly not lose a Tier-2 gate that was about to be armed."""
    def hostile(kind: str, payload: Dict[str, Any]) -> None:
        raise RuntimeError("the consumer went away")

    result = planner.process_command("what time is it", on_event=hostile)
    assert result["execution_result"]["success"] is True


def test_the_sink_sees_every_stage_of_a_routed_command(planner):
    seen: List[str] = []
    planner.process_command("health", on_event=lambda k, p: seen.append(k))
    assert seen == ["classified", "routing"]


# ── Streaming from the model ─────────────────────────────────────────────────
def test_token_events_are_forwarded_from_the_model(planner, monkeypatch):
    """Text the model writes is emitted as it is produced.

    Stubbed, because what is being tested is the plumbing between the model and
    the sink. Worth knowing when reading this: with a 49-tool schema,
    `llama3.2:3b` selects a tool for essentially every command and writes free
    text almost never — so in practice this path fires rarely. It is still the
    right shape, and it is what makes a chatty model usable if the tool list
    ever shrinks.
    """
    class _Streaming:
        model = "stub-model"

        def choose(self, command: str, on_token: Any = None, history: Any = None,
                   memories: Any = None) -> Any:
            from core.llm import LlmChoice

            for fragment in ("Mon", "days ", "are ", "fine."):
                on_token(fragment)
            return LlmChoice(text="Mondays are fine.", model=self.model)

    original = planner.router.llm
    planner.router.llm = _Streaming()
    try:
        events: List[Tuple[str, Dict[str, Any]]] = []
        # Must be a command neither stage 1 nor stage 2 claims, or the model is
        # never consulted — which is the correct cascade, and is how the first
        # two versions of this test failed. "say something about mondays"
        # matches the `say {phrase}` voice pattern; "determination is important"
        # clears the 0.50 floor as `memory_query` and is taken by stage 2.
        result = planner.process_command(
            "i need to book a flight", on_event=lambda k, p: events.append((k, p))
        )
    finally:
        planner.router.llm = original

    tokens = [p["text"] for k, p in events if k == "token"]
    assert tokens == ["Mon", "days ", "are ", "fine."]
    assert ("consulting_model", {"model": "stub-model"}) in events
    assert "Mondays are fine." in result["execution_result"]["message"]


def test_streamed_and_unstreamed_choices_agree(planner):
    """The streaming and non-streaming paths converge before any decision.

    `_collect` reassembles a streamed response into the shape `_read` already
    understands, so tool validation sees identical input either way — streaming
    cannot become a second set of routing rules.
    """
    from core.llm import LlmStage

    stage = LlmStage(planner.router.registry)
    chunks = [
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "battery_status", "arguments": {}}}]}},
        {"message": {"content": ""}},
    ]
    collected = stage._collect(iter(chunks), lambda f: None)
    assert stage._read(collected).skill == "battery_status"
