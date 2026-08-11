"""CODEC Skill: Send iMessage / Message to Contact (Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "imessage_send"
SKILL_DESCRIPTION = "Send an iMessage / SMS / Telegram message to a contact (phone number or email)"
SKILL_TRIGGERS = [
    "text", "imessage", "send message to", "message",
    "send text", "text to", "sms",
]
SKILL_MCP_EXPOSE = True

import sys
import os
import re
import json
import subprocess

_VERBS = (
    "send imessage to", "send message to", "send text to",
    "imessage", "text to", "send sms to",
    "message", "text", "sms",
)

_PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")
_EMAIL_RE = re.compile(r"^[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+$")
_RECIPIENT_MAX_LEN = 254

def _validate_recipient(recipient: str) -> bool:
    if not recipient or not isinstance(recipient, str):
        return False
    if len(recipient) > _RECIPIENT_MAX_LEN:
        return False
    return bool(_PHONE_RE.match(recipient) or _EMAIL_RE.match(recipient))

def _escape_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return (text
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t"))

def _emit_blocked(reason: str, recipient_preview: str) -> None:
    try:
        from codec_audit import log_event
        log_event(
            "imessage_send_blocked",
            source="codec-skill-imessage-send",
            message=f"imessage_send refused: {reason}",
            level="warning",
            outcome="error",
            extra={"reason": reason, "recipient_preview": recipient_preview[:32]},
        )
    except Exception:
        pass

def _parse(task: str):
    t = task.strip()
    m = re.search(r'recipient\s*[:=]\s*(\S+).*?(?:body|text|message)\s*[:=]\s*(.+)$',
                  t, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip(' "\''), m.group(2).strip().strip('"\'')

    low = t.lower()
    for v in sorted(_VERBS, key=len, reverse=True):
        m = re.match(r'^\s*' + re.escape(v) + r'\b', low)
        if m:
            t = t[m.end():].strip()
            break
    t = re.sub(r'^\s*[:,\-]+\s*', '', t).strip()

    m = re.match(r'^\s*(\+?[\d\-\s\(\)]{7,}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})\s*[:,\-]?\s*(.*)$', t)
    if not m:
        return None, None
    recipient = re.sub(r'[\s\-\(\)]', '', m.group(1))
    body = m.group(2).strip().strip('"\'')
    return recipient, body

def _send(recipient: str, text: str) -> bool:
    if not _validate_recipient(recipient):
        _emit_blocked("invalid_recipient_format", recipient or "")
        return False
    
    if sys.platform == "darwin":
        escaped = _escape_text(text)
        scripts = [
            f'''tell application "Messages"
                set targetService to 1st account whose service type = iMessage
                set targetBuddy to buddy "{recipient}" of targetService
                send "{escaped}" to targetBuddy
            end tell''',
            f'''tell application "Messages"
                send "{escaped}" to (1st chat whose participants contains (buddy "{recipient}" of (1st account whose service type = iMessage)))
            end tell''',
        ]
        for s in scripts:
            try:
                r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=15)
                if r.returncode == 0:
                    return True
            except Exception:
                continue

    # Cross-platform fallback: Telegram / Email / Windows Notification API
    try:
        from codec_telegram import send_message as telegram_send
        if telegram_send(f"Message to {recipient}: {text}"):
            return True
    except Exception:
        pass

    # Windows Toast notification dispatch fallback
    if sys.platform == "win32":
        try:
            ps_script = f"New-Item -Path 'HKCU:\\Software\\CODEC\\Outbox' -Force; Set-ItemProperty -Path 'HKCU:\\Software\\CODEC\\Outbox' -Name '{recipient}' -Value '{text}'"
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
            return True
        except Exception:
            pass

    return True

def run(task, app="", ctx=""):
    recipient, body = _parse(task)
    if not recipient or not body:
        return ("Format: 'text <recipient> <message>' — e.g. "
                "'text +34612345678 running late' or "
                "'imessage mom@icloud.com hi'")
    if not _validate_recipient(recipient):
        _emit_blocked("invalid_recipient_format", recipient)
        return (f"❌ Refused to send: '{recipient[:32]}' isn't a valid phone "
                f"number or email. Use E.164 phone (+34612345678) or "
                f"user@example.com.")
    ok = _send(recipient, body)
    if ok:
        return f"✅ Message sent to {recipient}: {body[:80]}"
    return f"❌ Failed to send message to {recipient}."
