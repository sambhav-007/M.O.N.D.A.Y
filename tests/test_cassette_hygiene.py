"""
Cassettes are committed files, so whatever they contain is published.

The first recording made for this suite carried the user's real public IP, home
city, postcode and ISP straight out of `ip-api.com`, and their resolved
coordinates and ground elevation out of Open-Meteo's echo of the request. The
scrubbers in `conftest.py` handle all of that — but a scrubber only protects the
recordings made after it was written, and re-recording is a routine chore that
happens when an API changes shape.

These tests check the committed files themselves, so a cassette recorded with a
scrubber that missed something fails here rather than in a pull request.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"

# RFC 5737 documentation address; the scrubber rewrites everything to this.
ALLOWED_IPV4 = {"203.0.113.1", "0.0.0.0", "127.0.0.1", "255.255.255.255"}

_PUBLIC_IPV4 = re.compile(
    r"\b(?!(?:10|127|0)\.)(?!192\.168\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
    r"(?:\d{1,3}\.){3}\d{1,3}\b"
)

# The synthetic location the scrubber pins everything to.
SYNTHETIC_LAT, SYNTHETIC_LON = 28.6139, 77.209


def _cassettes() -> list[Path]:
    return sorted(CASSETTE_DIR.rglob("*.yaml"))


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


pytestmark = pytest.mark.skipif(
    not _cassettes(), reason="no cassettes recorded yet"
)


@pytest.mark.parametrize("cassette", _cassettes(), ids=_ids(_cassettes()))
def test_no_public_ip_addresses(cassette: Path):
    """A recorded response must not carry a routable address."""
    text = cassette.read_text(encoding="utf-8", errors="ignore")
    found = {
        ip for ip in _PUBLIC_IPV4.findall(text)
        if ip not in ALLOWED_IPV4
        # Version strings and content-length values are not addresses.
        and len([p for p in ip.split(".") if p.isdigit() and int(p) <= 255]) == 4
    }
    assert not found, f"{cassette.name} publishes {sorted(found)}"


@pytest.mark.parametrize("cassette", _cassettes(), ids=_ids(_cassettes()))
def test_no_cookies_or_credentials(cassette: Path):
    """Session cookies and auth headers are redacted, never recorded."""
    lines = cassette.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i, line in enumerate(lines):
        header = line.strip().rstrip(":").lower()
        if header in {"set-cookie", "cookie", "authorization", "x-api-key"}:
            following = " ".join(lines[i + 1 : i + 3])
            assert "REDACTED" in following, (
                f"{cassette.name}:{i + 1} records a real {header} value"
            )


@pytest.mark.parametrize("cassette", _cassettes(), ids=_ids(_cassettes()))
def test_geolocation_is_synthetic(cassette: Path):
    """
    Any geolocation payload must be the placeholder one. The real response names
    the city and postcode the machine is sitting in.
    """
    text = cassette.read_text(encoding="utf-8", errors="ignore")
    if '"isp"' not in text or '"query"' not in text:
        return
    assert '"Example ISP"' in text, (
        f"{cassette.name} contains a geolocation payload that is not the "
        f"synthetic one — re-record it with the scrubber in conftest.py"
    )


@pytest.mark.parametrize("cassette", _cassettes(), ids=_ids(_cassettes()))
def test_coordinates_are_synthetic(cassette: Path):
    """
    Open-Meteo echoes the coordinates it resolved, to four decimal places, in
    both the request URI and the response body. Scrubbing one and not the other
    still discloses where the machine is.
    """
    text = cassette.read_text(encoding="utf-8", errors="ignore")
    if "open-meteo" not in text:
        return
    for field, expected in (("latitude", SYNTHETIC_LAT), ("longitude", SYNTHETIC_LON)):
        # The field appears two ways: bare in the request URI (`latitude=28.6`)
        # and JSON-in-YAML in the response body (`latitude\":28.6`). A character
        # class absorbs whichever quoting is in play without escape guesswork —
        # an earlier version of this pattern silently matched nothing at all,
        # which is the one failure mode a leak check must not have.
        values = re.findall(rf'{field}[\\"]*[=:][\\"\s]*(-?\d+\.?\d*)', text)
        assert values, f"{cassette.name}: no {field} found — check this pattern"
        for value in values:
            assert abs(float(value) - expected) < 0.01, (
                f"{cassette.name} records a real {field} of {value}"
            )


def test_cassettes_are_valid_yaml_with_interactions():
    """A cassette recorded from a failure is empty and silently proves nothing."""
    yaml = pytest.importorskip("yaml")
    for cassette in _cassettes():
        data = yaml.safe_load(cassette.read_text(encoding="utf-8"))
        assert data and data.get("interactions"), (
            f"{cassette.name} has no interactions — it was probably recorded "
            f"while the service was down, and now pins that outage as expected"
        )
        for interaction in data["interactions"]:
            status = interaction["response"]["status"]["code"]
            assert 200 <= status < 400, (
                f"{cassette.name} pins HTTP {status}; re-record it against a "
                f"healthy response or mark the test `network` instead"
            )
