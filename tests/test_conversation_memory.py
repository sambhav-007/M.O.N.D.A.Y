"""
Phase 6 — contacts as a table, and enough context to answer "and tell mum too".

Two changes with one theme: **the right data model beats a careful filter.**

`_resolve_phone_number` had four validation guards bolted onto a TF-IDF
similarity search, because that search could return a saved conversation
transcript when asked for a phone number — and once did, addressing a WhatsApp
message to a number lifted from an unrelated turn. The guards work. They also
have to be remembered by everyone who touches the code. A lookup that reads a
`contacts` table cannot return a transcript, because transcripts are not in that
table, and nobody has to remember anything.

The same shape applies to context: `auto_store_conversation_turn` was already
persisting every exchange, but retrieving the *previous* turn from a similarity
search over all turns is the wrong instrument. "and tell mum too" does not
resemble the turn it depends on; it follows it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from core.llm import LlmChoice
from core.planner import MAX_CONTEXT_MESSAGES, MasterPlanner


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clean(planner):
    planner.pending_clarification = None
    planner.recent_turns.clear()
    yield
    planner.pending_clarification = None
    planner.recent_turns.clear()


# ── The contacts table ───────────────────────────────────────────────────────
def test_a_contact_round_trips(planner):
    planner.memory_agent.save_contact("Testperson", phone="+919812345678")
    got = planner.memory_agent.get_contact("Testperson")
    assert got["phone"] == "+919812345678"


def test_lookup_is_case_insensitive_but_still_exact(planner):
    """Case is a spelling difference. A different name is a different person."""
    planner.memory_agent.save_contact("Bhumi", phone="+919812345670")
    assert planner.memory_agent.get_contact("bhumi")["phone"] == "+919812345670"
    assert planner.memory_agent.get_contact("BHUMI")["phone"] == "+919812345670"
    assert planner.memory_agent.get_contact("Bhumika") is None


def test_saving_twice_updates_rather_than_duplicating(planner):
    planner.memory_agent.save_contact("Dupe", phone="+911111111111")
    planner.memory_agent.save_contact("Dupe", phone="+912222222222")
    assert planner.memory_agent.get_contact("Dupe")["phone"] == "+912222222222"
    assert [c["name"] for c in planner.memory_agent.list_contacts()].count("Dupe") == 1


def test_a_later_email_does_not_erase_an_earlier_number(planner):
    """Blank fields leave the stored value alone — teaching one detail must not
    silently drop another."""
    planner.memory_agent.save_contact("Partial", phone="+913333333333")
    planner.memory_agent.save_contact("Partial", email="partial@example.com")
    row = planner.memory_agent.get_contact("Partial")
    assert row["phone"] == "+913333333333"
    assert row["email"] == "partial@example.com"


def test_a_contact_needs_a_name_and_something_to_store(planner):
    assert planner.memory_agent.save_contact("", phone="+91999")["error"] == "NO_CONTACT_NAME"
    assert planner.memory_agent.save_contact("Nobody")["error"] == "NO_CONTACT_DETAILS"


def test_the_lookup_cannot_return_a_conversation_transcript(planner, monkeypatch):
    """The bug the table exists to make impossible.

    `recall` is stubbed to return exactly the kind of row that caused it — a
    machine-written turn mentioning a number — and the contacts table is empty
    for that name. The resolver must find nothing rather than something.
    """
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda query, limit=8: {"matches": [{
            "key": "turn_20260817_101500",
            "value": "User: message +919998887777 saying hi | Assistant: opened chat",
        }]},
    )
    resolved = planner._resolve_phone_number("someone_with_no_saved_number")
    assert resolved["phone"] is None
    assert resolved["error"] == "NO_NUMBER"


def test_the_table_is_consulted_before_the_similarity_search(planner, monkeypatch):
    """Order matters: the typed record is the trustworthy one."""
    planner.memory_agent.save_contact("Ordering", phone="+919444444444")
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda query, limit=8: {"matches": [
            {"key": "ordering's number", "value": "+915555555555"}
        ]},
    )
    resolved = planner._resolve_phone_number("Ordering")
    assert resolved["phone"] == "919444444444"
    assert resolved["source"] == "saved contact"


def test_numbers_taught_before_the_table_existed_still_resolve(planner, monkeypatch):
    """The legacy path is kept for exactly this, behind its four guards.

    Deleting it would lose every contact a user taught before this change.
    """
    monkeypatch.setattr(
        planner.memory_agent, "get_contact", lambda name: None
    )
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda query, limit=8: {"matches": [
            {"key": "legacyperson's number", "value": "+919666666666"}
        ]},
    )
    resolved = planner._resolve_phone_number("legacyperson")
    assert resolved["phone"] == "919666666666"
    assert "remembered" in resolved["source"]


def test_teaching_a_number_by_command_writes_the_table(planner, monkeypatch):
    monkeypatch.setattr(planner.comms_agent, "open_whatsapp_chat",
                        lambda phone, text="": {"success": True, "message": "ok"})
    planner.process_command("chachu's number is 9812345671")
    row = planner.memory_agent.get_contact("chachu")
    assert row is not None and row["phone"].endswith("9812345671")


# ── Short-term conversation context ──────────────────────────────────────────
def test_a_turn_is_remembered_as_a_pair(planner):
    planner.process_command("what time is it")
    assert len(planner.recent_turns) == 2
    assert planner.recent_turns[0]["role"] == "user"
    assert planner.recent_turns[1]["role"] == "assistant"


def test_context_is_bounded(planner):
    """A 3B model's context is mostly spent on the 12 KB tool schema. Three
    exchanges is enough for "and tell mum too" and leaves room for the rest."""
    for _ in range(MAX_CONTEXT_MESSAGES):
        planner.process_command("what time is it")
    assert len(planner.recent_turns) == MAX_CONTEXT_MESSAGES


def test_a_long_reply_is_truncated_before_it_enters_the_context(planner):
    """`history` produces thousands of characters. Feeding an answer MONDAY
    already gave back into the model crowds out the schema it needs."""
    planner._remember_turn("show me everything", "x" * 5000)
    stored = planner.recent_turns[-1]["content"]
    assert len(stored) <= planner.MAX_CONTEXT_REPLY_CHARS + 1
    assert stored.endswith("…")


def test_the_model_receives_the_prior_turns(planner):
    """The point of the whole exercise.

    A follow-up like "and tell mum too" names no action and no recipient. Every
    stage before this one is stateless by design, so the only way it can mean
    anything is for stage 3 to see what came before it.
    """
    class _Recorder:
        model = "stub"
        unavailable_reason = ""

        def __init__(self) -> None:
            self.seen: List[Dict[str, str]] = []

        def choose(self, command: str, on_token: Any = None,
                   history: Optional[List[Dict[str, str]]] = None,
                   memories: Optional[List[Dict[str, Any]]] = None,
                   direct_answer: bool = False) -> Any:
            self.seen = list(history or [])
            return LlmChoice(skill="battery_status", model=self.model)

    recorder = _Recorder()
    original = planner.router.llm
    planner.router.llm = recorder
    try:
        planner.process_command("what time is it")
        planner.process_command("i need to book a flight")
    finally:
        planner.router.llm = original

    assert recorder.seen, "stage 3 was given no conversation context"
    assert recorder.seen[0]["role"] == "user"
    assert "what time is it" in recorder.seen[0]["content"]


def test_the_deterministic_stages_stay_stateless(planner):
    """Context goes to stage 3 only.

    A pattern that matched yesterday must match today, and a classifier whose
    answer depended on the previous command would make the published routing
    figure unreproducible.
    """
    planner.process_command("what time is it")
    planner.process_command("remember my exam is on friday")
    decision = planner.router.route("battery")
    assert decision.stage == "pattern"
    assert decision.skill.name == "battery_status"
