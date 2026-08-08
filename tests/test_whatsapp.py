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


@pytest.mark.parametrize(
    "prose",
    [
        "+919876543210 saying hello there",
        "call me at +919876543210 tomorrow",
        "order 12345678 shipped",
        "user said message +919876543210 saying hi",
    ],
)
def test_normalise_phone_rejects_prose_containing_a_number(prose):
    """
    The number-from-prose bug. normalise_phone used to strip every non-digit and
    treat the residue as a phone number, so a stored sentence became a valid
    recipient — that is how a chat was once opened with a number the user never
    typed.
    """
    assert CommunicationAgent.normalise_phone(prose) is None


# ── Default country code ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9876543210", "919876543210"),      # bare national mobile
        ("98765 43210", "919876543210"),     # spaced
        ("09876543210", "919876543210"),     # trunk prefix
        ("919876543210", "919876543210"),    # already carries the code
        ("+ 919 876 543 210", "919876543210"),  # space after the +
    ],
)
def test_missing_country_code_defaults_to_91(raw, expected):
    assert CommunicationAgent.normalise_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "79828 0245",       # 9 digits — opened a chat with "+798280245"
        "+ 9199 662 4322",  # 11 digits, cannot be a real +91 number
        "12345",
        "987654321",        # 9 digits
        "98765432101",      # 11 digits, no trunk zero
    ],
)
def test_malformed_numbers_are_rejected_not_guessed(raw):
    assert CommunicationAgent.normalise_phone(raw) is None


def test_other_country_codes_still_work():
    assert CommunicationAgent.normalise_phone("+1 555 123 4567") == "15551234567"


def test_extract_phone_is_the_deliberate_prose_search():
    assert CommunicationAgent.extract_phone("her number is +91 98765 43210") == "919876543210"
    # Requires an explicit '+', so IDs and order numbers are not recipients.
    assert CommunicationAgent.extract_phone("order 12345678 shipped") is None


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


# ── The wrong-recipient bug ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "command,target,text",
    [
        ('open whatsapp and send message "Hello" to +917988280245', "+917988280245", "Hello"),
        ('send message "Hi there" to bhumi', "bhumi", "Hi there"),
        ('whatsapp "Good morning" to +917988280245', "+917988280245", "Good morning"),
    ],
)
def test_trailing_recipient_is_read_correctly(planner, command, target, text):
    """
    English puts the recipient last as often as first. Reading only the leading
    form made the literal word "message" the recipient, and the real number was
    left inside the message body.
    """
    got_target, got_text = planner._parse_whatsapp_command(command)
    assert got_target == target
    assert got_text == text


@pytest.mark.parametrize("filler", ["message", "msg", "send", "whatsapp", "text", "to"])
def test_filler_words_are_never_treated_as_a_recipient(planner, filler):
    assert planner._clean_wa_target(filler) == ""
    assert planner._resolve_phone_number(filler)["phone"] is None


def test_conversation_transcripts_cannot_supply_a_recipient(planner, monkeypatch):
    """
    recall() is a TF-IDF similarity search and returns loosely related rows,
    including saved conversation turns. Lifting a number out of one is exactly
    how a message was addressed to a stranger.
    """
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda q, limit=8: {"matches": [
            {"key": "turn_20260808_001132", "value": "user said message +919876543210 saying hi"},
            {"key": "my favourite editor", "value": "VSCode, call +919876543210 for support"},
        ]},
    )
    assert planner._resolve_phone_number("bhumi")["phone"] is None


def test_only_contact_shaped_memories_resolve(planner, monkeypatch):
    """The key must name the person AND read like a contact record."""
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda q, limit=8: {"matches": [
            # Mentions bhumi, but is not a contact record.
            {"key": "bhumi's favourite food", "value": "pasta, table +919876543210"},
        ]},
    )
    assert planner._resolve_phone_number("bhumi")["phone"] is None


def test_end_to_end_uses_the_number_the_user_typed(planner, stub_whatsapp):
    """The reported bug, end to end: the gate must quote the typed number."""
    res = _exec(planner.process_command(
        'open whatsapp and send message "Hello" to +917988280245'
    ))
    assert res.get("target") == "+917988280245"
    assert '"Hello"' in res["message"]
    assert stub_whatsapp["sent"] == []

    _exec(planner.process_command("yes"))
    assert stub_whatsapp["sent"] == [("917988280245", "Hello")]


# ── Teaching a number ────────────────────────────────────────────────────────
@pytest.fixture
def no_memory_writes(planner, monkeypatch):
    """
    Capture saved contacts instead of writing them. memories.db is the user's
    real assistant memory; a suite must not leave relatives in it.
    """
    saved = {}
    monkeypatch.setattr(
        planner.memory_agent, "remember",
        lambda key, value, topic="general": saved.update({key: value}) or {"success": True},
    )
    monkeypatch.setattr(
        planner.memory_agent, "recall",
        lambda query, limit=8: {"matches": [
            {"key": k, "value": v} for k, v in saved.items()
            if query.strip().lower() in k.lower()
        ]},
    )
    return saved


