"""
WhatsApp messaging — parsing, number resolution, and the Tier-2 boundary.

WhatsApp has no API a desktop script may send through. The official deep link
opens a chat with the message pre-typed but deliberately will not send it. So
there are two behaviours and the split between them is the thing worth testing:

  prepare (Tier 1)  opens the chat with the text typed; nothing leaves the machine
  send    (Tier 2)  additionally simulates Enter, which really does send

Nothing here may actually launch WhatsApp, so both agent calls are stubbed.
"""

from __future__ import annotations

import pytest

from agents.comms_agent import CommunicationAgent
from core.planner import MasterPlanner
from core.security import TIER_2_ACTIONS, TIER_2_IMPLEMENTED, classify_action_risk


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def stub_whatsapp(planner, monkeypatch):
    """Never open the real app. Records what would have happened."""
    planner.pending_clarification = None
    calls = {"opened": [], "sent": []}

    monkeypatch.setattr(
        planner.comms_agent, "open_whatsapp_chat",
        lambda phone, text="": calls["opened"].append((phone, text)) or {
            "success": True, "phone": phone, "text": text,
            "message_sent": False, "message": f"opened +{phone}",
        },
    )
    monkeypatch.setattr(
        planner.comms_agent, "send_whatsapp_now",
        lambda phone, text: calls["sent"].append((phone, text)) or {
            "success": True, "phone": phone, "text": text,
            "enter_sent": True, "delivery_confirmed": False,
            "message": f"pressed Enter for +{phone}",
        },
    )
    yield calls
    planner.pending_clarification = None


def _exec(res):
    return res["execution_result"]


# ── Phone normalisation ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+919876543210", "919876543210"),
        ("+91 98765 43210", "919876543210"),
        ("919876543210", "919876543210"),
        ("+1 (555) 123-4567", "15551234567"),
    ],
)
def test_normalise_phone_accepts_real_numbers(raw, expected):
    assert CommunicationAgent.normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", ["bhumi", "12345", "", "not a number", None])
def test_normalise_phone_rejects_non_numbers(raw):
    assert CommunicationAgent.normalise_phone(raw) is None


# ── Command parsing ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "command,target,text",
    [
        ("message +919876543210 saying hello there", "+919876543210", "hello there"),
        ("send whatsapp to bhumi saying hello", "bhumi", "hello"),
        ("open whatsapp and message bhumi hi", "bhumi", "hi"),
        ("whatsapp message bhumi saying hi", "bhumi", "hi"),
        ("message bhumi hi", "bhumi", "hi"),
        ("text +919876543210 hello", "+919876543210", "hello"),
        ("open whatsapp", "", ""),
    ],
)
def test_parse_whatsapp_command(planner, command, target, text):
    got_target, got_text = planner._parse_whatsapp_command(command)
    assert got_target == target
    assert got_text == text


def test_message_text_is_not_swallowed_into_the_contact(planner):
    """'message bhumi hi' once captured 'bhumi hi' as the whole contact name."""
    target, text = planner._parse_whatsapp_command("open whatsapp and message bhumi hi")
    assert target == "bhumi"
    assert text == "hi"


# ── Number resolution ────────────────────────────────────────────────────────
def test_direct_number_needs_no_lookup(planner):
    assert planner._resolve_phone_number("+919876543210")["phone"] == "919876543210"


def test_unknown_name_reports_how_to_fix_it(planner):
    res = planner._resolve_phone_number("nobody_known_xyz")
    assert res["phone"] is None
    assert "remember" in res["message"].lower()


def test_remembered_number_is_found(planner, monkeypatch):
    """
    Stubs recall rather than calling `remember`: memories.db is the user's real
    assistant memory, and a test suite should not leave fake contacts in it.
    """
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda query, limit=5: {
            "matches": [{"key": "testcontact's number", "value": "+919812345678"}]
        },
    )
    resolved = planner._resolve_phone_number("testcontact")
    assert resolved["phone"] == "919812345678"
    assert "remembered" in resolved["source"]


# ── The Tier-1 / Tier-2 split ────────────────────────────────────────────────
def test_prepare_is_tier1_and_sends_nothing(planner, stub_whatsapp):
    res = _exec(planner.process_command("message +919876543210 saying hello"))
    assert res.get("success") is True
    assert stub_whatsapp["opened"] == [("919876543210", "hello")]
    assert stub_whatsapp["sent"] == [], "preparing must not send"
    assert res.get("awaiting_tier2_approval") is not True


def test_send_is_gated_and_sends_nothing_until_approved(planner, stub_whatsapp):
    res = _exec(planner.process_command("send whatsapp to +919876543210 saying hello"))
    assert res.get("awaiting_tier2_approval") is True
    assert res.get("risk_tier") == 2
    assert stub_whatsapp["sent"] == [], "nothing may be sent before approval"


def test_send_runs_only_after_explicit_yes(planner, stub_whatsapp):
    planner.process_command("send whatsapp to +919876543210 saying hello")
    res = _exec(planner.process_command("yes"))
    assert res.get("approved_by_user") is True
    assert stub_whatsapp["sent"] == [("919876543210", "hello")]


def test_send_cancelled_sends_nothing(planner, stub_whatsapp):
    planner.process_command("send whatsapp to +919876543210 saying hello")
    res = _exec(planner.process_command("no"))
    assert res.get("cancelled") is True
    assert stub_whatsapp["sent"] == []


def test_unknown_number_never_reaches_the_gate(planner, stub_whatsapp):
    res = _exec(planner.process_command("send whatsapp to nobody_known_xyz saying hi"))
    assert res.get("awaiting_tier2_approval") is not True
    assert stub_whatsapp["sent"] == []


# ── Honesty of the reported outcome ──────────────────────────────────────────
def test_send_whatsapp_is_registered_as_tier2():
    assert "send_whatsapp" in TIER_2_ACTIONS
    assert "send_whatsapp" in TIER_2_IMPLEMENTED
    assert classify_action_risk("send_whatsapp")[0] == 2


def test_auto_send_never_claims_confirmed_delivery(planner, stub_whatsapp):
    """
    Nothing here can read WhatsApp back, so the result reports that Enter was
    pressed — never that the message was delivered.
    """
    planner.process_command("send whatsapp to +919876543210 saying hello")
    res = _exec(planner.process_command("yes"))
    assert res.get("delivery_confirmed") is False


def test_auto_send_without_pyautogui_fails_honestly(monkeypatch):
    """With the optional dependency absent, say so rather than pretending."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pyautogui":
            raise ImportError("No module named 'pyautogui'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    res = CommunicationAgent().send_whatsapp_now("+919876543210", "hi")
    assert res["success"] is False
    assert res["error"] == "PYAUTOGUI_MISSING"
    assert "pyautogui" in res["message"]
