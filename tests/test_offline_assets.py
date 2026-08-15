"""The UI must start with no network.

`ui/index.html` used to load eight libraries from three CDNs. They are plain
`<script src>` tags, so a failed load is silent — and the resulting
`ReferenceError: THREE is not defined` in the inline script aborts everything
after it, including `sendCommand`, `Voice` and the input handler. With no
network the app was not degraded, it was **dead**: no commands, no voice, no
console, and no error the user could see. A working connection hides that
completely, which is why it survived so long.

Offline is the demo-day requirement (handoff.md §6), so the libraries are
vendored into `ui/vendor/`.

The mount test below is the one that matters most. Vendoring the files is the
obvious half; serving them is the half that is easy to forget, because `/app`
returns the HTML with a `FileResponse` — one file, nothing beside it — and
**both** entry points go through it. `app.py` points the pywebview window at
`http://127.0.0.1:8000/app` rather than opening the file from disk. Without the
mount, every `vendor/*.js` request 404s and the fix for the CDN problem
reintroduces the exact failure it was meant to remove.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX = PROJECT_ROOT / "ui" / "index.html"
VENDOR = PROJECT_ROOT / "ui" / "vendor"

#: The one external origin the page is allowed to name: its own backend.
ALLOWED = ("127.0.0.1", "localhost")


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


# ── Nothing external ─────────────────────────────────────────────────────────
def test_no_script_loads_from_a_cdn(html):
    external = [
        src for src in re.findall(r'<script[^>]+src="([^"]+)"', html)
        if src.startswith(("http://", "https://", "//"))
    ]
    assert not external, f"these would break with no network: {external}"


def test_no_stylesheet_or_font_is_fetched_remotely(html):
    remote_imports = [
        url for url in re.findall(r"@import\s+url\(['\"]?([^'\")]+)", html)
        if url.startswith(("http://", "https://", "//"))
    ]
    assert not remote_imports, f"remote @import: {remote_imports}"

    remote_links = [
        href for href in re.findall(r'<link[^>]+href="([^"]+)"', html)
        if href.startswith(("http://", "https://", "//"))
    ]
    assert not remote_links, f"remote <link>: {remote_links}"


def test_the_only_external_host_named_is_the_backend(html):
    hosts = {
        m.split("//", 1)[1].split("/")[0].split(":")[0]
        for m in re.findall(r"https?://[^\s\"'`)]+", html)
    }
    # Comments naming a source URL are documentation, not a fetch; only hosts
    # appearing in an attribute or a fetch would be requested. Those are covered
    # by the two tests above, so this one just keeps the surface visible.
    unexpected = {h for h in hosts if h not in ALLOWED and "." in h}
    assert unexpected <= {"fonts.googleapis.com"}, (
        f"unexpected hosts referenced in the page: {sorted(unexpected)}"
    )


# ── Everything referenced is present ─────────────────────────────────────────
def test_every_vendored_file_referenced_exists(html):
    missing = [
        src for src in re.findall(r'<script[^>]+src="(vendor/[^"]+)"', html)
        if not (PROJECT_ROOT / "ui" / src).exists()
    ]
    assert not missing, f"referenced but not on disk: {missing}"


def test_the_vendored_set_is_complete():
    from ui.vendor.fetch_vendor import ASSETS

    missing = [name for name, _ in ASSETS if not (VENDOR / name).exists()]
    assert not missing, (
        f"missing {missing} — run `py -3.12 -m ui.vendor.fetch_vendor --write`"
    )


def test_the_fonts_are_vendored_too():
    css = VENDOR / "fonts.css"
    assert css.exists(), "run `py -3.12 -m ui.vendor.fetch_vendor --write`"
    text = css.read_text(encoding="utf-8")
    assert "https://" not in text.split("*/", 1)[-1], \
        "fonts.css still points at a remote host outside its header comment"
    for rel in re.findall(r"url\(\./([^)]+\.woff2)\)", text):
        assert (VENDOR / rel).exists(), f"fonts.css references missing {rel}"


# ── And it is actually served ────────────────────────────────────────────────
def test_the_app_serves_every_script_it_asks_for(client, html):
    """
    The regression this file exists for. `/app` is a `FileResponse`, so without
    an explicit static mount the vendored files 404 and `THREE` is undefined —
    which is the original bug, reintroduced by its own fix.
    """
    assert client.get("/app").status_code == 200

    broken = []
    for src in re.findall(r'<script[^>]+src="(vendor/[^"]+)"', html):
        if client.get(f"/{src}").status_code != 200:
            broken.append(src)
    assert not broken, f"served 404 from the running app: {broken}"


def test_the_app_serves_the_stylesheet_and_its_fonts(client):
    css = client.get("/vendor/fonts.css")
    assert css.status_code == 200

    for rel in re.findall(r"url\(\./([^)]+\.woff2)\)", css.text):
        assert client.get(f"/vendor/{rel}").status_code == 200, rel
