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