@pytest.mark.parametrize(
    "command,key,value",
    [
        ("papa number is +919996624322", "papa's number", "+919996624322"),
        ("mummy's number is 9876543210", "mummy's number", "+919876543210"),
        ("remember bhaiya number is 09812345678", "bhaiya's number", "+919812345678"),
        ("save didi contact number 9812345678", "didi's number", "+919812345678"),
    ],
)
def test_natural_phrasings_save_a_contact_number(planner, no_memory_writes, command, key, value):
    """
    Every one of these previously fell through to chitchat and was answered with
    a greeting, so a number could only be taught via one exact phrasing.
    """
    res = _exec(planner.process_command(command))
    assert res.get("success") is True
    assert no_memory_writes.get(key) == value


def test_number_with_no_owner_asks_whose_it_is(planner, no_memory_writes):
    """'the number is +91…' must not be filed under "the's number"."""
    res = _exec(planner.process_command("the number is +919996624322"))
    assert res.get("success") is False
    assert res.get("error") == "NO_CONTACT_NAME"
    # Conversation turns are stored via the same remember() call, so assert on
    # contact records specifically rather than on the store being untouched.
    contacts = {k: v for k, v in no_memory_writes.items() if k.endswith("'s number")}
    assert contacts == {}


# ── The follow-up flow ───────────────────────────────────────────────────────
def test_unknown_contact_asks_then_saves_then_resumes(planner, stub_whatsapp, no_memory_writes):
    """The screenshot flow: ask for the number, then carry on with the message."""
    first = _exec(planner.process_command("papa on WhatsApp hello"))
    assert first.get("awaiting_contact_number") is True
    assert stub_whatsapp["opened"] == []

    second = _exec(planner.process_command("9996624322"))
    assert no_memory_writes.get("papa's number") == "+919996624322"
    # The original message is carried through to the send prompt, not discarded.
    assert second.get("awaiting_tier2_approval") is True
    assert '"hello"' in second["message"]
    assert stub_whatsapp["sent"] == []

    _exec(planner.process_command("yes"))
    assert stub_whatsapp["sent"] == [("919996624322", "hello")]


def test_mid_sentence_on_whatsapp_is_not_message_text(planner):
    """'papa on WhatsApp hello' put "on WhatsApp hello" in the body."""
    target, text = planner._parse_whatsapp_command("papa on WhatsApp hello")
    assert target == "papa"
    assert text == "hello"


def test_known_contact_routes_bare_message_to_whatsapp(planner, stub_whatsapp, no_memory_writes):
    """'message papa saying hi' fell through to chitchat once papa was known."""
    planner.process_command("papa number is 9996624322")
    planner.pending_clarification = None
    res = _exec(planner.process_command("message papa saying good morning"))
    assert res.get("awaiting_tier2_approval") is True
    assert res.get("target") == "+919996624322"


def test_unknown_bare_name_does_not_become_a_whatsapp_message(planner, stub_whatsapp, no_memory_writes):
    """Without a saved number the command must not be hijacked from email."""
    _exec(planner.process_command("message someone_unknown_xyz saying hi"))
    assert stub_whatsapp["opened"] == []


def test_malformed_number_target_says_so(planner, stub_whatsapp):
    """'WhatsApp 79828 0245 hello' opened a chat with +798280245."""
    res = _exec(planner.process_command("WhatsApp 79828 0245 hello"))
    assert res.get("error") == "BAD_PHONE"
    assert "9 digits" in res["message"]
    assert stub_whatsapp["opened"] == []


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
def test_any_message_asks_before_sending(planner, stub_whatsapp):
    """
    Every message with text is gated and then sent for real. Leaving the user to
    press Enter themselves was needless — they had already said what to send and
    to whom, so the only thing worth asking is whether to go ahead.
    """
    res = _exec(planner.process_command("message +919876543210 saying hello"))
    assert res.get("awaiting_tier2_approval") is True
    assert "send it?" in res["message"].lower()
    assert stub_whatsapp["sent"] == [], "nothing may be sent before approval"
    assert stub_whatsapp["opened"] == []


def test_opening_with_no_message_is_tier1(planner, stub_whatsapp):
    """No text means nothing to send, so it just opens the chat."""
    res = _exec(planner.process_command("whatsapp +919876543210"))
    assert res.get("success") is True
    assert res.get("awaiting_tier2_approval") is not True
    assert stub_whatsapp["opened"] == [("919876543210", "")]
    assert stub_whatsapp["sent"] == []


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


def test_auto_send_without_pyautogui_degrades_honestly(monkeypatch):
    """
    Approval has already been given at this point, so do as much as is possible —
    open the chat with the message typed — and say exactly which part could not
    be done, rather than dead-ending or claiming it was sent.
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pyautogui":
            raise ImportError("No module named 'pyautogui'")
        return real_import(name, *args, **kwargs)

    agent = CommunicationAgent()
    opened = []
    monkeypatch.setattr(
        agent, "open_whatsapp_chat",
        lambda phone, text="": opened.append((phone, text)) or {
            "success": True, "phone": phone, "message": "opened",
        },
    )
    monkeypatch.setattr(builtins, "__import__", fake_import)

    res = agent.send_whatsapp_now("+919876543210", "hi")
    assert res["error"] == "PYAUTOGUI_MISSING"
    assert res["message_sent"] is False
    assert opened == [("919876543210", "hi")], "should still prepare the message"
    assert "pyautogui" in res["message"]
