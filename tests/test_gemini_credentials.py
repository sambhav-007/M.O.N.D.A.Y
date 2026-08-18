"""
The two Gemini paths that are left, and what they do with a key.

The third one — a hosted call in `MasterPlanner.process_command` that ran after
any failed or low-confidence dispatch — was removed on 2026-08-18, and stage 3
in `core/llm.py` is now the only language model in the routing path. What
remains is code synthesis in `agents/coder_agent.py` and document Q&A in
`agents/document_agent.py`, both of which reach Google through
`load_gemini_api_key` and the endpoint below.

Both defects covered here were found while removing the third path, and both
were invisible for the same reason everything else in this corner was: no key
is configured on the development machine, so none of this code had run. "It
never runs here" is a claim about the machine, not about the code — which is
the lesson `pyttsx3` taught when installing it woke a dormant path that started
Outlook to answer a contact lookup.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List

import pytest

from agents.vision_agent import GEMINI_ENDPOINT, load_gemini_api_key
from core.cognitive import TriModelCognitiveEngine

#: Deliberately not shaped like a Google key. `.githooks/pre-commit` blocks
#: added lines matching the real vendor prefixes, and a test fixture is not a
#: good enough reason to teach a secret scanner to hesitate.
FAKE_KEY = "not-a-real-google-key-0123456789"
FAKE_OPENAI_KEY = "not-a-real-openai-key-0123456789"


@pytest.fixture
def captured_requests(monkeypatch) -> List[urllib.request.Request]:
    """Intercepts the HTTP call and returns the `Request` objects it was given.

    Nothing is sent. The suite runs with `--block-network`, so a test that
    reached Google would fail on the socket rather than on the assertion — and
    the assertion is the interesting part.
    """
    seen: List[urllib.request.Request] = []

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

        def read(self) -> bytes:
            body = {"candidates": [{"content": {"parts": [{"text": "an answer"}]}}]}
            return json.dumps(body).encode("utf-8")

    def _urlopen(req: urllib.request.Request, timeout: float = 0) -> _Response:
        seen.append(req)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return seen


def _use_key(monkeypatch, key: str = FAKE_KEY) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", key)


# ── A credential for one provider is not a credential for another ────────────
def test_an_openai_key_is_never_offered_to_google(monkeypatch):
    """`OPENAI_API_KEY` was third in the lookup list.

    Everything that calls `load_gemini_api_key` sends the result to
    `generativelanguage.googleapis.com`, so on a machine with an OpenAI key and
    no Gemini key, the OpenAI key was handed to Google. The call site wanting a
    key to exist does not make one exist.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI_KEY)

    assert load_gemini_api_key() != FAKE_OPENAI_KEY


def test_a_google_key_is_still_found(monkeypatch):
    """The narrowing must not have removed the working case."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", FAKE_KEY)
    assert load_gemini_api_key() == FAKE_KEY


# ── The key travels in a header, not in the URL ──────────────────────────────
def test_the_key_is_not_in_the_url(monkeypatch, captured_requests):
    """A URL is the part of a request that gets logged.

    Proxy history, server access logs, a traceback pasted into a bug report — a
    query-string credential ends up in all three, and `?key=` was how both call
    sites authenticated.
    """
    _use_key(monkeypatch)
    TriModelCognitiveEngine().generate_cognitive_response("summarise this")

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert FAKE_KEY not in request.full_url
    assert request.full_url == GEMINI_ENDPOINT
    assert request.get_header("X-goog-api-key") == FAKE_KEY


def test_the_screen_reader_authenticates_the_same_way(monkeypatch, captured_requests):
    """Two call sites, one decision. The endpoint is defined once and imported."""
    from agents.vision_agent import VisionAgent

    _use_key(monkeypatch)
    agent = VisionAgent()
    agent.api_key = FAKE_KEY
    agent._query_multimodal_api("what is on screen", base64_img="ZmFrZQ==")

    assert len(captured_requests) == 1
    assert FAKE_KEY not in captured_requests[0].full_url
    assert captured_requests[0].get_header("X-goog-api-key") == FAKE_KEY


# ── An answer still has to have come from somewhere ──────────────────────────
def test_an_answered_call_reports_success(monkeypatch, captured_requests):
    _use_key(monkeypatch)
    result = TriModelCognitiveEngine().generate_cognitive_response("summarise this")

    assert result["llm_backed"] is True
    assert bool(result) is True
    assert result["response"] == "an answer"


def test_no_key_is_falsy_and_says_so(monkeypatch):
    """`CognitiveResponseDict.__bool__` returned `True` unconditionally once, so
    `if llm_response:` overwrote every genuine result with a placeholder."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result: Dict[str, Any] = TriModelCognitiveEngine().generate_cognitive_response("hi")
    if result["llm_backed"]:
        pytest.skip("a Gemini key is configured on this machine")

    assert bool(result) is False
    assert result["success"] is False
    assert "GEMINI_API_KEY" in result["response"]
