"""
M.O.N.D.A.Y. — tranche 6: email and WhatsApp.

Migrated last, deliberately. These are the only outward-facing paths in the
system — one of them is Tier 2 and irreversible — and they carry ~74 of the
suite's tests. UPGRADE_PLAN §4 puts them at the end of the migration order for
exactly that reason: they are the ones you least want to disturb early.

**What moves and what does not.** Routing moves. Parsing does not.
`_parse_email_command`, `_parse_whatsapp_command`, `_resolve_phone_number` and
the four contact-validation guards stay in `core/planner.py` and are called
unchanged. Those guards exist because `normalise_phone` once stripped digits out
of arbitrary text while `recall` returned loosely-similar rows, and between them
a WhatsApp message was addressed to a number lifted from an unrelated saved
transcript (handoff.md §9.2). Re-expressing that as patterns would be rewriting
the most safety-critical parsing in the repo in the same change that reroutes
it. The patterns here decide *which* handler runs; the handler decides what the
command means.

What the substring chain got wrong here, and what patterns fix:

* `"gmail" in cmd_lower` fired ~70 lines above the app launcher, so **`open
  gmail` answered "✓ Recipient set to 'recipient@example.com'! What is the
  subject of the email?"** — a request to open a website became a half-built
  message to a placeholder address.
* The email wizard block was written **twice**, ~130 lines apart, with slightly
  different behaviour in each copy. Whichever ran depended on which keyword
  matched first. Both are now one function.
* `"message" in cmd_lower` was in the *email* branch's keyword list, which is
  why "message papa saying hi" — with papa's number saved — had to be rescued
  by a special case wedged in above it.
"""

from __future__ import annotations

from typing import Any, Dict

from core.skills import Skill, SkillRegistry


