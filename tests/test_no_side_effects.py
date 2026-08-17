"""
The suite must not do things to the machine that runs it.

**Reported by the user, 2026-08-17: "when you test, I could only see mail tabs
opening."** They were right. `CommunicationAgent.draft_email` calls
`webbrowser.open(gmail_url)` for every draft — "also launch browser tab for
visual inspection" — and a dozen tests compose email, so every full run opened a
stack of Gmail compose tabs on their desktop. It had been happening for as long
as those tests existed.

This is the third time this class of bug has been found here, which is why it
now has its own file:

1. The volume tests drove the real speakers and left the machine muted, until
   `fake_powershell` intercepted the PowerShell calls.
2. The suite wrote 2,196 rows into the user's real assistant memory, until
   `_isolate_memory_db` redirected it — and it got slower every run as a result.
3. This: browser tabs, one per draft.

The pattern is always the same. A handler reaches outside the process, a test
exercises the handler, and nobody notices because the side effect lands
somewhere no assertion looks. The general defence is a fixture that intercepts
the reach; this file is the assertion that the defence is in place.
"""

from __future__ import annotations

import webbrowser

import pytest

from core.planner import MasterPlanner


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clean(planner):
    planner.pending_clarification = None
    yield
    planner.pending_clarification = None


def test_the_browser_is_intercepted_for_every_test(no_browser_tabs):
    """The fixture is autouse, so this holds without asking for it.

    Asserted against the module attribute rather than by opening something,
    because a test that opens a real tab to prove tabs are blocked has already
    failed.
    """
    assert webbrowser.open.__name__ == "_record", (
        "webbrowser.open is not intercepted — a test that drafts an email will "
        "open a Gmail tab on the machine running the suite"
    )


def test_drafting_an_email_opens_no_tab(planner, no_browser_tabs):
    """The exact path the user saw.

    `send mail to …` writes a draft, and `draft_email` opens a Gmail compose
    URL. The draft still has to be written — the assertion is that the tab is
    recorded rather than opened.
    """
    planner.process_command('send mail to a@b.com subject "Demo" body "Hello"')
    planner.pending_clarification = None

    assert no_browser_tabs, "draft_email no longer opens a URL — has the behaviour changed?"
    assert any("mail.google.com" in url for url in no_browser_tabs)
    # Recorded, not launched: nothing reached a real browser.
    assert webbrowser.open.__name__ == "_record"


def test_the_whole_demo_script_opens_no_tabs(planner, no_browser_tabs, fake_powershell):
    """`DEMO.md` Act 5 drafts an email; Act 1–4 must not open anything at all."""
    for command in ["what time is it", "health", "battery", "my ip",
                    "kill notepad", "no"]:
        planner.process_command(command)
    planner.pending_clarification = None
    assert no_browser_tabs == [], f"the offline demo commands opened: {no_browser_tabs}"


def test_opening_an_app_is_recorded_not_performed(planner, no_browser_tabs):
    """`open_app_or_website` falls back to `webbrowser.open` for anything that
    is not an installed program, which in a test means a real tab."""
    planner.browser_agent.open_app_or_website("example.com")
    assert any("example.com" in url for url in no_browser_tabs)


def test_preparing_a_whatsapp_message_opens_no_tab(planner, no_browser_tabs):
    """The deep link is a URL too. Preparing a message is the feature, but a
    test asserting the URL was built should not launch WhatsApp to find out."""
    planner.comms_agent.open_whatsapp_chat("919876543210", "hello")
    assert any("whatsapp" in url.lower() or "wa.me" in url.lower()
               for url in no_browser_tabs)
