"""
Shared pytest configuration — network policy.

Several tests used to call live third-party services (DuckDuckGo, open-notify,
CoinGecko, Open-Meteo, Wikipedia, IP-API). That made a red suite ambiguous: the
run on 2026-08-08 failed `test_agent_public_api_fetch_iss_location` because
`api.open-notify.org` was unreachable, not because anything had regressed. It
also made the suite slow and variable — 117s to 301s across runs, and one run
never finished at all.

The policy now:

* HTTP-dependent tests carry ``@pytest.mark.vcr`` and replay a **cassette** — a
  recorded request/response pair committed under ``tests/cassettes/``. They run
  offline, deterministically, in milliseconds.
* Tests that genuinely need to reach the internet carry ``@pytest.mark.network``
  and are **deselected by default** (see ``pytest.ini``). Run them deliberately:

      py -3.12 -m pytest -m network

* Anything else attempting a socket connection fails loudly rather than quietly
  depending on the network. ``--block-network`` is on by default.

**``--block-network`` has one blind spot worth knowing about.** It patches
sockets inside *this* interpreter, so a child process is invisible to it.
``CoderAgent.generate_and_execute_script`` runs generated code via
``subprocess.run``, and such a script can and does reach the internet while the
blocker reports nothing — see ``test_planner_process_command_search``. A test
that reaches the network through a subprocess must be marked ``network`` by
hand; the blocker cannot find it for you.

Re-recording a cassette after an API changes shape:

    py -3.12 -m pytest tests/test_100_ruthless.py -k crypto \\
        --record-mode=rewrite --disable-blockage

Review the diff before committing it — a cassette is test input, and a recording
made against a rate-limited or error response will happily pin that behaviour in.
"""

from __future__ import annotations

import json
import re
import subprocess

import pytest

# ── Scrubbing ────────────────────────────────────────────────────────────────
# A cassette is a committed file, so whatever a response contained is published.
# `ip-api.com` answers with the caller's real public IP, city, postcode and ISP;
# the first recording made here carried a home address and an IP into a file
# destined for git. Responses are rewritten before they are ever written out.

_SYNTHETIC_GEOLOCATION = {
    "status": "success",
    "country": "India",
    "countryCode": "IN",
    "region": "DL",
    "regionName": "Delhi",
    "city": "New Delhi",
    "zip": "110001",
    "lat": 28.6139,
    "lon": 77.2090,
    "timezone": "Asia/Kolkata",
    "isp": "Example ISP",
    "org": "Example Org",
    "as": "AS0000 Example",
    "query": "203.0.113.1",  # RFC 5737 documentation range — never routable
}

# Any dotted quad that is not obviously private. Deliberately over-eager: a
# false positive redacts a number in a payload, a false negative publishes an
# address.
_PUBLIC_IPV4 = re.compile(
    r"\b(?!(?:10|127|0)\.)(?!192\.168\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
    r"(?:\d{1,3}\.){3}\d{1,3}\b"
)


def _scrub_request(request):
    """Normalises coordinates out of outgoing request URIs.

    `PublicApiAgent.get_weather` geolocates by IP and then puts the resulting
    latitude and longitude straight into the Open-Meteo query string, so the
    recorded *request* carried the user's real coordinates just as the
    geolocation response carried their city. Pinning them to the synthetic
    location removes that, and has a second effect that matters just as much:
    the replayed geolocation now yields the same coordinates the cassette was
    recorded with, so the two-call chain still matches. Without this the weather
    tests looked for a URI no cassette contained.

    VCR applies this to requests during playback matching as well as during
    recording, so both sides are normalised by the same rule.
    """
    uri = getattr(request, "uri", "") or ""
    if "open-meteo.com" in uri:
        uri = re.sub(r"latitude=[-\d.]+", f"latitude={_SYNTHETIC_GEOLOCATION['lat']}", uri)
        uri = re.sub(r"longitude=[-\d.]+", f"longitude={_SYNTHETIC_GEOLOCATION['lon']}", uri)
        request.uri = uri
    return request


