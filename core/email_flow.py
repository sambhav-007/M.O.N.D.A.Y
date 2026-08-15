"""
M.O.N.D.A.Y. — composing, confirming and sending email.

The only genuinely irreversible thing this assistant does, so the shape
matters more than the code: **draft → show → ask → send**, and the send only
ever happens in a separate confirming turn.

`_handle_send_email` ignores `user_approved` deliberately. `ui/index.html`
used to post `user_approved: true` on *every* command, so honouring it fired
a real email off the first message the user typed. Approval for a Tier-2
action can only come from an explicit answer to the question it asks.

Moved out of `core/planner.py` as a mixin when the substring chain was
removed. The wizard entry point (`_start_email_wizard`) existed **twice** in
that chain, ~130 lines apart, with different behaviour in each copy — one
invented `recipient@example.com` as the recipient, the other refused. Which
ran depended on which keyword list matched first. One copy now, and it is
the one that refuses to invent an address.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from core.tier2 import parse_confirmation


class EmailMixin:
    """Email parsing, the step-by-step composer, and the gated send."""

    # "send mail to a@b.com subject: "Hi" body: "There"" and friends. Quotes may
    # be straight or curly; subject/body may also run unquoted to the next keyword.
    _EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    # The separator is optional when the value is quoted, so both
    # `subject: "Hi"` and `subject "Hi"` work. Unquoted values still require a
    # ':' or '=' — otherwise "subject" would swallow the rest of the sentence.
    _SUBJECT_RE = re.compile(
        r'subject\s*(?:[:=]\s*)?["“‘\']([^"”’\']*)["”’\']'
        r'|subject\s*[:=]\s*([^"\n]+?)(?=\s+(?:body|message|content)\b|$)',
        re.IGNORECASE,
    )
    _BODY_RE = re.compile(
        r'(?:body|message|content)\s*(?:[:=]\s*)?["“‘\']([^"”’\']*)["”’\']'
        r'|(?:body|message|content)\s*[:=]\s*([^"\n]+?)$',
        re.IGNORECASE,
    )

    def _resolve_email_clarification(
        self, clarification: Dict[str, Any], user_response: str
    ) -> Dict[str, Any]:
        """Advances a paused email conversation by one step.

        Everything the planner's multi-turn state machine can be in that is
        not a Tier-2 gate or a contact-number prompt is an email step:
        confirming a send, collecting the subject, collecting the body, or
        resolving which contact was meant. The planner delegates the whole
        tail here rather than holding 200 lines of email conversation in the
        class that also runs the ML pipeline.

        The `confirm_send` branch is the one to read carefully. A reply that
        is neither yes nor no is tried as an **edit** before it is given up
        on: someone shown `(no subject)` naturally types `subject: hello
        body: hii`, and answering that with "I didn't catch that" strands
        them — the draft could not be corrected, and the only ways out were
        sending it empty or cancelling.
        """
        raw_ans = user_response.strip()
        c_step = clarification.get("step", "resolve_contact")
        target_name = clarification.get("target_name", "contact")
        candidates = clarification.get("candidates", [])

        if c_step == "confirm_send":
            verdict = parse_confirmation(raw_ans)

            to_email = clarification["to_email"]
            subject = clarification.get("subject", "(no subject)")
            body = clarification.get("body", "")
            draft_id = clarification.get("draft_id")

            if verdict == "yes":
                result = self._send_confirmed_email(to_email, subject, body, draft_id)
            elif verdict == "no":
                result = {
                    "success": True,
                    "delivered": False,
                    "cancelled": True,
                    "to": to_email,
                    "draft_id": draft_id,
                    "message": f"Cancelled — nothing was sent. The draft for {to_email} is still saved.",
                }
            else:
                # Before giving up: the reply may be an edit rather than an
                # answer. Someone shown "(no subject)" naturally types
                # `subject: hello body: hii`, and answering that with "I didn't
                # catch that" strands them — the draft cannot be corrected and
                # the only ways out are sending it empty or cancelling.
                edit = self._parse_email_command(user_response)
                if edit["subject"] or edit["body"]:
                    subject = edit["subject"] or subject
                    body = edit["body"] or body
                    draft_res = self.comms_agent.draft_email(to_email, subject, body)
                    draft_id = draft_res.get("draft_id", draft_id)
                    self.pending_clarification = {
                        **clarification,
                        "subject": subject,
                        "body": body,
                        "draft_id": draft_id,
                    }
                    preview = body if len(body) <= 160 else body[:160] + "…"
                    result = {
                        "success": True,
                        "pending_clarification": True,
                        "awaiting_send_confirmation": True,
                        "updated": True,
                        "to": to_email,
                        "subject": subject,
                        "body": body,
                        "draft_id": draft_id,
                        "message": (
                            f"📧 Draft updated.\n"
                            f"  To      : {to_email}\n"
                            f"  Subject : {subject}\n"
                            f"  Body    : {preview}\n\n"
                            f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
                        ),
                    }
                else:
                    # Genuinely unrecognised: re-arm rather than guess about a send.
                    self.pending_clarification = clarification
                    result = {
                        "success": False,
                        "pending_clarification": True,
                        "awaiting_send_confirmation": True,
                        "message": (
                            f"I didn't catch that. Reply 'send' to deliver the email to "
                            f"{to_email}, 'cancel' to keep it as a draft, or give me the "
                            f'missing parts, e.g. subject "Hi" body "Hello".'
                        ),
                    }

            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_send_confirm", "clo": "CLO05"},
                "execution_result": result,
            }

        if c_step == "get_subject":
            subject_val = user_response.strip()
            self.pending_clarification = {
                "type": "email_wizard",
                "step": "get_body",
                "to_email": clarification["to_email"],
                "subject": subject_val,
                "body": None,
                "original_command": clarification.get("original_command", "")
            }
            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_wizard", "clo": "CLO05"},
                "execution_result": {
                    "success": True,
                    "pending_clarification": True,
                    "message": f"✓ Subject set to '{subject_val}'! What should the email message body say?"
                }
            }

        if c_step == "get_body":
            body_val = user_response.strip()
            to_email = clarification["to_email"]
            subject_val = clarification.get("subject", "Automated Assistant Request")
            self.pending_clarification = None  # Clear wizard state

            res = self.comms_agent.draft_email(to_email, subject_val, body_val)

            # Hand straight over to the send confirmation instead of stopping
            # at a draft the user then has no way to send.
            self.pending_clarification = {
                "type": "email_send_confirm",
                "step": "confirm_send",
                "to_email": to_email,
                "subject": subject_val,
                "body": body_val,
                "draft_id": res.get("draft_id"),
                "original_command": clarification.get("original_command", ""),
            }
            preview = body_val if len(body_val) <= 160 else body_val[:160] + "…"
            return {
                "user_command": user_response,
                "clarification_resumed": True,
                "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
                "rl_routing": {"strategy": "email_wizard_complete", "clo": "CLO05"},
                "execution_result": {
                    "success": True,
                    "pending_clarification": True,
                    "awaiting_send_confirmation": True,
                    "draft_id": res.get("draft_id"),
                    "to": to_email,
                    "subject": subject_val,
                    "body": body_val,
                    "gmail_compose_url": res.get("gmail_compose_url"),
                    "message": (
                        f"📧 Draft ready.\n"
                        f"  To      : {to_email}\n"
                        f"  Subject : {subject_val}\n"
                        f"  Body    : {preview}\n\n"
                        f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
                    ),
                }
            }

        # Step 1: Contact Disambiguation
        resolved_email = None
        if candidates:
            if raw_ans.isdigit():
                idx = int(raw_ans) - 1
                if 0 <= idx < len(candidates):
                    resolved_email = candidates[idx]["email"]
            if not resolved_email:
                for c in candidates:
                    if raw_ans.lower() in c["name"].lower() or raw_ans.lower() in c["email"].lower():
                        resolved_email = c["email"]
                        break

        if not resolved_email:
            if "@" in raw_ans and "." in raw_ans:
                resolved_email = raw_ans
            else:
                self.pending_clarification = clarification
                return {
                    "user_command": user_response,
                    "clarification_resumed": False,
                    "execution_result": {
                        "success": False,
                        "pending_clarification": True,
                        "message": f"🔒 Invalid Selection: '{raw_ans}' didn't match any candidate or valid email. Please enter a valid candidate number or full email address."
                    }
                }

        # Cache this resolved contact in SQLite memory so future calls are instant
        self.memory_agent.remember(f"{target_name} email", resolved_email, topic="contacts")

        # Ask for Subject next
        self.pending_clarification = {
            "type": "email_wizard",
            "step": "get_subject",
            "to_email": resolved_email,
            "subject": None,
            "body": None,
            "original_command": clarification.get("original_command", "")
        }

        return {
            "user_command": user_response,
            "clarification_resumed": True,
            "intent_classification": {"predicted_intent": "communication", "confidence": 1.0, "llm_fallback": False, "clo": "CLO04"},
            "rl_routing": {"strategy": "email_wizard", "clo": "CLO05"},
            "execution_result": {
                "success": True,
                "pending_clarification": True,
                "to": resolved_email,
                "message": f"✓ Contact resolved to '{resolved_email}'! What is the subject of the email?"
            }
        }

    def _parse_email_command(self, command: str) -> Dict[str, str]:
        """Pulls recipient, subject and body out of a free-form email command.

        Returns a dict with 'recipient' (an address, or a bare name to resolve
        against contacts), 'subject' and 'body' — each '' when absent.
        """
        recipient = ""
        addr = self._EMAIL_RE.search(command)
        if addr:
            recipient = addr.group(0)
        else:
            # "to <name>" — stop before the subject/body keywords.
            name = re.search(
                r'\bto\s+([^\n,]+?)(?=\s+(?:subject|body|message|content)\b|$)',
                command, re.IGNORECASE,
            )
            if name:
                recipient = name.group(1).strip()

        def _first(match) -> str:
            if not match:
                return ""
            return (match.group(1) or match.group(2) or "").strip()

        return {
            "recipient": recipient,
            "subject": _first(self._SUBJECT_RE.search(command)),
            "body": _first(self._BODY_RE.search(command)),
        }

    def _handle_send_email(self, command: str, user_approved: bool) -> Dict[str, Any]:
        """Parses a 'send mail ...' command and runs the draft → send sequence.

        Previously the whole raw command was handed to send_email() as the
        recipient, so errors read "Cannot send email to 'send mail to a@b.com
        subject: ...'" and neither subject nor body was ever captured.
        """
        parsed = self._parse_email_command(command)
        recipient = parsed["recipient"]

        if not recipient:
            return {
                "success": False,
                "error": "NO_RECIPIENT",
                "message": (
                    "I couldn't find a recipient in that command. Try: "
                    'send mail to name@example.com subject: "Hi" body: "Hello"'
                ),
            }

        # A bare name has to be resolved against real contacts first.
        if "@" not in recipient:
            from agents.comms_agent import search_local_contacts
            matches = search_local_contacts(recipient)
            if len(matches) == 1:
                recipient = matches[0]["email"]
            elif len(matches) > 1:
                self.pending_clarification = {
                    "type": "contact_disambiguation",
                    "target_name": recipient,
                    "candidates": matches,
                    "original_command": command,
                }
                c_str = ", ".join(
                    f"({i+1}) {c['name']} ({c['email']})" for i, c in enumerate(matches)
                )
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "pending_clarification": True,
                    "candidates": matches,
                    "target_name": recipient,
                    "message": f"🔒 Multiple Contacts Found: {c_str}. Which one did you mean?",
                }
            else:
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "target_name": recipient,
                    "message": (
                        f"🔒 Contact Unresolved: no email address found for "
                        f"'{recipient}'. Give me the address directly."
                    ),
                }

        # "send mail to someone@example.com" with no subject or body used to jump
        # straight to "Send it? (no subject), empty body" — offering to send an
        # empty email, and leaving the user no way to supply the missing parts.
        # Collect them first instead; the wizard ends at the same confirmation.
        if not parsed["subject"] and not parsed["body"]:
            self.pending_clarification = {
                "type": "email_wizard",
                "step": "get_subject",
                "to_email": recipient,
                "subject": None,
                "body": None,
                "original_command": command,
            }
            return {
                "success": True,
                "pending_clarification": True,
                "awaiting_subject": True,
                "to": recipient,
                "message": (
                    f"📧 Composing an email to {recipient}.\n"
                    f"What should the subject be?\n\n"
                    f"(Or give it all at once: send mail to {recipient} "
                    f'subject "Hi" body "Hello")'
                ),
            }

        subject = parsed["subject"] or "(no subject)"
        body = parsed["body"] or ""

        # Persist the draft before the Tier-2 send, so a composed message
        # survives an unconfigured or failing transport.
        draft_res = self.comms_agent.draft_email(recipient, subject, body)

        # Sending is irreversible, so ALWAYS confirm — deliberately ignoring
        # `user_approved` here. The UI posts user_approved=true on every command,
        # so honouring it would silently fire the mail off the first message.
        # _resolve_clarification performs the send only on an explicit yes.
        self.pending_clarification = {
            "type": "email_send_confirm",
            "step": "confirm_send",
            "to_email": recipient,
            "subject": subject,
            "body": body,
            "draft_id": draft_res.get("draft_id"),
            "original_command": command,
        }
        preview = body if len(body) <= 160 else body[:160] + "…"
        return {
            "success": True,
            "pending_clarification": True,
            "awaiting_send_confirmation": True,
            "to": recipient,
            "subject": subject,
            "body": body,
            "draft_id": draft_res.get("draft_id"),
            "message": (
                f"📧 Draft ready.\n"
                f"  To      : {recipient}\n"
                f"  Subject : {subject}\n"
                f"  Body    : {preview}\n\n"
                f"Send it? Reply 'send' to deliver, or 'cancel' to keep it as a draft."
            ),
        }

    def _send_confirmed_email(
        self, recipient: str, subject: str, body: str, draft_id: Optional[str]
    ) -> Dict[str, Any]:
        """Performs the approved Tier-2 send and annotates the result."""
        send_res = self.comms_agent.send_email(
            recipient, user_approved=True, subject=subject, body=body
        )
        send_res["to"] = recipient
        send_res["subject"] = subject
        send_res["body"] = body
        if draft_id:
            send_res["draft_id"] = draft_id
        return send_res

    def _start_email_wizard(self, command: str) -> Dict[str, Any]:
        """Resolves a recipient and opens the step-by-step email composer.

        This existed **twice** in the substring chain, ~130 lines apart, with
        different behaviour in each copy: one defaulted an unknown recipient to
        `recipient@example.com` and started composing to a placeholder address,
        the other returned "No email recipient specified". Which one ran was
        decided by whichever keyword list matched first. One copy now, and it
        keeps the branch that refuses to invent an address.
        """
        to_match = re.search(r'to\s+([^\s,"]+(?:\s+[^\s,"]+)?)', command, re.IGNORECASE)
        raw_target = to_match.group(1).strip() if to_match else ""

        if not raw_target:
            return {
                "success": False,
                "error": "NO_RECIPIENT",
                "message": (
                    "Who should I send it to? Try: draft email to "
                    "name@example.com"
                ),
            }

        if "@" in raw_target:
            to_email = raw_target
        else:
            from agents.comms_agent import search_local_contacts
            matches = search_local_contacts(raw_target)
            if len(matches) == 1:
                to_email = matches[0]["email"]
            elif len(matches) > 1:
                self.pending_clarification = {
                    "type": "contact_disambiguation",
                    "target_name": raw_target,
                    "candidates": matches,
                    "original_command": command,
                }
                c_str = ", ".join(
                    f"({i+1}) {c['name']} ({c['email']})" for i, c in enumerate(matches)
                )
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "pending_clarification": True,
                    "candidates": matches,
                    "target_name": raw_target,
                    "message": (
                        f"🔒 Multiple Contacts Found: I found {len(matches)} contacts "
                        f"matching '{raw_target}': {c_str}. Which one did you mean?"
                    ),
                }
            else:
                self.pending_clarification = {
                    "type": "contact_disambiguation",
                    "target_name": raw_target,
                    "original_command": command,
                }
                return {
                    "success": False,
                    "contact_unresolved": True,
                    "pending_clarification": True,
                    "target_name": raw_target,
                    "message": (
                        f"🔒 Contact Unresolved: I couldn't find an email address "
                        f"for '{raw_target}' in local contacts or memory. What is "
                        f"{raw_target}'s email address?"
                    ),
                }

        self.pending_clarification = {
            "type": "email_wizard",
            "step": "get_subject",
            "to_email": to_email,
            "subject": None,
            "body": None,
            "original_command": command,
        }
        return {
            "success": True,
            "pending_clarification": True,
            "to": to_email,
            "message": f"✓ Recipient set to '{to_email}'! What is the subject of the email?",
        }
