"""
M.O.N.D.A.Y. — contacts, phone numbers, and WhatsApp.

The most safety-critical parsing in the repo, and the reason is one bug:
`normalise_phone` once stripped every non-digit from arbitrary text, and
`memory_agent.recall` is a TF-IDF *similarity* search. Between them, a
WhatsApp message was addressed to a phone number lifted from an unrelated
saved conversation transcript. The four guards in `_resolve_phone_number`
are what stop that, and none of them may be loosened.

Moved out of `core/planner.py` unchanged when the substring chain was
removed — as a mixin, so every call site and every one of the ~74 tests
covering it keeps working against `MasterPlanner` exactly as before.
Routing now happens in `core/skills_comms.py`; what lives here is the
parsing that decides what a command *means* once it has been routed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from agents.memory_agent import is_machine_written
from core.tier2 import parse_confirmation


class ContactMixin:
    """Contact-number storage, lookup, and the WhatsApp handler."""

    def _resolve_contact_number(
        self, clarification: Dict[str, Any], reply: str
    ) -> Dict[str, Any]:
        """
        Takes the number the user just supplied, saves it, and resumes the
        message they originally asked for.
        """
        name = clarification.get("name", "that contact")
        pending_text = clarification.get("pending_text", "")

        # Accept a bare number, or a full "papa's number is +91..." restatement.
        phone = self.comms_agent.normalise_phone(reply)
        if not phone:
            restated = self._SAVE_NUMBER_RE.match(reply or "")
            if restated:
                phone = self.comms_agent.normalise_phone(restated.group("phone"))
                # Only let a restatement rename the contact if it names a real
                # person. "the number is +91..." must stay attached to whoever we
                # were already asking about, not be saved as "the's number".
                restated_name = self._clean_contact_name(restated.group("name"))
                if restated_name:
                    name = restated_name
        if not phone:
            phone = self.comms_agent.extract_phone(reply)

        if not phone:
            if parse_confirmation(reply) == "no":
                return self._wrap_contact_result(reply, {
                    "success": True, "cancelled": True,
                    "message": f"Alright — nothing sent, and I haven't saved a number for {name}.",
                })
            self.pending_clarification = clarification  # re-arm, don't guess
            return self._wrap_contact_result(reply, {
                "success": False,
                "pending_clarification": True,
                "awaiting_contact_number": True,
                "message": (
                    f"That didn't look like a phone number. What's {name}'s number? "
                    f"(10 digits is fine — I'll assume +91, or say 'cancel')"
                ),
            })

        # Same pair as `_handle_save_contact_number`: the typed table is the
        # store of record, the memory row is compatibility.
        self.memory_agent.save_contact(name, phone=f"+{phone}", source="user")
        self.memory_agent.remember(f"{name}'s number", f"+{phone}", topic="contacts")

        if not pending_text:
            return self._wrap_contact_result(reply, {
                "success": True,
                "contact": name,
                "phone": phone,
                "message": f"✓ Saved {name}'s number as +{phone}.",
            })

        # Resume the message the user originally asked for, now that the number
        # is known. It is prepared, not sent — see `_handle_whatsapp`.
        result = self.comms_agent.open_whatsapp_chat(phone, pending_text)
        result["message"] = f"✓ Saved {name}'s number as +{phone}. " + result["message"]
        result["speech"] = f"Saved {name}'s number. It's typed in the chat — press Enter to send."
        return self._wrap_contact_result(reply, result)

    def _wrap_contact_result(self, reply: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "user_command": reply,
            "clarification_resumed": True,
            "intent_classification": {
                "predicted_intent": "communication", "confidence": 1.0,
                "llm_fallback": False, "clo": "CLO04",
            },
            "rl_routing": {"strategy": "contact_number_prompt", "clo": "CLO05"},
            "execution_result": result,
        }

    # ── Saving a contact's phone number ──────────────────────────────────────
    # "papa number is +919996624322", "remember bhumi's number is 9876543210",
    # "save papa 9876543210". Without this, every one of those fell through to
    # chitchat and answered with a greeting, so a number could only ever be
    # taught by hitting the exact `remember X's number is Y` phrasing.
    _SAVE_NUMBER_RE = re.compile(
        r'^\s*(?:remember|save|store|set|add)?\s*'
        r'(?P<name>[A-Za-z][\w .\-]{0,40}?)'
        r"(?:'s|s')?\s+"
        r'(?:phone\s+|mobile\s+|cell\s+|whats\s?app\s+|contact\s+)?'
        r'(?:number|num|no\.?)\s*'
        r'(?:is|=|:|-)?\s*'
        r'(?P<phone>\+?\s*[\d][\d\s\-().]{5,24})\s*$',
        re.IGNORECASE,
    )

    # Words that are never a person. "the number is +91…" must not be filed
    # under "the's number".
    _NON_NAMES = {
        "the", "my", "a", "an", "this", "that", "his", "her", "their", "its",
        "your", "our", "there", "here", "it", "whatsapp", "phone", "mobile",
        "contact", "number",
    }

    def _clean_contact_name(self, raw: str) -> str:
        """Returns a usable contact name, or '' if it is filler."""
        name = (raw or "").strip().strip(",:;\"'")
        name = re.sub(
            r'^(?:remember|save|store|set|add|the|my|his|her|their)\s+',
            "", name, flags=re.IGNORECASE,
        ).strip()
        return "" if not name or name.lower() in self._NON_NAMES else name

    def _handle_save_contact_number(self, command: str) -> Optional[Dict[str, Any]]:
        """Stores '<name>'s number' when the command reads like one. Else None."""
        match = self._SAVE_NUMBER_RE.match(command or "")
        if not match:
            return None

        name = self._clean_contact_name(match.group("name"))
        phone = self.comms_agent.normalise_phone(match.group("phone"))

        if not phone:
            return {
                "success": False,
                "error": "BAD_PHONE",
                "message": (
                    f"'{match.group('phone').strip()}' doesn't look like a valid "
                    f"number. Indian mobiles are 10 digits (9876543210); for other "
                    f"countries include the code (+1 555 123 4567)."
                ),
            }
        if not name:
            # "the number is ..." — a number with nobody to attach it to.
            return {
                "success": False,
                "error": "NO_CONTACT_NAME",
                "phone": phone,
                "message": (
                    f"Whose number is +{phone}? Try: papa's number is +{phone}"
                ),
            }

        # The typed table is the store of record. The `memories` row is written
        # too, and only for backwards compatibility: a user's existing contacts
        # live there, `search_local_contacts` still reads it, and dropping it
        # would lose numbers taught before this table existed.
        self.memory_agent.save_contact(name, phone=f"+{phone}", source="user")
        self.memory_agent.remember(f"{name}'s number", f"+{phone}", topic="contacts")
        return {
            "success": True,
            "intent": "save_contact_number",
            "contact": name,
            "phone": phone,
            "message": (
                f"✓ Saved {name}'s number as +{phone}.\n"
                f"  You can now say: message {name} saying hello"
            ),
        }

    # ── WhatsApp helpers ─────────────────────────────────────────────────────
    def _resolve_phone_number(self, target: str) -> Dict[str, Any]:
        """
        Turns "+919876543210" or a saved name into a WhatsApp number.

        Three sources, in descending order of trust:

        1. **The number itself**, if the user typed one.
        2. **The `contacts` table** — an exact, case-insensitive lookup of a
           typed record. This cannot return a conversation transcript, because
           transcripts are not in that table.
        3. **The legacy `memories` search**, behind four guards, for numbers
           taught before the table existed. It is a TF-IDF *similarity* search,
           which is precisely why it needs the guards and why it is last.

        Source 3 is what once addressed a message to a number lifted from an
        unrelated saved turn. It is kept because deleting it would lose a user's
        existing contacts, not because it is a good way to find a phone number.
        """
        direct = self.comms_agent.normalise_phone(target)
        if direct:
            return {"phone": direct, "source": "given directly"}

        name = (target or "").strip().lower()
        if not name:
            return {"phone": None, "error": "NO_TARGET", "message": "Who should I message?"}

        # ── 2. The typed table ───────────────────────────────────────────────
        try:
            contact = self.memory_agent.get_contact(target)
        except Exception:
            contact = None
        if contact and contact.get("phone"):
            typed = self.comms_agent.normalise_phone(str(contact["phone"]))
            if typed:
                return {"phone": typed, "source": "saved contact"}

        # ── 3. The legacy similarity search, behind its guards ───────────────
        try:
            recalled = self.memory_agent.recall(target, limit=8)
        except Exception:
            recalled = {"matches": []}

        # `recall` is a TF-IDF similarity search, so it happily returns loosely
        # related rows — including stored conversation transcripts. Picking a
        # recipient out of those is how "send message to +917988280245" once
        # opened a chat with a number lifted from an unrelated saved turn. A row
        # is only accepted as a contact record when ALL of the following hold.
        for match in recalled.get("matches", []):
            key = str(match.get("key", ""))
            key_l = key.lower()
            value = str(match.get("value", ""))

            # 1. Not a conversation transcript or other machine-written record.
            if is_machine_written(key):
                continue
            # 2. The key must actually name the person asked for.
            if name not in key_l:
                continue
            # 3. The key must read like a contact record, not an arbitrary fact
            #    that happens to mention them.
            if not any(w in key_l for w in ("number", "phone", "mobile", "cell", "whatsapp", "contact")):
                continue
            # 4. The value must be a phone number, or contain an explicit +… one.
            phone = self.comms_agent.normalise_phone(value) or self.comms_agent.extract_phone(value)
            if phone:
                return {"phone": phone, "source": f"remembered as '{key}'"}

        return {
            "phone": None,
            "error": "NO_NUMBER",
            "message": (
                f"I don't have a phone number for '{target}'. Either give it "
                f"directly (message +919876543210 saying hi) or teach me first: "
                f"remember {target}'s number is +919876543210"
            ),
        }

    # "message/text +91… " — a literal phone number after a messaging verb.
    _WHATSAPP_PHONE_RE = re.compile(
        r'\b(?:message|msg|text|send to)\s+\+?\d[\d\s\-()]{7,}', re.IGNORECASE
    )
    # A messaging verb followed by a bare name — only routed to WhatsApp when
    # that name turns out to have a saved number. See the guard at the call site.
    _WA_NAME_VERB_RE = re.compile(
        r'^\s*(?:message|msg|text)\s+[A-Za-z]', re.IGNORECASE
    )

    # Leading verbs and filler stripped before the target is read. Done stepwise
    # rather than as one regex: "send whatsapp to bhumi saying hi", "open whatsapp
    # and message bhumi hi" and "message +91… saying hi" are all natural phrasings,
    # and a single pattern that covers them is unreadable and fragile.
    _WA_PREFIX_RE = re.compile(
        r'^\s*(?:please\s+)?(?:open|send|shoot|fire|write|start)?\s*'
        r'(?:a\s+)?(?:whats\s?app|whatsapp)?\s*(?:and\s+)?'
        r'(?:message|msg|text|send)?\s*(?:on\s+)?(?:whats\s?app|whatsapp)?\s*'
        r'(?:to\s+)?',
        re.IGNORECASE,
    )
    _WA_LEADING_PHONE_RE = re.compile(r'^\+?\s*\d[\d\s\-()]{6,}\d')
    # "papa on WhatsApp hello" puts the app name in the middle. Without removing
    # it the message body came out as "on WhatsApp hello".
    _WA_MIDDLE_APP_RE = re.compile(
        r'\s*\b(?:on|in|via|through|over|using)\s+whats\s?app\b\s*', re.IGNORECASE
    )
    _WA_CONNECTOR_RE = re.compile(
        r'^(?:saying|say|that\s+says|that|with\s+text|:|-)\s+', re.IGNORECASE
    )

    # "... to +917988280245" / "... to bhumi" at the END of the command. English
    # puts the recipient last as often as first ("send message "Hi" to +91…"),
    # and reading only the leading form made "message" itself the recipient.
    _WA_TRAILING_TARGET_RE = re.compile(
        r'\s+to\s+(?P<target>\+?[\d][\d\s\-().]{6,20}|[^\s,"]+)\s*$', re.IGNORECASE
    )
    _WA_QUOTED_RE = re.compile(r'["“‘\']([^"”’\']+)["”’\']')

    def _parse_whatsapp_command(self, command: str) -> Tuple[str, str]:
        """
        Returns (target, text). Either may be '' when absent.

        Handles both orders, because both are natural:
            message +919876543210 saying hi          target first
            send message "Hi" to +919876543210       target last
        """
        work = (command or "").strip()
        # Drop a mid-sentence "on WhatsApp" so it cannot become message text.
        work = self._WA_MIDDLE_APP_RE.sub(" ", work).strip()

        # 1. A trailing "to <target>" is the recipient — take it before anything
        #    else, so it cannot be mistaken for part of the message.
        target = ""
        trailing = self._WA_TRAILING_TARGET_RE.search(work)
        if trailing:
            target = trailing.group("target").strip()
            work = work[:trailing.start()].strip()

        rest = self._WA_PREFIX_RE.sub("", work, count=1).strip()

        # 2. A quoted span is the message, wherever it sits.
        quoted = self._WA_QUOTED_RE.search(rest)
        if quoted:
            text = quoted.group(1).strip()
            leftover = (rest[:quoted.start()] + " " + rest[quoted.end():]).strip()
            if not target:
                target = self._WA_CONNECTOR_RE.sub("", leftover, count=1).strip()
            return self._clean_wa_target(target), text

        if not rest:
            return self._clean_wa_target(target), ""

        # 3. Otherwise: leading target, then the message.
        if not target:
            phone_match = self._WA_LEADING_PHONE_RE.match(rest)
            if phone_match:
                target = phone_match.group(0).strip()
                rest = rest[phone_match.end():].strip()
            else:
                parts = rest.split(None, 1)
                target = parts[0]
                rest = parts[1].strip() if len(parts) > 1 else ""

        text = self._WA_CONNECTOR_RE.sub("", rest, count=1).strip()
        return self._clean_wa_target(target), text

    # Filler that must never be treated as a recipient. "message" reaching the
    # contact lookup is what let an unrelated saved transcript supply a number.
    _WA_NON_TARGETS = {
        "message", "msg", "text", "send", "whatsapp", "whats", "app", "a", "the",
        "and", "on", "to", "saying", "say", "that", "with", "please", "open",
    }

    def _clean_wa_target(self, target: str) -> str:
        target = (target or "").strip().strip(",:;\"'")
        return "" if target.lower() in self._WA_NON_TARGETS else target

    def _handle_whatsapp(self, command: str, cmd_lower: str) -> Dict[str, Any]:
        """
        Routes a WhatsApp request.

        Preparing a message is Tier 1 — it opens the chat with the text typed and
        nothing leaves the machine. Actually sending it is Tier 2 and goes through
        the approval gate, because it is irreversible and outward-facing.
        """
        target, text = self._parse_whatsapp_command(command)
        if not target:
            res = self.computer_agent.launch_application("whatsapp")
            if res.get("success"):
                res["message"] = (
                    "✓ Opened WhatsApp. To have me prepare a message, try: "
                    "message +919876543210 saying hello"
                )
            return res

        # A target that is clearly meant to be a number, but is not a valid one,
        # deserves to be told so — "I don't have a phone number for '79828 0245'"
        # reads as if it were a contact name we failed to look up.
        if (
            re.fullmatch(r'[\d\s\-+().]{4,}', target or "")
            and not self.comms_agent.normalise_phone(target)
        ):
            digits = re.sub(r'\D', '', target)
            return {
                "success": False,
                "error": "BAD_PHONE",
                "requested_contact": target,
                "message": (
                    f"'{target.strip()}' isn't a valid number — I count {len(digits)} "
                    f"digits. Indian mobiles are 10 digits (9876543210, I'll add +91); "
                    f"for other countries include the code (+1 555 123 4567)."
                ),
            }

        resolved = self._resolve_phone_number(target)
        if not resolved.get("phone"):
            # Park the request so the next message can supply the number and the
            # original instruction resumes. Previously the user was told to run a
            # `remember ...` command and then retype the whole thing.
            self.pending_clarification = {
                "type": "contact_number_prompt",
                "step": "get_contact_number",
                "name": target,
                "pending_text": text,
                "original_command": command,
            }
            return {
                "success": False,
                "error": resolved.get("error", "NO_NUMBER"),
                "requested_contact": target,
                "pending_clarification": True,
                "awaiting_contact_number": True,
                "message": (
                    f"I don't have a phone number for '{target}'.\n"
                    f"  What's their number? (10 digits is fine — I'll assume +91)"
                ),
            }
        phone = resolved["phone"]

        # Open the chat with the message typed, and stop there — for both the
        # text and no-text cases. Tier 1: nothing leaves the machine.
        #
        # This used to gate on Tier 2 and then simulate an Enter keypress, and
        # it did not work. Reported in live use on 2026-08-13: the gate was
        # approved, the reply said "Opened the chat for +91… and pressed Enter",
        # and no message was sent. That path was never reliable and could not be
        # made so — `pyautogui.press("enter")` goes to whatever window has focus
        # after a fixed 8-second sleep, so WhatsApp loading slowly, a
        # notification, or the user clicking anywhere sends the keystroke
        # somewhere else. Nothing here can read WhatsApp back to find out.
        #
        # So the honest version is the one the user asked for: type it into the
        # box and let them press Enter. That is also what the deep link is
        # designed for — `whatsapp://send?…&text=…` pre-fills deliberately and
        # declines to send, which is anti-spam design, not an obstacle to route
        # around. A confirmation prompt is pointless once nothing is transmitted,
        # so the Tier-2 gate goes with it: it was guarding a keypress that
        # usually missed.
        return self.comms_agent.open_whatsapp_chat(phone, text)