def _scrub_response(response):
    """Replaces anything in a response that identifies this machine.

    `filter_headers` in vcr_config only reaches *request* headers, so response
    headers are handled here — otherwise Wikipedia's `set-cookie` lands in a
    committed file.
    """
    headers = response.get("headers") or {}
    for name in list(headers):
        if name.lower() in {"set-cookie", "cookie", "authorization"}:
            headers[name] = ["REDACTED"]

    body = response.get("body", {})
    raw = body.get("string")
    if raw is None:
        return response

    text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw

    # Geolocation is identifying end to end, so the payload is replaced wholesale
    # rather than field-patched — a new field appearing upstream must not leak.
    if '"query"' in text and '"isp"' in text:
        text = json.dumps(_SYNTHETIC_GEOLOCATION)
    else:
        # Open-Meteo echoes back the coordinates it resolved, to ~4 decimal
        # places, plus the ground elevation. Normalising the request URI was not
        # enough: the response body located the user all over again.
        if '"generationtime_ms"' in text:
            text = re.sub(r'"latitude":\s*[-\d.]+', f'"latitude":{_SYNTHETIC_GEOLOCATION["lat"]}', text)
            text = re.sub(r'"longitude":\s*[-\d.]+', f'"longitude":{_SYNTHETIC_GEOLOCATION["lon"]}', text)
            text = re.sub(r'"elevation":\s*[-\d.]+', '"elevation":0.0', text)
        text = _PUBLIC_IPV4.sub("203.0.113.1", text)

    body["string"] = text.encode("utf-8") if isinstance(raw, bytes) else text
    return response


