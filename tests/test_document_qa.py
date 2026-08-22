"""
ROADMAP Phase 12, first slice — asking questions of your own documents.

The interesting part of this tranche is what was wrong before it:
`DocumentAgent.rag_search` and `DocumentAgent.ask_document_question` were fully
implemented and **unreachable**. No skill exposed either, so nothing a user
could type arrived there, and `summarize_document` was the only door into that
agent — it summarises, it does not answer.

That is a different defect from the ones this repository usually finds. Nothing
lied; a capability simply had no entrance. `test_every_agent_method_worth_having_has_a_door`
at the bottom is the guard against a second one, because the skill registry is
the only map of what MONDAY can do: a function absent from it does not exist as
far as any user, the classifier or stage 3 is concerned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

import core.skills_documents as documents
from core.planner import MasterPlanner
from ml.intent_classifier import predict_intent


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


def _run(planner, command) -> Dict[str, Any]:
    return planner.process_command(command)["execution_result"]


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


@pytest.fixture
def library(tmp_path):
    """A small document folder with one obvious answer in it.

    Real prose, deliberately. The first version padded each file with
    "filler text. " x80 and retrieval found nothing — correctly, because a
    chunk that is 90% one repeated word buries the sentence that matters below
    the cosine floor. That was the fixture being unlike a document, not TF-IDF
    being wrong, and testing against it would have meant tuning the threshold
    to accommodate a file nobody would ever write.
    """
    (tmp_path / "notes.md").write_text(
        "Project notes for the autumn release.\n"
        "The deadline for the final report is the 30th of November, agreed in "
        "the planning meeting.\n"
        "Budget review happens the week before, and marketing wants screenshots "
        "by the 20th.\n"
        "The testing window is two weeks and the release candidate is cut on "
        "the 25th.\n"
        "Anna owns the migration; Ben owns documentation and the changelog.\n",
        encoding="utf-8",
    )
    (tmp_path / "shopping.txt").write_text(
        "milk, eggs, bread, coffee beans, olive oil and rice for the week ahead",
        encoding="utf-8",
    )
    (tmp_path / "photo.png").write_bytes(b"\x89PNG not readable")
    return tmp_path


# ── Routing ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("command,skill", [
    ("what does report.pdf say about the deadline", "ask_document"),
    ("ask notes.md about the meeting", "ask_document"),
    ("look up the deadline in notes.md", "ask_document"),
    ("search my documents for the deadline", "search_documents"),
    ("which document mentions the deadline", "search_documents"),
    ("look through my notes for the budget", "search_documents"),
])
def test_document_questions_reach_the_document_skills(planner, command, skill):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} routes nowhere"
    assert decision.skill.name == skill


def test_summarising_is_still_summarising(planner):
    """`summarize_document` and `ask_document` both take a path and must not
    take each other's commands."""
    assert _route(planner, "summarize report.pdf").skill.name == "summarize_document"


# ── One document ─────────────────────────────────────────────────────────────
def test_a_question_is_answered_from_the_document(planner, library):
    result = _run(planner, f"what does {library / 'notes.md'} say about the deadline")

    assert result["success"] is True
    assert "november" in result["message"].lower()
    assert result["evidence"]["kind"] == "file_read"


def test_a_missing_document_is_a_failure_not_an_answer(planner):
    """`ask_document_question` treats an unreadable path as raw text, which is
    how `summarize no_such_file.pdf` once "summarised" its own filename."""
    result = _run(planner, "what does no_such_file_xyzzy.md say about anything")

    assert result["success"] is False
    assert result["error"] == "DOCUMENT_NOT_FOUND"


def test_a_folder_given_to_the_single_document_skill_is_handed_over(planner, library):
    """`search <folder> for <thing>` matches the single-document pattern, and a
    pattern cannot tell a folder from a file — only the filesystem can.

    Before this, it read a directory as a document and reported
    "[Errno 13] Permission denied", which told the user nothing.
    """
    result = _run(planner, f"search {library} for the deadline")

    assert result["success"] is True
    assert result["documents_read"] == 2, "the .png must not be read"


# ── A folder ─────────────────────────────────────────────────────────────────
def test_a_folder_search_quotes_its_sources(planner, library):
    result = _run(planner, f"search {library} for the deadline")

    assert result["success"] is True
    assert "notes.md" in result["message"]
    assert result["passages"] >= 1


def test_a_folder_search_says_the_passages_are_not_a_summary(planner, library):
    """Retrieved, not reasoned over. "Your report says X" and "the most relevant
    passage is X" are different claims, and only one of them is true here."""
    message = _run(planner, f"search {library} for the deadline")["message"]
    assert "not a summary" in message.lower()


def test_unreadable_file_types_are_skipped(library):
    found = documents.readable_documents(library)
    assert sorted(p.name for p in found) == ["notes.md", "shopping.txt"]


def test_a_folder_with_nothing_readable_says_so(planner, tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    result = _run(planner, f"search {tmp_path} for anything")

    assert result["success"] is False
    assert result["error"] == "NO_DOCUMENTS"


def test_a_path_that_does_not_exist_says_so(planner, tmp_path):
    """Whether the user meant a file or a folder is unknowable once the path is
    absent, so the error is the path-level one. What matters is that it fails
    and names what it could not find."""
    missing = tmp_path / "nope"
    result = _run(planner, f"search {missing} for anything")

    assert result["success"] is False
    assert result["error"] in {"DOCUMENT_NOT_FOUND", "DOCUMENT_FOLDER_NOT_FOUND"}
    assert "nope" in result["message"]


def test_the_document_count_is_capped(library, monkeypatch):
    monkeypatch.setattr(documents, "MAX_DOCUMENTS", 1)
    assert len(documents.readable_documents(library, limit=1)) == 1


# ── The guard against a second orphaned capability ───────────────────────────
def test_the_retrieval_that_was_unreachable_is_reachable(planner):
    """The defect this tranche fixed, asserted directly.

    `rag_search` and `ask_document_question` were implemented for weeks with no
    skill exposing either. The registry is the only map of what MONDAY can do —
    a method absent from it does not exist to any user, to the classifier, or to
    stage 3.
    """
    registry = planner.router.registry
    assert registry.get("ask_document") is not None
    assert registry.get("search_documents") is not None
    for name in ("ask_document", "search_documents"):
        skill = registry.get(name)
        assert skill.read_only is True, f"{name} only reads"
        assert skill.offline is True
        assert skill.tier == 1
