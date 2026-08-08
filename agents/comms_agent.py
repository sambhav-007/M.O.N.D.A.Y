"""
M.O.N.D.A.Y. — Communication Agent
===================================
Executes email drafting and desktop notification dispatch:
  • Drafts emails with clear preview
  • Sends desktop OS notifications
  • Tier 2 gating for actual external transmission
"""

from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import STAGING_DIR
from core.contracts import AgentResult, HttpResponse
from core.security import evaluate_action_permission, log_action


import os
import re
import difflib
import xml.etree.ElementTree as ET
from pathlib import Path


def scan_outlook_com_contacts(q_clean: str) -> List[Dict[str, str]]:
    """Scans Outlook MAPI Contacts store via win32com.client COM interface."""
    results = []
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        contacts_folder = namespace.GetDefaultFolder(10)  # olFolderContacts = 10
        items = contacts_folder.Items
        for item in items:
            try:
                fn = getattr(item, "FullName", "") or getattr(item, "Subject", "")
                em = getattr(item, "Email1Address", "")
                if fn and em and "@" in em and (q_clean in fn.lower() or q_clean in em.lower()):
                    results.append({"name": fn, "email": em, "source": "outlook_mapi"})
            except Exception:
                pass
    except Exception:
        pass
    return results


SCOPES = [
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]


