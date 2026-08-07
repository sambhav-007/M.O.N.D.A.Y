"""
/help — trigger precision and content honesty.

Two things are being protected here:

1. The trigger is exact, not a substring. The previous intercept tested
   `"help" in cmd_lower`, so "help me summarize sample.pdf" printed the menu
   instead of summarising the file.
2. The menu does not promise capabilities the system lacks. The version it
   replaced advertised "signature mondayvoice.mp3 speech output" (the voice
   clone was abandoned — speech is gTTS) and a "Self-Evolution Plugin System"
   that "synthesizes generalized Python scripts" (the coder agent supports three
   fixed domains and refuses everything else).
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner, build_help_text, is_help_request
from core.security import TIER_2_IMPLEMENTED


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clear_state(planner):
    planner.pending_clarification = None
    yield
    planner.pending_clarification = None


# ── Trigger precision ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cmd",
    ["/help", "/?", "help", "help me", "?", "commands", "capabilities",
     "features", "what can you do", "menu", "HELP", "  /help  ", "help."],
)
def test_help_triggers(cmd):
    assert is_help_request(cmd) is True


@pytest.mark.parametrize(
    "cmd",
    [
        "help me summarize sample.pdf",
        "can you help me organize downloads",
        "what commands do i use for search",
        "search for helper libraries",
        "features of python 3.13",
        "remember that help is at extension 4",
        "",
    ],
)
def test_non_help_commands_are_not_hijacked(cmd):
    assert is_help_request(cmd) is False


def test_task_mentioning_help_still_routes_to_its_agent(planner):
    """The regression that motivated the exact-match trigger."""
    res = planner.process_command("help me summarize sample.pdf")
    assert res["execution_result"].get("intent") != "help_menu"
    assert res["intent_classification"]["predicted_intent"] == "document_intel"


# ── Content honesty ──────────────────────────────────────────────────────────
def test_help_does_not_claim_abandoned_or_fabricated_features():
    text = build_help_text().lower()
    # The voice clone was abandoned (Smart App Control blocks the FFmpeg XTTS
    # needs); replies are gTTS / browser speechSynthesis.
    assert "mondayvoice" not in text
    # The coder agent supports three fixed domains and honestly refuses the rest.
    assert "self-evolution" not in text
    assert "synthesizes generalized" not in text


def test_help_lists_only_genuinely_gated_tier2_actions():
    """The safety section must name the real gated set, not the policy list."""
    text = build_help_text()
    for action in TIER_2_IMPLEMENTED:
        assert action in text
    # These are policy placeholders with no implementation — never advertise them.
    for phantom in ("delete_file", "overwrite_file", "execute_shell"):
        assert phantom not in text


def test_help_flags_what_needs_setup():
    text = build_help_text().lower()
    assert "needs setup" in text
    assert "smtp" in text          # email sending is not configured by default
    assert "gemini" in text        # screen vision needs a key


def test_help_documents_the_tier2_contract():
    text = build_help_text().lower()
    assert "tier 2" in text
    assert "approve" in text or "asks" in text


# ── The examples in the menu must actually work ──────────────────────────────
@pytest.mark.parametrize(
    "example",
    ["health", "battery", "what time is it", "what is the date", "volume",
     "history", "proactive"],
)
def test_offline_help_examples_actually_run(planner, example):
    """
    A menu whose examples fail is as misleading as one that invents features.
    Limited to examples that need no network, no file argument and no side
    effect. 'history' and 'proactive' are here because they were CLI-only and
    returned "I'm not sure how to do that yet" in the app.
    """
    res = planner.process_command(example)["execution_result"]
    assert res.get("success") is True, f"help example failed: {example!r}"
    assert res.get("message"), f"help example returned no message: {example!r}"


# ── Help is always answerable ────────────────────────────────────────────────
def test_help_during_pending_confirmation_preserves_it(planner):
    """Asking what the options are must not drop a pending Tier-2 prompt."""
    planner.process_command("kill notepad")
    assert planner.pending_clarification is not None

    res = planner.process_command("/help")["execution_result"]
    assert res["intent"] == "help_menu"
    assert planner.pending_clarification is not None, "help swallowed the gate"

    # And the gate still resolves normally afterwards.
    after = planner.process_command("no")["execution_result"]
    assert after.get("cancelled") is True


def test_help_is_not_counted_as_an_approval(planner):
    """/help must never read as 'yes' to an irreversible action."""
    planner.process_command("kill notepad")
    res = planner.process_command("help")["execution_result"]
    assert res.get("approved_by_user") is not True
    assert res.get("executed") is not True
