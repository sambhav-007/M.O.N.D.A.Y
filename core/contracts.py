"""
M.O.N.D.A.Y. — the result contract
==================================

Every handler in this project reports back as a plain dict with a `success` key.
That shape has one structural weakness, and this repo has hit it at least six
times: nothing stops a function from writing `{"success": True, "message":
"✓ Done"}` when it did nothing at all.

The history is in `handoff.md`. `CoderAgent` reported "✓ compiled plugin" for
plugins it never compiled and littered `data/plugins/` with thirteen of them.
`CommunicationAgent.send_email` reported "✓ Email successfully sent" from a
function that had no `subject` or `body` parameter and structurally could not
send. `CognitiveResponseDict.__bool__` returned `True` unconditionally, so every
failed dispatch was overwritten with a fabricated success. `BrowserAgent`
reported `success: True` with zero results when DuckDuckGo answered HTTP 202.
Each was found and fixed one at a time; the pattern kept coming back, because
nothing in the type made it hard to write.

`AgentResult` makes it hard to write. A result may only claim success if it
carries **evidence** — a concrete record of the thing that actually happened: a
process that exited, a response that arrived, a file that grew, a keypress that
was delivered. There is no `Evidence` variant meaning "trust me".

What this deliberately does *not* do is verify the evidence. `KeypressSent` says
a keypress was sent, not that WhatsApp delivered a message; nothing on this
machine can read WhatsApp back, and a contract that claimed otherwise would be
the same lie one layer up. The contract's job is to make the honest statement
the easy one to write and the dishonest one impossible to express.

Usage::

    from core.contracts import AgentResult, HttpResponse

    return AgentResult.ok(
        "✓ Fetched the forecast.",
        evidence=HttpResponse(status=200, url=url),
        data={"temperature": 21.4},
    ).as_dict()

    return AgentResult.failed(
        "Could not reach the forecast service.",
        error="WEATHER_UNREACHABLE",
    ).as_dict()

`as_dict()` produces exactly the `{"success", "message", "error", ...data}` shape
the API, the UI and the existing tests already consume, so a migrated handler is
a drop-in replacement for the one it replaces.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ── Evidence ─────────────────────────────────────────────────────────────────
# Each variant records something observable. Add a variant when a genuinely new
# kind of proof appears — never a general-purpose one, which would reopen the
# hole this module exists to close.


class _EvidenceBase(BaseModel):
    """Common base. `kind` discriminates the union when serialised."""

    model_config = {"frozen": True}

    def describe(self) -> str:  # pragma: no cover - overridden by every variant
        raise NotImplementedError


class ProcessExit(_EvidenceBase):
    """A subprocess ran and returned a status."""

    kind: Literal["process_exit"] = "process_exit"
    command: str
    returncode: int
    stdout_excerpt: str = ""

    def describe(self) -> str:
        return f"`{self.command}` exited {self.returncode}"


class HttpResponse(_EvidenceBase):
    """A remote endpoint answered."""

    kind: Literal["http_response"] = "http_response"
    status: int
    url: str

    def describe(self) -> str:
        return f"HTTP {self.status} from {self.url}"


class FileRead(_EvidenceBase):
    """A file existed and was read."""

    kind: Literal["file_read"] = "file_read"
    path: str
    bytes_read: int

    def describe(self) -> str:
        return f"read {self.bytes_read} bytes from {self.path}"


class FileWritten(_EvidenceBase):
    """A file was written to disk."""

    kind: Literal["file_written"] = "file_written"
    path: str
    bytes_written: int

    def describe(self) -> str:
        return f"wrote {self.bytes_written} bytes to {self.path}"


class SystemQuery(_EvidenceBase):
    """The local system was interrogated and answered — psutil, os, WMI."""

    kind: Literal["system_query"] = "system_query"
    source: str
    detail: str = ""

    def describe(self) -> str:
        return f"queried {self.source}" + (f" ({self.detail})" if self.detail else "")


class SmtpAccepted(_EvidenceBase):
    """An SMTP server accepted a message for delivery.

    Accepted, not delivered — the distinction is the server's, and overstating it
    is exactly the failure this module is about.
    """

    kind: Literal["smtp_accepted"] = "smtp_accepted"
    server: str
    recipients: str

    def describe(self) -> str:
        return f"{self.server} accepted a message for {self.recipients}"


class KeypressSent(_EvidenceBase):
    """A synthetic keypress was delivered to the focused window.

    Says nothing about what the receiving application did with it. WhatsApp
    sending is built on this and must keep reporting at exactly this strength.
    """

    kind: Literal["keypress_sent"] = "keypress_sent"
    key: str
    target_hint: str = ""

    def describe(self) -> str:
        return f"sent {self.key}" + (f" to {self.target_hint}" if self.target_hint else "")


class TaskQueued(_EvidenceBase):
    """Work was handed to a background worker that really was started.

    The narrowest variant here, and the one most easily misused. It witnesses
    *dispatch* and nothing else: a thread exists. It says nothing about whether
    the work succeeded, and a message paired with it must not claim it did.
    `VoiceAgent.speak` is the motivating case — it returns before synthesis
    finishes by design, so "queued for synthesis" is the strongest true statement
    available, where the old code said `audio_synthesized: True`.

    If you can wait for the outcome, wait for it and use the evidence that
    describes what actually happened instead.
    """

    kind: Literal["task_queued"] = "task_queued"
    worker: str
    detail: str = ""

    def describe(self) -> str:
        return f"queued on {self.worker}" + (f" ({self.detail})" if self.detail else "")


class RecordStored(_EvidenceBase):
    """A row was committed to the local database."""

    kind: Literal["record_stored"] = "record_stored"
    store: str
    key: str

    def describe(self) -> str:
        return f"stored '{self.key}' in {self.store}"


class ModelAnswered(_EvidenceBase):
    """A named language model produced this text, and nothing further is claimed.

    The narrowest variant after `TaskQueued`, and the one that needs the most
    care, because a fluent answer *reads* like a verified one.

    It witnesses exactly this: a model was asked, and it replied. It does not
    witness that the reply is true, that anything was looked up, or that any
    action was taken. A message paired with this evidence must not describe work
    the assistant did — if the assistant did work, use the evidence that
    describes the work.

    It exists because the alternative was worse. `CognitiveResponseDict.__bool__`
    once returned `True` unconditionally, so *every* failed dispatch was
    overwritten with a fabricated "🤖 Cognitive Response" success — including
    when no key was configured and nothing had been asked of any model. This
    variant makes the honest version expressible: the model answered, that is
    all, and callers can tell a generated answer from an observed one by looking
    at the evidence rather than at the prose.
    """

    kind: Literal["model_answered"] = "model_answered"
    model: str
    #: Where the model ran. "local" for Ollama on this machine; anything else
    #: means the text left the box, which a user is entitled to know.
    host: str = "local"

    def describe(self) -> str:
        return f"{self.model} ({self.host}) generated this text"


Evidence = Annotated[
    Union[
        ProcessExit,
        HttpResponse,
        FileRead,
        FileWritten,
        SystemQuery,
        SmtpAccepted,
        KeypressSent,
        TaskQueued,
        RecordStored,
        ModelAnswered,
    ],
    Field(discriminator="kind"),
]


# ── The result ───────────────────────────────────────────────────────────────


class AgentResult(BaseModel):
    """What every handler returns.

    The field is `success`, not `ok`, so `as_dict()` matches the shape the API,
    the UI and 300-odd existing tests already read. The contract is the
    validator, not the vocabulary.
    """

    success: bool
    message: str
    evidence: Optional[Evidence] = None
    error: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _claims_must_be_witnessed(self) -> "AgentResult":
        if self.success and self.evidence is None:
            raise ValueError(
                "AgentResult(success=True) requires evidence. If nothing "
                "observable happened, this is not a success — report the real "
                "outcome with AgentResult.failed() or AgentResult.unsupported()."
            )
        if not self.success and not self.error:
            raise ValueError(
                "AgentResult(success=False) requires an `error` code so callers "
                "can branch on the reason rather than parse the message."
            )
        return self

    # ── Constructors ─────────────────────────────────────────────────────────
    @classmethod
    def ok(
        cls,
        message: str,
        *,
        evidence: Evidence,
        data: Optional[Dict[str, Any]] = None,
    ) -> "AgentResult":
        """A success. `evidence` is keyword-only and required — that is the point."""
        return cls(success=True, message=message, evidence=evidence, data=data or {})

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        error: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> "AgentResult":
        """Something was attempted and did not work."""
        return cls(success=False, message=message, error=error, data=data or {})

    @classmethod
    def unsupported(cls, what: str, *, detail: str = "") -> "AgentResult":
        """We cannot do this at all — distinct from having tried and failed.

        The honest answer for a capability that is declared somewhere but has no
        implementation behind it.
        """
        message = f"I can't do that yet: {what}."
        if detail:
            message += f" {detail}"
        return cls(success=False, message=message, error="NOT_IMPLEMENTED")

    @classmethod
    def not_configured(cls, what: str, *, needs: str) -> "AgentResult":
        """The capability is real but this machine is missing its credentials."""
        return cls(
            success=False,
            message=f"{what} is not set up on this machine. It needs {needs}.",
            error="NOT_CONFIGURED",
        )

    # ── Serialisation ────────────────────────────────────────────────────────
    def as_dict(self) -> Dict[str, Any]:
        """The wire shape: `success`, `message`, optional `error`, plus `data`
        flattened to top level so existing callers keep working unchanged.

        `evidence` is included so the audit log and the API can show *why* a
        success was allowed to call itself one.
        """
        out: Dict[str, Any] = {"success": self.success, "message": self.message}
        if self.error:
            out["error"] = self.error
        if self.evidence is not None:
            out["evidence"] = self.evidence.model_dump()
            out["evidence_summary"] = self.evidence.describe()
        out.update(self.data)
        return out