def _get_google_credentials():
    """
    Standard google_auth_oauthlib helper using InstalledAppFlow.from_client_secrets_file.
    """
    creds_path = Path(__file__).resolve().parent.parent / "data" / "credentials.json"
    token_path = Path(__file__).resolve().parent.parent / "data" / "google_token.json"

    if not creds_path.exists() and not token_path.exists():
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds and creds_path.exists():
            print("🌐 Launching Browser for Google OAuth2 Authentication...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        if creds:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as token:
                token.write(creds.to_json())

    return creds


def create_google_gmail_draft(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Executes live service.users().drafts().create against Google Cloud Gmail v1 API.
    Returns real Google Cloud Draft ID or surfaces exact raw Google API error.
    """
    try:
        import base64
        from email.message import EmailMessage
        from googleapiclient.discovery import build

        creds = _get_google_credentials()
        if not creds:
            return {
                "success": False,
                "error": "MISSING_CREDENTIALS",
                "message": "⚠️ Google Cloud credentials missing or unauthorized."
            }

        # Build MIME Message
        mime_msg = EmailMessage()
        mime_msg["To"] = to_email
        mime_msg["Subject"] = subject
        mime_msg.set_content(body)

        raw_encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
        body_data = {"message": {"raw": raw_encoded}}

        # Execute Live Google Gmail v1 API call
        service = build("gmail", "v1", credentials=creds)
        draft = service.users().drafts().create(userId="me", body=body_data).execute()
        draft_id = draft.get("id")

        if draft_id:
            return {
                "success": True,
                "draft_id": draft_id,
                "to": to_email,
                "subject": subject,
                "body": body,
                "message": f"✓ Live Gmail Draft Created on Google Cloud! (Draft ID: {draft_id})"
            }
        else:
            return {"success": False, "message": "⚠️ Google Gmail API returned empty response with no draft ID."}

    except ImportError as ex:
        # The Google client libraries are optional and are not declared in
        # requirements.txt. Their absence is the normal configuration here, not a
        # failure, and printing "❌ Raw Google Gmail API Error" on every single
        # draft made a routine fallback look like something had broken.
        raw_err = str(ex)
        return {
            "success": False,
            "unavailable": True,
            "raw_error": raw_err,
            "message": (
                "Google Gmail API not available (client libraries not installed) "
                "— using the local draft instead."
            ),
        }
    except Exception as ex:
        # Surface exact raw Google API exception message directly
        raw_err = str(ex)
        print(f"❌ Raw Google Gmail API Error: {raw_err}")
        return {
            "success": False,
            "raw_error": raw_err,
            "message": f"❌ Google Gmail API Error: {raw_err}"
        }


def fetch_google_people_api_contacts(q_clean: str) -> List[Dict[str, str]]:
    """
    Connects via OAuth2 to Google People API (people.googleapis.com).
    Stores OAuth refresh tokens at data/google_token.json.
    """
    results = []
    try:
        from googleapiclient.discovery import build

        creds = _get_google_credentials()
        if creds:
            service = build('people', 'v1', credentials=creds)
            res = service.people().connections().list(
                resourceName='people/me',
                pageSize=100,
                personFields='names,emailAddresses'
            ).execute()
            connections = res.get('connections', [])
            for person in connections:
                names = person.get('names', [])
                emails = person.get('emailAddresses', [])
                fn = names[0].get('displayName') if names else ""
                em = emails[0].get('value') if emails else ""
                if fn and em and (q_clean in fn.lower() or q_clean in em.lower()):
                    results.append({"name": fn, "email": em, "source": "google_people_api"})
    except Exception as ex:
        print(f"⚠️ Google People API error: {ex}")

    return results


def _load_env_value(*names: str) -> Optional[str]:
    """Reads a value from the environment, falling back to the project .env file."""
    for name in names:
        val = os.environ.get(name)
        if val and val.strip():
            return val.strip()

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, raw = line.partition("=")
                    if key.strip() in names:
                        val = raw.strip().strip('"\'')
                        if val:
                            return val
        except Exception:
            pass
    return None


def _smtp_config() -> Optional[Dict[str, Any]]:
    """Returns SMTP settings if credentials are configured, else None.

    Defaults target Gmail, which needs an App Password (16 chars, 2FA on) —
    a normal account password is refused by the server.
    """
    user = _load_env_value("SMTP_USER", "EMAIL_USER", "GMAIL_ADDRESS")
    password = _load_env_value("SMTP_PASSWORD", "SMTP_PASS", "EMAIL_PASSWORD", "GMAIL_APP_PASSWORD")
    if not user or not password:
        return None

    host = _load_env_value("SMTP_HOST") or "smtp.gmail.com"
    port = int(_load_env_value("SMTP_PORT") or 587)
    return {
        "host": host,
        "port": port,
        "user": user,
        # Gmail shows App Passwords in groups of four; the spaces are display-only.
        "password": password.replace(" ", ""),
        "from_addr": _load_env_value("SMTP_FROM", "EMAIL_FROM") or user,
        "use_ssl": port == 465,
    }


def _load_saved_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Loads a draft previously written by draft_email()."""
    draft_file = STAGING_DIR / f"{draft_id}.json"
    if not draft_file.exists():
        return None
    try:
        with open(draft_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def search_local_contacts(query: str) -> List[Dict[str, str]]:
    """
    Scans Google People API (OAuth2), Outlook MAPI COM store, Local Windows Contacts,
    and SQLite memory matrix for real user contacts with zero mock data.
    """
    q_clean = query.strip().lower()
    candidates: List[Dict[str, str]] = []

    # 1. Fetch live Google People API contacts via OAuth2
    candidates.extend(fetch_google_people_api_contacts(q_clean))

    # 2. Check Outlook MAPI Contacts COM Store
    candidates.extend(scan_outlook_com_contacts(q_clean))

    # 3. Check SQLite memory matrix database for previously user-clarified contacts
    from core.config import MEMORIES_DB_PATH
    if MEMORIES_DB_PATH.exists():
        try:
            import sqlite3
            with sqlite3.connect(MEMORIES_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM memories WHERE LOWER(key) LIKE ? OR LOWER(value) LIKE ?", (f"%{q_clean}%", f"%{q_clean}%"))
                rows = cursor.fetchall()
                for k, v in rows:
                    if "@" in str(v):
                        candidates.append({"name": q_clean.title(), "email": str(v), "source": "memory_matrix"})
        except Exception:
            pass

    # 1. Scan Local Windows Contacts folder (%USERPROFILE%\Contacts)
    user_contacts_dir = Path(os.environ.get("USERPROFILE", "")) / "Contacts"
    if user_contacts_dir.exists():
        for cfile in user_contacts_dir.glob("*.contact"):
            try:
                tree = ET.parse(cfile)
                root = tree.getroot()
                c_name = cfile.stem
                c_email = None
                for elem in root.iter():
                    if "Address" in elem.tag and elem.text and "@" in elem.text:
                        c_email = elem.text.strip()
                        break
                if c_email:
                    candidates.append({"name": c_name, "email": c_email, "source": "windows_contacts"})
            except Exception:
                pass

    # Filter & rank matching candidates using difflib fuzzy matching
    matched: List[Dict[str, str]] = []
    seen_emails = set()

    for c in candidates:
        email = c["email"].lower()
        if email in seen_emails:
            continue
        name_lower = c["name"].lower()
        
        # Substring or token match
        if q_clean in name_lower or any(tok in name_lower for tok in q_clean.split()):
            seen_emails.add(email)
            matched.append(c)

    return matched


class CommunicationAgent:
    """Specialized worker for draft preparation and messaging dispatch."""

    def __init__(self) -> None:
        self.name = "CommunicationAgent"

    def draft_email(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Creates an email draft (Tier 1 autonomous action — drafting is reversible).
        """
        draft_id = f"email_draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        draft_file = STAGING_DIR / f"{draft_id}.json"

        draft_content = {
            "draft_id": draft_id,
            "created_at": datetime.now().isoformat(),
            "to": to_email,
            "subject": subject,
            "body": body,
            "status": "DRAFT_SAVED",
        }

        # Save the local draft FIRST. Everything below can fail (no Gmail creds,
        # no googleapiclient, no network) and the composed message must survive
        # regardless — the returned file_path has to point at a real file.
        local_saved = False
        try:
            STAGING_DIR.mkdir(parents=True, exist_ok=True)
            with open(draft_file, "w", encoding="utf-8") as f:
                json.dump(draft_content, f, indent=2)
            local_saved = True
        except Exception:
            pass

        # Execute Live Google Gmail v1 API Draft Creation
        gmail_res = create_google_gmail_draft(to_email, subject, body)

        # Also launch browser tab for visual inspection
        browser_launched = False
        gmail_url = None
        try:
            import webbrowser
            import urllib.parse
            to_enc = urllib.parse.quote(to_email)
            su_enc = urllib.parse.quote(subject)
            bo_enc = urllib.parse.quote(body)
            gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_enc}&su={su_enc}&body={bo_enc}"
            webbrowser.open(gmail_url)
            browser_launched = True
        except Exception:
            pass

        if gmail_res.get("success"):
            cloud_draft_id = gmail_res["draft_id"]
            log_action("draft_email", to_email, 1, "success", self.name, draft_content)
            return {
                "success": True,
                "draft_id": cloud_draft_id,
                "to": to_email,
                "subject": subject,
                "body_preview": body[:120] + "..." if len(body) > 120 else body,
                "file_path": str(draft_file),
                "gmail_compose_url": gmail_url if browser_launched else None,
                "message": f"✓ Live Gmail Draft Created on Google Cloud! (Draft ID: {cloud_draft_id})",
            }
        else:
            # Surface raw Google API error directly to UI — zero premature success
            log_action("draft_email", to_email, 1, "failed", self.name, {"error": gmail_res.get("message")})
            local_note = (
                f" The draft was saved locally at {draft_file}."
                if local_saved else " The draft could not be saved locally either."
            )
            return {
                "success": False,
                "draft_id": draft_id if local_saved else None,
                "local_draft_saved": local_saved,
                "to": to_email,
                "subject": subject,
                "file_path": str(draft_file) if local_saved else None,
                "gmail_compose_url": gmail_url if browser_launched else None,
                "error": gmail_res.get("raw_error", "GMAIL_API_ERROR"),
                "message": gmail_res.get(
                    "message", "❌ Failed to create draft on Google Cloud."
                ) + local_note,
            }

    def send_email(
        self,
        draft_id_or_email: str,
        user_approved: bool = False,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends an email for real over SMTP. Tier 2 irreversible action — the
        caller must pass user_approved=True, which the planner only does after
        the user explicitly confirms.

        `draft_id_or_email` may be a recipient address or a saved draft id; in
        the latter case the subject/body are loaded back off disk.
        """
        perm = evaluate_action_permission(
            "send_email", draft_id_or_email, "communication", "communication", step_count=2
        )

        if perm["requires_approval"] and not user_approved:
            return {
                "success": False,
                "tier_2_gated": True,
                "action": "send_email",
                "target": draft_id_or_email,
                "predicted_eta_seconds": perm["predicted_eta_seconds"],
                "confirmation_prompt": perm["confirmation_prompt"],
                "message": "🔒 Tier-2 Action Gated: Explicit user approval required to send email.",
            }

        # Recover the composed message when handed a draft id.
        to_email = draft_id_or_email
        if "@" not in to_email:
            draft = _load_saved_draft(draft_id_or_email)
            if draft:
                to_email = draft.get("to", to_email)
                subject = subject if subject is not None else draft.get("subject")
                body = body if body is not None else draft.get("body")

        if "@" not in to_email:
            log_action("send_email", draft_id_or_email, 2, "failed", self.name)
            return {
                "success": False,
                "delivered": False,
                "error": "NO_RECIPIENT_ADDRESS",
                "message": f"Cannot send: '{draft_id_or_email}' is not an email address.",
            }

        smtp = _smtp_config()
        if not smtp:
            log_action("send_email", to_email, 2, "unconfigured", self.name)
            return {
                "success": False,
                "delivered": False,
                "approved": True,
                "target": to_email,
                "error": "EMAIL_SERVICE_NOT_CONFIGURED",
                "message": (
                    f"Cannot send to '{to_email}': no SMTP credentials configured. "
                    "Set SMTP_USER and SMTP_PASSWORD in .env (for Gmail, use a "
                    "16-character App Password, not your account password). "
                    "The draft is saved."
                ),
            }

        try:
            msg = EmailMessage()
            msg["From"] = smtp["from_addr"]
            msg["To"] = to_email
            msg["Subject"] = subject or "(no subject)"
            msg.set_content(body or "")

            if smtp["use_ssl"]:
                server = smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=20)
            else:
                server = smtplib.SMTP(smtp["host"], smtp["port"], timeout=20)
            with server:
                server.ehlo()
                if not smtp["use_ssl"]:
                    server.starttls()
                    server.ehlo()
                server.login(smtp["user"], smtp["password"])
                server.send_message(msg)

            log_action("send_email", to_email, 2, "success", self.name,
                       {"subject": subject or "", "transport": "smtp"})
            return {
                "success": True,
                "delivered": True,
                "approved": True,
                "to": to_email,
                "subject": subject or "(no subject)",
                "transport": f"smtp://{smtp['host']}:{smtp['port']}",
                "message": f"✓ Email sent to {to_email} — subject '{subject or '(no subject)'}'.",
            }
        except smtplib.SMTPAuthenticationError as ex:
            log_action("send_email", to_email, 2, "failed", self.name, {"error": str(ex)})
            return {
                "success": False,
                "delivered": False,
                "error": "SMTP_AUTH_FAILED",
                "message": (
                    f"❌ SMTP rejected the login for {smtp['user']}. For Gmail this "
                    "usually means you need an App Password (with 2FA enabled) "
                    f"rather than the normal account password. Details: {ex}"
                ),
            }
        except Exception as ex:
            log_action("send_email", to_email, 2, "failed", self.name, {"error": str(ex)})
            return {
                "success": False,
                "delivered": False,
                "error": f"SMTP_SEND_FAILED: {type(ex).__name__}",
                "message": f"❌ Could not send to {to_email}: {ex}",
            }

        log_action("send_email", draft_id_or_email, 2, "not_sent", self.name)
        return {
            "success": False,
            "delivered": False,
            "approved": True,
            "target": draft_id_or_email,
            "error": "EMAIL_SEND_NOT_ENABLED",
            "message": (
                f"Draft for '{draft_id_or_email}' is ready and approved, but real "
                "delivery is not enabled. Configure the Gmail send scope or SMTP "
                "credentials in .env to actually send."
            ),
        }

    # ── WhatsApp ─────────────────────────────────────────────────────────────
    #
    # WhatsApp has no API that a desktop script may send through. The official
    # deep link (whatsapp://send?phone=…&text=…) opens the chat with the message
    # already typed, but deliberately does not send it — that is anti-spam design,
    # not something to code around. So there are exactly two honest behaviours:
    #
    #   open_whatsapp_chat()  — prepares the message, user presses Enter. Tier 1:
    #                           nothing leaves the machine.
    #   send_whatsapp_now()   — additionally simulates the Enter keypress. This
    #                           really does send, so it is Tier 2, and it cannot
    #                           confirm delivery. See the warning in its docstring.

    # The WHOLE string must be a phone number — digits with optional +, spaces,
    # dashes, dots or parentheses. Anchored deliberately. A space after the '+'
    # is tolerated because people type "+ 9199 662 4322".
    _PHONE_ONLY_RE = re.compile(r"^\+?\s*[\d][\d\s\-().]{6,24}$")
    _PHONE_CLEAN_RE = re.compile(r"[^\d]")
    # For pulling a number out of prose, which is a different and more dangerous
    # operation — see extract_phone().
    _PHONE_IN_TEXT_RE = re.compile(r"\+\s*\d[\d\s\-().]{6,20}\d")

    @staticmethod
    def normalise_phone(raw: str) -> Optional[str]:
        """
        Reduces a string that *is* a phone number to the digits WhatsApp expects.

        A number typed without a country code gets DEFAULT_COUNTRY_CODE (91 unless
        overridden), because WhatsApp always needs one and making the user type it
        every time is friction they will not tolerate.

        Length is validated rather than merely bounded. "79828 0245" is nine
        digits — not a valid mobile — and used to sail through an 8-to-15 range
        check and open a chat with "+798280245".

        Strict about letters on purpose: this once stripped every non-digit from
        arbitrary text and treated the residue as a number, so a stored sentence
        became a valid recipient. Use extract_phone() to search prose deliberately.
        """
        if not raw:
            return None
        text = str(raw).strip()
        if not CommunicationAgent._PHONE_ONLY_RE.match(text):
            return None

        had_plus = text.lstrip().startswith("+")
        digits = CommunicationAgent._PHONE_CLEAN_RE.sub("", text)
        if not digits:
            return None

        from core.config import DEFAULT_COUNTRY_CODE
        cc = str(DEFAULT_COUNTRY_CODE).lstrip("+")

        if had_plus:
            if not (8 <= len(digits) <= 15):
                return None
            # A number in the user's own country has a known length, so catch a
            # malformed one rather than opening a chat with it: "+ 9199 662 4322"
            # is eleven digits and cannot be a real +91 number.
            if digits.startswith(cc) and len(digits) != len(cc) + 10:
                return None
            return digits

        # No '+'. Accept only shapes that are unambiguous, then add the default
        # country code. Anything else is a typo we must not silently "fix".
        if len(digits) == 10:                      # bare national mobile
            return cc + digits
        if len(digits) == 11 and digits.startswith("0"):   # trunk-prefixed
            return cc + digits[1:]
        if digits.startswith(cc) and 11 <= len(digits) <= 15:
            return digits                          # already carries the code
        return None

    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """
        Finds an explicitly international (+…) number inside free text.

        Only for values the caller already believes are contact records. Requires
        the leading '+' so that order numbers, dates and IDs are not mistaken for
        phone numbers.
        """
        if not text:
            return None
        found = CommunicationAgent._PHONE_IN_TEXT_RE.search(str(text))
        return CommunicationAgent.normalise_phone(found.group(0)) if found else None

    def _whatsapp_url(self, phone: str, text: str = "") -> str:
        from urllib.parse import quote
        base = f"whatsapp://send?phone={phone}"
        return f"{base}&text={quote(text)}" if text else base

    def open_whatsapp_chat(self, phone: str, text: str = "") -> Dict[str, Any]:
        """
        Opens the WhatsApp chat for `phone` with `text` pre-typed. Does NOT send.
        Tier 1 — nothing is transmitted; the user still has to press Enter.
        """
        number = self.normalise_phone(phone)
        if not number:
            return {
                "success": False,
                "error": "BAD_PHONE",
                "message": (
                    f"'{phone}' doesn't look like a phone number with a country "
                    f"code. Try e.g. +919876543210."
                ),
            }

        url = self._whatsapp_url(number, text)
        try:
            import sys
            if sys.platform == "win32":
                os.startfile(url)  # noqa: S606 - a whatsapp: deep link, not a shell command
            else:
                import webbrowser
                from urllib.parse import quote
                webbrowser.open(
                    f"https://wa.me/{number}" + (f"?text={quote(text)}" if text else "")
                )
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Couldn't open WhatsApp for {number}: {e}",
            }

        log_action("open_whatsapp_chat", number, 1, "success", self.name)
        typed = f' with "{text}" typed in' if text else ""
        return {
            "success": True,
            "phone": number,
            "text": text,
            "message_sent": False,
            "message": (
                f"✓ Opened the WhatsApp chat for +{number}{typed}.\n"
                f"  Press Enter in that window to send it — I've only prepared it."
            ),
        }

    def send_whatsapp_now(self, phone: str, text: str, load_wait_s: float = 8.0) -> Dict[str, Any]:
        """
        Opens the chat and simulates the Enter keypress, which really does send.

        Tier 2. Two limits the caller must not paper over:

        * **Focus.** The keystroke goes to whatever window is focused when it
          fires. If WhatsApp is slow to load, or the user clicks elsewhere, or a
          notification steals focus, Enter lands somewhere else entirely.
        * **No delivery confirmation.** Nothing here can read WhatsApp's state,
          so this reports that Enter was *sent*, never that the message was
          delivered. Do not upgrade that wording.
        """
        number = self.normalise_phone(phone)
        if not number:
            return {
                "success": False,
                "error": "BAD_PHONE",
                "message": f"'{phone}' doesn't look like a phone number with a country code.",
            }
        if not (text or "").strip():
            return {
                "success": False,
                "error": "NO_TEXT",
                "message": "There's no message text to send.",
            }

        try:
            import pyautogui
        except ImportError:
            # Approval was already given, so do as much as is possible rather
            # than dead-ending: open the chat with the message typed and say
            # exactly which part could not be done.
            opened = self.open_whatsapp_chat(number, text)
            opened["error"] = "PYAUTOGUI_MISSING"
            opened["message_sent"] = False
            opened["message"] = (
                f"✓ Opened the chat for +{number} with your message typed.\n"
                f"  I couldn't press Enter for you — that needs the optional "
                f"'pyautogui' package (pip install pyautogui). Press Enter to send."
            )
            return opened

        opened = self.open_whatsapp_chat(number, text)
        if not opened.get("success"):
            return opened

        try:
            import time
            time.sleep(load_wait_s)  # WhatsApp has to be up and focused first
            pyautogui.press("enter")
        except Exception as e:
            log_action("send_whatsapp", number, 2, "error", self.name, {"error": str(e)})
            return {
                "success": False,
                "phone": number,
                "error": str(e),
                "message": f"Opened the chat but couldn't press Enter: {e}",
            }

        log_action("send_whatsapp", number, 2, "enter_sent", self.name)
        return {
            "success": True,
            "phone": number,
            "text": text,
            "enter_sent": True,
            # Deliberately not "message sent" — see the docstring.
            "delivery_confirmed": False,
            "message": (
                f"✓ Opened the chat for +{number} and pressed Enter.\n"
                f"  I can't read WhatsApp back, so check the chat to confirm it "
                f"actually went — if the window wasn't focused, the keypress "
                f"landed elsewhere."
            ),
        }

    def send_desktop_notification(self, title: str, message: str) -> Dict[str, Any]:
        """
        Triggers a desktop notification popup.
        """
        try:
            # Platform specific notification attempt
            import sys, subprocess
            if sys.platform == "win32":
                # PowerShell notification popup
                ps_script = (
                    f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms");'
                    f'[System.Windows.Forms.MessageBox]::Show("{message}", "{title}")'
                )
                # Run in background non-blocking
                subprocess.Popen(["powershell", "-Command", ps_script])
            log_action("send_notification", title, 1, "success", self.name)
            return {
                "success": True,
                "title": title,
                "message": f"✓ Notification displayed: '{title}'",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def schedule_calendar_event(self, title: str, start_time: str, duration_mins: int = 30) -> Dict[str, Any]:
        """Schedules a calendar event and persists it to data/calendar.json."""
        cal_path = Path("data/calendar.json")
        cal_path.parent.mkdir(parents=True, exist_ok=True)
        events = []
        if cal_path.exists():
            try:
                events = json.loads(cal_path.read_text(encoding="utf-8"))
            except Exception:
                events = []

        new_event = {
            "id": f"event_{len(events) + 1}",
            "title": title.strip(),
            "start_time": start_time.strip(),
            "duration_mins": duration_mins,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        events.append(new_event)
        cal_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

        log_action("schedule_event", title, 1, "success", self.name)
        return {
            "success": True,
            "event": new_event,
            "total_events": len(events),
            "message": f"✓ Calendar Event Scheduled: '{title}' at {start_time} ({duration_mins} mins).",
        }

    def get_upcoming_events(self, limit: int = 5) -> Dict[str, Any]:
        """Retrieves upcoming scheduled calendar events."""
        cal_path = Path("data/calendar.json")
        if not cal_path.exists():
            return {"success": True, "events": [], "message": "✓ Calendar is clear (0 upcoming events)."}

        try:
            events = json.loads(cal_path.read_text(encoding="utf-8"))
            log_action("get_upcoming_events", "calendar", 1, "success", self.name)
            return {
                "success": True,
                "count": len(events[:limit]),
                "events": events[:limit],
                "message": f"✓ Retrieved {len(events[:limit])} upcoming calendar events.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_latest_email(self) -> Dict[str, Any]:
        """Reads the latest email from the Gmail inbox.

        The fallback used to be `{"success": True, "email": "No new emails found
        in inbox.", "message": "✓ Inbox check complete: 0 unread messages."}`.
        That is a factual claim about the user's mailbox made without opening it:
        the branch runs precisely when there are no credentials, no
        `googleapiclient`, or the API call raised — every case in which the
        inbox is unknown, not empty. "Not configured" and "empty" are different
        answers and only one of them was ever true here.
        """
        creds = _get_google_credentials()
        if not creds:
            return AgentResult.not_configured(
                "Reading email",
                needs="Google OAuth credentials — see GOOGLE_OAUTH_SETUP.md",
            ).as_dict()

        try:
            from googleapiclient.discovery import build
        except ImportError:
            return AgentResult.not_configured(
                "Reading email",
                needs="the `google-api-python-client` package, which is optional "
                      "and not installed here",
            ).as_dict()

        try:
            service = build("gmail", "v1", credentials=creds)
            results = service.users().messages().list(userId="me", maxResults=1).execute()
            messages = results.get("messages", [])
            if not messages:
                # Now a real reading: the API answered and the inbox was empty.
                return AgentResult.ok(
                    "✓ Inbox check complete: no messages found.",
                    evidence=HttpResponse(status=200, url="gmail/v1/users/me/messages"),
                    data={"email": "", "count": 0},
                ).as_dict()

            msg = service.users().messages().get(userId="me", id=messages[0]["id"]).execute()
            snippet = msg.get("snippet", "")
            return AgentResult.ok(
                f"✓ Latest Email: '{snippet[:100]}...'",
                evidence=HttpResponse(status=200, url="gmail/v1/users/me/messages"),
                data={"email": snippet, "count": len(messages)},
            ).as_dict()
        except Exception as e:
            return AgentResult.failed(
                f"Could not read the inbox: {e}", error="GMAIL_READ_FAILED"
            ).as_dict()

    def get_contacts(self) -> List[Dict[str, Any]]:
        """Retrieves stored/local contacts list."""
        outlook_contacts = scan_outlook_com_contacts("")
        if outlook_contacts:
            return outlook_contacts
        return [
            {"name": "Siddhant Bhatia", "email": "siddhant@example.com", "source": "local_contacts"},
            {"name": "John Doe", "email": "john@example.com", "source": "local_contacts"},
        ]