@pytest.fixture(autouse=True)
def no_browser_tabs(monkeypatch):
    """Stops the suite opening browser tabs on the machine running it.

    **Reported by the user, 2026-08-17: "I could only see mail tabs opening."**
    They were right, and it had been happening on every run.

    `CommunicationAgent.draft_email` calls `webbrowser.open(gmail_url)` for every
    draft it writes — "also launch browser tab for visual inspection". A dozen
    tests compose email (`test_email_and_whatsapp_ux.py` alone drafts seven
    times, and `DEMO.md`'s Act 5 drafts once more), so a full run opened a stack
    of Gmail compose tabs. `open_whatsapp_chat` and `open_app_or_website` are
    the same shape.

    This is the `fake_powershell` problem again: that fixture exists because the
    volume tests drove the real speakers and left the machine muted. A test
    should not reach outside the process to prove a function assembled the right
    URL. The recorder is returned so a test that genuinely cares can assert
    *what* would have been opened, which is more precise than watching tabs
    appear.

    Not a fix to the product behaviour, which is a separate question: opening a
    Gmail tab the instant a draft is written — before the user has confirmed
    anything — is arguably too eager, given the UI already offers an explicit
    "Open Pre-Filled Gmail Web Composer" button. That is a design decision and
    belongs in its own change.

    **Three ways out, not one.** `webbrowser.open` was the reported symptom, but
    on Windows a deep link goes through `os.startfile` and an application goes
    through `subprocess.Popen` — so intercepting only the browser would have
    left WhatsApp and `launch_application` still opening real windows. Writing
    the fixture against the symptom is how this bug survives its own fix.
    """
    import os
    import subprocess
    import webbrowser

    opened: list = []

    def _record(url: str, *args: object, **kwargs: object) -> bool:
        opened.append(str(url))
        return True

    monkeypatch.setattr(webbrowser, "open", _record)
    monkeypatch.setattr(webbrowser, "open_new", _record, raising=False)
    monkeypatch.setattr(webbrowser, "open_new_tab", _record, raising=False)
    # Windows' "open this with whatever handles it" — whatsapp:// links, apps,
    # documents. Absent on other platforms, hence `raising=False`.
    monkeypatch.setattr(os, "startfile", _record, raising=False)

    # The desktop notification pops a PowerShell MessageBox via `Popen`, which
    # would sit on screen waiting to be dismissed. Intercepted *narrowly*:
    #
    # `subprocess.run` is implemented on top of `Popen`, so a blanket stub
    # breaks every legitimate subprocess in the suite — `test_voice_ui.py` runs
    # the shipped `Voice` object under node, and nine of its tests failed the
    # moment this patched Popen unconditionally. Match the one command that
    # opens a window and delegate everything else to the real thing.
    real_popen = subprocess.Popen

    def _popen(args: object, *a: object, **kw: object) -> object:
        flat = " ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args)
        if "MessageBox" in flat:
            opened.append(flat)

            class _Stub:
                pid = -1
                returncode = 0

                def wait(self, timeout: object = None) -> int:
                    return 0

                def poll(self) -> int:
                    return 0

            return _Stub()
        return real_popen(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", _popen)
    return opened


@pytest.fixture(autouse=True)
def _stage_three_is_off_unless_asked_for(request, monkeypatch):
    """Switches the language model out of the router for the whole suite.

    `--block-network` deliberately allows `127.0.0.1` — FastAPI's TestClient and
    the in-process API tests need it — and Ollama listens on exactly that
    address. So on a machine where a model happens to be running, stage 3 would
    join the routing cascade during the test run, and a suite that passes on one
    developer's laptop would fail on another's for a reason unrelated to any
    change. Concretely: `xyzzyspoon12345` is in `DEMO.md`'s honest-failure act
    and must fail; a language model will answer it cheerfully.

    That would undo the property Phase 1 was fought for — *a red suite means a
    regression*. So the default run is deterministic, and the tests that want a
    live model ask for it with `@pytest.mark.llm` (deselected by default, like
    `network`).

    Setting the environment variable rather than patching the router covers
    every construction path, including planners built inside a test.
    `LlmStage.available()` reads it before consulting its own cache, so this
    works even on a stage that already probed.
    """
    if request.node.get_closest_marker("llm") is None:
        monkeypatch.setenv("MONDAY_LLM", "off")
    else:
        monkeypatch.delenv("MONDAY_LLM", raising=False)
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolate_memory_db(tmp_path_factory):
    """Points the memory store at a throwaway database for the whole session.

    `MasterPlanner.process_command` calls `auto_store_conversation_turn` on every
    command, so each test that issues one wrote a permanent row into
    `data/memory.db` — the user's real assistant memory. handoff.md warns about
    this ("Tests must not write to data/memories.db… manual testing left fake
    relatives in it more than once"), but the warning only ever covered the
    contact-saving tests, which stub `remember`/`recall`. Every other test wrote
    freely.

    Two consequences, and the second is why it showed up:

    1. The user's memory filled with test transcripts — 2,196 rows by
       2026-08-10, of which 2,196 were machine-written conversation turns.
    2. `recall` builds a TF-IDF matrix over *every* stored row, and
       `get_contextual_memories` runs on every command. So the suite got slower
       each time it ran, permanently: ~70s, then ~92s, then 222s across one
       afternoon. It was not a regression in any of the code being changed.

    Redirecting the module-level name is what works here — `memory_agent` does
    `from core.config import MEMORIES_DB_PATH`, so patching `core.config` alone
    would rebind nothing.
    """
    import agents.memory_agent as memory_agent

    scratch = tmp_path_factory.mktemp("memory") / "test_memory.db"
    patcher = pytest.MonkeyPatch()
    patcher.setattr(memory_agent, "MEMORIES_DB_PATH", scratch, raising=True)
    yield scratch
    patcher.undo()


@pytest.fixture(scope="session", autouse=True)
def _isolate_audit_log(tmp_path_factory):
    """Points the audit log at a throwaway file for the session.

    `core.security.log_action` reads the entire JSON array, appends one entry and
    writes the whole thing back, under a lock, on **every action**. That is
    O(file) per call, so the cost grows with the log — and the log only ever
    grows.

    Measured on 2026-08-10: `data/action_history.json` had reached **19,837
    entries / 6.5 MB**, and the suite took **209s**. The same suite against the
    committed 87 KB log took **38.7s**. Nothing in the code under test had
    regressed; the audit log had simply grown, and every run made it worse.

    Isolating it here keeps the suite fast and stops tests writing to the user's
    real audit trail — which is CLO01 evidence, and should contain their actions,
    not the test suite's.

    **This is a real defect in the app, not only in the tests.** A user's own log
    grows the same way, and every command they issue slows down with it. The fix
    is an append-only format (JSON Lines) rather than read-modify-write, which
    also resolves the multi-process last-writer-wins loss that `core/security.py`
    already documents. That is a change to a CLO01 evidence artefact, so it wants
    its own commit rather than being folded into the router work.
    """
    import core.security as security

    scratch_dir = tmp_path_factory.mktemp("audit")
    patcher = pytest.MonkeyPatch()
    patcher.setattr(security, "ACTION_LOG_PATH", scratch_dir / "action_history.jsonl")
    # The legacy reader too, or `get_action_history` would fall back to the real
    # 6.5 MB array whenever a test logged fewer records than it asked for.
    patcher.setattr(security, "LEGACY_ACTION_LOG_PATH", scratch_dir / "action_history.json")
    yield scratch_dir
    patcher.undo()


@pytest.fixture
def fake_powershell(monkeypatch):
    """Intercepts `ComputerAgent`'s PowerShell calls instead of running them.

    `set_system_volume` drives the real speakers: 50 volume-down keypresses to
    reach zero, then back up to the requested level. Running the suite therefore
    left the machine muted or at whatever the last test asked for. That was
    always true, but it used to be fired with `subprocess.Popen` and never waited
    for, so it was unreliable as well as unwanted; making the call synchronous so
    it could be witnessed also made the side effect dependable.

    A test should not reach outside the process to prove a function assembled the
    right command. This records the command and reports a clean exit.
    """

    class _Recorder:
        last_command: str = ""

    recorder = _Recorder()
    real_run = subprocess.run

    def _fake_run(args, *a, **kw):
        if isinstance(args, (list, tuple)) and args and "powershell" in str(args[0]).lower():
            recorder.last_command = " ".join(str(x) for x in args)
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return recorder


@pytest.fixture(scope="module")
def vcr_config():
    """VCR settings applied to every ``@pytest.mark.vcr`` test.

    ``record_mode`` stays "none" so a cassette miss is an error rather than a
    silent live call — the whole point is that a passing suite proves nothing
    reached the network. Pass ``--record-mode`` on the command line to record.
    """
    return {
        # Never persist anything that identifies this machine or its user. The
        # public APIs here need no credentials, but a cassette is a committed
        # file and this stops one from becoming a leak later.
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("cookie", "REDACTED"),
            ("set-cookie", "REDACTED"),
            ("x-api-key", "REDACTED"),
            ("user-agent", "REDACTED"),
        ],
        "filter_query_parameters": [("key", "REDACTED"), ("token", "REDACTED")],
        "before_record_request": _scrub_request,
        "before_record_response": _scrub_response,
        # Match on method + full URI. Body matching would make the crypto and
        # weather GETs unnecessarily brittle, and none of them POST.
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
        "decode_compressed_response": True,
        # record_mode is deliberately not set here: pytest-recording already
        # defaults to "none", so a cassette miss is an error rather than a silent
        # live call, and leaving it out keeps --record-mode on the command line
        # authoritative when a cassette genuinely needs re-recording.
    }


@pytest.fixture(scope="module")
def vcr_cassette_dir(request):
    """One cassette directory per test module, so they stay easy to locate."""
    import os

    return os.path.join(os.path.dirname(__file__), "cassettes", request.module.__name__.split(".")[-1])
