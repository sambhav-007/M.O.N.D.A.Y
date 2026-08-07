"""
Conversation-flow regressions found by driving the running app.

All three came from one screenshot of a real session:

  > send mail to sambhav.sehgal.007@gmail.com
    Draft ready. Subject: (no subject)  Body:        <- offered to send an empty email
  > subject : hello body: hii
    I didn't catch that. Reply 'send' or 'cancel'.   <- no way to supply the missing parts
  > open whatsapp and message bhumi hi
    ✓ Opened WhatsApp for contact 'bhumi hi'.        <- never messaged anyone; mis-parsed too
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner


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


def _exec(res):
    return res["execution_result"]


# ── A bare recipient must not produce a sendable empty email ─────────────────
def test_bare_recipient_asks_for_subject_not_send_confirmation(planner):
    res = _exec(planner.process_command("send mail to a@b.com"))
    assert res.get("awaiting_subject") is True
    # Crucially NOT offering to send an empty message.
    assert res.get("awaiting_send_confirmation") is not True
    assert "(no subject)" not in res["message"]


def test_wizard_collects_subject_then_body_then_confirms(planner):
    planner.process_command("send mail to a@b.com")
    subj = _exec(planner.process_command("Quarterly update"))
    assert "body" in subj["message"].lower()

    body = _exec(planner.process_command("Numbers attached."))
    assert body.get("awaiting_send_confirmation") is True
    assert "Quarterly update" in body["message"]
    assert "Numbers attached." in body["message"]
    assert body.get("delivered") is not True


def test_fully_specified_command_still_goes_straight_to_confirmation(planner):
    """The one-liner path must not be made slower by the wizard."""
    res = _exec(
        planner.process_command('send mail to a@b.com subject "Hi" body "Hello"')
    )
    assert res.get("awaiting_send_confirmation") is True
    assert res.get("awaiting_subject") is not True


# ── The draft must be correctable at the confirmation prompt ────────────────
def test_subject_and_body_at_confirm_prompt_update_the_draft(planner):
    planner.process_command('send mail to a@b.com subject "old" body "old body"')
    res = _exec(planner.process_command("subject : hello body: hii"))

    assert res.get("updated") is True
    assert res["subject"] == "hello"
    assert res["body"] == "hii"
    # Still gated — an edit is not an approval.
    assert res.get("awaiting_send_confirmation") is True
    assert res.get("delivered") is not True


def test_edit_then_cancel_still_works(planner):
    planner.process_command('send mail to a@b.com subject "old" body "old body"')
    planner.process_command("subject: new body: text")
    res = _exec(planner.process_command("cancel"))
    assert res.get("cancelled") is True
    assert planner.pending_clarification is None


def test_genuinely_unclear_reply_still_reasks(planner):
    planner.process_command('send mail to a@b.com subject "s" body "b"')
    res = _exec(planner.process_command("purple monkey dishwasher"))
    assert res.get("awaiting_send_confirmation") is True
    assert res.get("updated") is not True
    assert planner.pending_clarification is not None


# ── WhatsApp ────────────────────────────────────────────────────────────────
# The third screenshot bug was fixed twice over: first by making the handler
# report honestly, then by actually implementing messaging. Its coverage now
# lives in tests/test_whatsapp.py, which tests parsing, number resolution and
# the Tier-1 (prepare) / Tier-2 (send) split against stubbed agent calls.
#
# The one assertion kept here is the original regression, because it is the bug
# the screenshot showed: the message text must not be swallowed into the contact
# name. "message bhumi hi" once produced contact "bhumi hi".


def test_message_text_is_not_swallowed_into_contact_name(planner):
    target, text = planner._parse_whatsapp_command("open whatsapp and message bhumi hi")
    assert target == "bhumi"
    assert text == "hi"
