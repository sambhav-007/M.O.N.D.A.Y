"""Re-download the front-end libraries `ui/index.html` loads.

    py -3.12 -m ui.vendor.fetch_vendor          # verify what is committed
    py -3.12 -m ui.vendor.fetch_vendor --write  # re-download

Everything it fetches is committed, so this never needs to run — it exists so
the files are auditable and reproducible rather than a pile of unattributed
minified blobs.

Why they are vendored
---------------------
`ui/index.html` used to load all eight from CDNs. Because they are plain
`<script src>` tags, a failed load is silent — and a `ReferenceError: THREE is
not defined` in the inline script that follows aborts *everything after it*.
That script defines `sendCommand`, `Voice` and the command input handler, so
with no network the app was not degraded, it was dead: no commands, no voice,
no console, and no error the user could see.

A working connection hides this completely. It was found by loading the page in
a sandboxed browser that blocks external hosts, while testing something else.

Offline is the demo-day requirement (handoff.md §6), so the files live here.

Licences
--------
* three.js and its `examples/js` add-ons — MIT, © three.js authors.
* Tailwind CSS (Play CDN build) — MIT, © Tailwind Labs.

Both are permissive and require the copyright notice be preserved; the notices
are inside the minified files themselves and are not stripped here.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parent

#: Pinned by version on purpose. `three@0.128.0` and the r128 build are the same
#: release; the `examples/js` add-ons attach themselves to the `THREE` global and
#: only work against a matching core, so these versions move together or not at
#: all.
THREE = "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js"
ASSETS = [
    # (local name, url)
    # The Play CDN build — a JIT compiler that scans the DOM and injects styles
    # at runtime. That is not how Tailwind should ship to production, but it is
    # what this page was written against, and swapping it for a compiled
    # stylesheet would mean rebuilding every utility class the markup uses.
    ("tailwind.min.js", "https://cdn.tailwindcss.com"),
    ("three.min.js", "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"),
    ("EffectComposer.js", f"{THREE}/postprocessing/EffectComposer.js"),
    ("RenderPass.js", f"{THREE}/postprocessing/RenderPass.js"),
    ("CopyShader.js", f"{THREE}/shaders/CopyShader.js"),
    ("LuminosityHighPassShader.js", f"{THREE}/shaders/LuminosityHighPassShader.js"),
    ("ShaderPass.js", f"{THREE}/postprocessing/ShaderPass.js"),
    ("UnrealBloomPass.js", f"{THREE}/postprocessing/UnrealBloomPass.js"),
]


#: Google Fonts, requested as a browser so the CSS comes back referencing woff2
#: rather than the older formats it serves to unknown agents.
FONTS_CSS = (
    "https://fonts.googleapis.com/css2"
    "?family=Plus+Jakarta+Sans:wght@300;400;600;800"
    "&family=JetBrains+Mono:wght@400;700&display=swap"
)
#: The stylesheet declares 28 `@font-face` blocks across six subsets. This UI is
#: English; `latin` covers it and `latin-ext` covers accented names and search
#: results. Cyrillic, Greek and Vietnamese would be ~1 MB of fonts that nothing
#: in the app can produce.
FONT_SUBSETS = ("latin", "latin-ext")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch(url: str) -> bytes:
    import httpx

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url, headers={"User-Agent": BROWSER_UA})
        resp.raise_for_status()
        return resp.content


def fetch_fonts(write: bool) -> int:
    """Downloads the woff2 files and writes a stylesheet pointing at them.

    The `@import` of the Google stylesheet was the one external request left
    after the scripts. It is not fatal when it fails — CSS `@import` fails
    silently and the `sans-serif` / `monospace` fallbacks take over — but it is
    a visible change in an app whose whole presentation is the point, and it
    leaves the offline path depending on a third party for no reason.
    """
    import re

    fonts_dir = VENDOR / "fonts"
    css_path = VENDOR / "fonts.css"

    if not write:
        if not css_path.exists():
            print("  MISSING  fonts.css   <- run with --write")
            return 1
        files = sorted(fonts_dir.glob("*.woff2")) if fonts_dir.exists() else []
        total = sum(f.stat().st_size for f in files)
        print(f"  {total/1024:8.1f} KB  {len(files)} woff2 files + fonts.css")
        return 0 if files else 1

    fonts_dir.mkdir(parents=True, exist_ok=True)
    css = fetch(FONTS_CSS).decode("utf-8")

    # Each block is preceded by a `/* subset */` comment naming it.
    blocks = re.split(r"(?=/\*\s*[\w-]+\s*\*/)", css)
    kept, downloaded = [], 0
    for block in blocks:
        m = re.match(r"/\*\s*([\w-]+)\s*\*/", block.strip())
        if not m or m.group(1) not in FONT_SUBSETS:
            continue
        # Google serves these as `/s/<family>/<version>/<hash>.woff2`, so the
        # bare filename is an opaque hash. Prefixing family, weight and subset
        # makes the directory listing mean something.
        weight = (re.search(r"font-weight:\s*(\d+)", block) or [None, "400"])[1]
        for url in re.findall(r"url\((https://[^)]+\.woff2)\)", block):
            parts = url.split("/")
            family = parts[-3] if len(parts) >= 3 else "font"
            name = f"{family}-{weight}-{m.group(1)}-{parts[-1]}"
            (fonts_dir / name).write_bytes(fetch(url))
            block = block.replace(url, f"./fonts/{name}")
            downloaded += 1
        kept.append(block.strip())

    css_path.write_text(
        "/* Vendored from Google Fonts — see fetch_vendor.py.\n"
        f"   Source: {FONTS_CSS}\n"
        f"   Subsets kept: {', '.join(FONT_SUBSETS)}.\n"
        "   Plus Jakarta Sans and JetBrains Mono are both SIL Open Font\n"
        "   License 1.1, which permits redistribution with the licence. */\n\n"
        + "\n\n".join(kept) + "\n",
        encoding="utf-8",
    )
    total = sum(f.stat().st_size for f in fonts_dir.glob("*.woff2"))
    print(f"  {total/1024:8.1f} KB  {downloaded} woff2 files + fonts.css")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="download and overwrite; otherwise just report")
    args = ap.parse_args()

    VENDOR.mkdir(parents=True, exist_ok=True)
    problems = 0

    for name, url in ASSETS:
        path = VENDOR / name
        if args.write:
            data = fetch(url)
            path.write_bytes(data)
        elif path.exists():
            data = path.read_bytes()
        else:
            print(f"  MISSING  {name}   <- {url}")
            problems += 1
            continue

        digest = hashlib.sha256(data).hexdigest()[:16]
        print(f"  {len(data)/1024:8.1f} KB  sha256:{digest}  {name}")

    problems += fetch_fonts(args.write)

    print()
    print(f"{len(ASSETS)} scripts + fonts in {VENDOR}")
    if problems:
        print(f"{problems} missing — run with --write")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