def register_comms_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers the email and WhatsApp skills."""

    # ── Email: the one-liner path ────────────────────────────────────────────
    # Sending is Tier 2, but the *skill* is Tier 1: this handler drafts and then
    # asks. Nothing leaves the machine until a separate confirming turn says so
    # — `_handle_send_email` ignores `user_approved` on purpose, because
    # `ui/index.html` used to post it as `true` on every command, and honouring
    # it fired a real email off the first message.
    def send_email(_command: str = "", **_: Any) -> Dict[str, Any]:
        return planner._handle_send_email(_command, user_approved=False)

    registry.register(Skill(
        name="send_email",
        description="Compose an email and ask before sending it",
        patterns=[
            # "gmail" is in the alternation and bare `gmail` is not a pattern of
            # its own — that distinction is the whole tranche-3 defect. The old
            # branch tested `"gmail" in cmd_lower`, so "open gmail" started an
            # email; here the word only means email when a mail verb is in front
            # of it, and `open gmail` belongs to the launcher.
            "send [(a|an)] (mail|email|e-mail|gmail) to {rest}",
            "send [(a|an)] (mail|email|e-mail|gmail) {rest}",
            "(mail|email|e-mail) to {rest}",
            "send {rest} (a|an) (mail|email|e-mail|gmail)",
        ],
        handler=send_email,
        tier=1,
        # Offline, and the distinction is exact: this skill *drafts* and asks.
        # The draft is written to `data/staging/` and the confirmation is a
        # local prompt — no socket is opened. The SMTP connection happens in
        # `_send_confirmed_email`, on the following turn, only after an explicit
        # yes. So composing an email is demonstrable with the Wi-Fi off, and
        # `tests/test_demo_script.py` proves it every run rather than taking the
        # flag's word for it. (It was `False`, and that test is what caught it.)
        offline=True,
    ))

    # ── Email: the wizard path ───────────────────────────────────────────────
    def compose_email(_command: str = "", **_: Any) -> Dict[str, Any]:
        return planner._start_email_wizard(_command)

    registry.register(Skill(
        name="compose_email",
        description="Start an email step by step",
        patterns=[
            "(draft|write|compose|create|start) [(a|an)] (mail|email|e-mail|gmail) to {rest}",
            "(draft|write|compose|create|start) [(a|an)] (mail|email|e-mail|gmail)",
            # No bare `draft {rest}` / `write {rest}`. The legacy branch fired on
            # `"draft" in cmd_lower`, so "draft a report on Q3" was answered
            # "🔒 Contact Unresolved: no email address found for 'a report'".
            # Without the word "email" in it, a draft is not an email.
        ],
        handler=compose_email,
        tier=1,
        # Same reasoning: the wizard collects a recipient, a subject and a body,
        # all locally, and ends at the same confirmation.
        offline=True,
    ))

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    # Every message is *prepared*, never sent. The deep link
    # (`whatsapp://send?phone=…&text=…`) opens the chat with the text typed in
    # the box and deliberately declines to send it — anti-spam design, not an
    # obstacle to route around. The previous version simulated an Enter keypress
    # after a fixed 8-second sleep; reported from live use on 2026-08-13, the
    # gate was approved, the reply read "Opened the chat … and pressed Enter",
    # and no message was sent. `pyautogui.press("enter")` goes to whatever
    # window has focus, and nothing here can read WhatsApp back to notice.
    #
    # A gate in front of an action that does not happen is worse than no gate,
    # so both went. This handler reports that the message was *typed*.
    def whatsapp(_command: str = "", **_: Any) -> Dict[str, Any]:
        return planner._handle_whatsapp(_command, _command.lower())

    registry.register(Skill(
        name="whatsapp_message",
        description="Open a WhatsApp chat with a message typed in",
        patterns=[
            # Explicitly named. `{rest}` carries the whole remainder to
            # `_parse_whatsapp_command`, which handles both word orders.
            "whatsapp {rest}",
            "whats app {rest}",
            "open whatsapp",
            "open whats app",
            "(open|launch) whatsapp and {rest}",
            "send [(a|an)] whatsapp [message] to {rest}",
            "send [(a|an)] whatsapp [message] {rest}",
            "(message|msg|text) {rest} on whatsapp",
            # "papa on WhatsApp hello" — the app named in the middle, which is
            # how people actually say it. `_parse_whatsapp_command` strips the
            # mid-sentence "on WhatsApp" so it cannot end up inside the message
            # body, where it once produced the text "on WhatsApp hello".
            "{who} on whatsapp {text}",
            "{who} on whats app {text}",
            # A literal phone number after a messaging verb has no other
            # sensible destination, and it is what `/help` tells the user to
            # type. The `:phone` type is what keeps this from swallowing
            # "message the team about friday".
            "(message|msg|text) {phone:phone} {rest}",
            "(message|msg|text) {phone:phone}",
            "send [a] (message|msg|text) to {phone:phone} {rest}",
        ],
        handler=whatsapp,
        tier=1,
        offline=True,
    ))

    # ── The genuinely ambiguous one ──────────────────────────────────────────
    # "message papa saying good morning" names no app and carries no number.
    # It is a WhatsApp message if we know papa's number and an email if we know
    # papa's address, and there is no way to tell from the words alone.
    #
    # The chain expressed this by trying WhatsApp in one branch and then, ~15
    # lines further down, letting `"message" in cmd_lower` fall into the email
    # branch. That worked, but the decision was spread across two places and
    # readable in neither. It is one function here, and it resolves the same
    # way: a saved number wins, because "message X saying Y" with a number on
    # file is not ambiguous in practice.
    def message_contact(_command: str = "", **_: Any) -> Dict[str, Any]:
        target, _text = planner._parse_whatsapp_command(_command)
        if target and "@" not in _command:
            if planner._resolve_phone_number(target).get("phone"):
                return planner._handle_whatsapp(_command, _command.lower())
        return planner._start_email_wizard(_command)

    registry.register(Skill(
        name="message_contact",
        description="Message someone — WhatsApp if their number is saved, else email",
        patterns=[
            "(message|msg|text) {rest}",
            "send [(a|an)] (message|msg|text) to {rest}",
            "send {rest} a (message|msg|text)",
        ],
        handler=message_contact,
        tier=1,
        offline=True,
    ))
