"""Derive the real-utterance half of the intent corpus from Amazon MASSIVE.

    py -3.12 -m datagen.fetch_massive

Downloads MASSIVE 1.0 (39.5 MB, all 51 locales), keeps **en-US only**, maps its
60 intents onto MONDAY's 7, and writes `data/external/massive_en_us.csv`. The
tarball is discarded; only the derived CSV is kept, and it is committed, so a
fresh clone trains without ever touching the network. This script exists to make
that derivation auditable and repeatable, not because it needs to run.

Why an external corpus at all
-----------------------------
`data/synthetic/commands.csv` is generated, and `data/DATASET.md` is right that
generation buys balance, reproducibility and no personal data. What it cannot
buy is *how people actually phrase things*. Measured on 2026-08-13 against the
67 commands the app itself advertises (`/help`, the demo list, the routing set),
the classifier trained on synthetic data alone scored **0.657 accuracy at 0.549
mean confidence**, against 0.929 macro-F1 on its own held-out synthetic split.
`what time is it` came back `memory_query` at 0.33; `what is the capital of
france` came back `chitchat` at 0.47.

MASSIVE is the right corpus for the overlap because it is the same *kind* of
data — 16,521 English utterances spoken to a virtual assistant, collected from
human workers, not templated. SLURP/MASSIVE covers volume control, date and time
questions, factoid QA, weather, news, email, calendar and list management, which
is most of MONDAY's surface.

What it does not cover is the rest: launching a desktop application, killing a
process, taking a screenshot, reading the battery, summarising a local file,
WhatsApp. There is no public corpus for those, so they stay generated —
`datagen/commands.py` covers them deliberately and says so.

Provenance
----------
* Source: https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.0.tar.gz
* Paper: FitzGerald et al., *MASSIVE: A 1M-Example Multilingual Natural Language
  Understanding Dataset with 51 Typologically-Diverse Languages*, ACL 2023.
  https://arxiv.org/abs/2204.08582
* Licence: Apache 2.0 (`1.0/LICENSE` in the tarball, reproduced alongside the
  derived CSV as `data/external/MASSIVE_LICENSE.txt`).
* Downloaded and derived: 2026-08-13.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from datagen.massive import MASSIVE_TO_MONDAY, OUT_CSV, map_rows  # noqa: E402

TARBALL_URL = (
    "https://amazon-massive-nlu-dataset.s3.amazonaws.com/"
    "amazon-massive-dataset-1.0.tar.gz"
)
LOCALE_MEMBER = "1.0/data/en-US.jsonl"
LICENSE_MEMBER = "1.0/LICENSE"
OUT_LICENSE = PROJECT_ROOT / "data" / "external" / "MASSIVE_LICENSE.txt"


def download(url: str = TARBALL_URL) -> bytes:
    """Streams the tarball into memory. ~39.5 MB; nothing is left on disk."""
    import httpx

    print(f"Downloading {url}")
    buf = io.BytesIO()
    with httpx.stream("GET", url, timeout=180.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(1 << 20):
            buf.write(chunk)
            print(f"\r  {buf.tell() / 1e6:6.1f} MB", end="", flush=True)
    print()
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tarball",
        type=Path,
        default=None,
        help="Use an already-downloaded tarball instead of fetching it.",
    )
    args = ap.parse_args()

    raw = args.tarball.read_bytes() if args.tarball else download()

    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        member = tf.extractfile(LOCALE_MEMBER)
        if member is None:
            raise SystemExit(f"{LOCALE_MEMBER} not found in the archive")
        rows = [
            json.loads(line)
            for line in member.read().decode("utf-8").splitlines()
            if line.strip()
        ]
        licence = tf.extractfile(LICENSE_MEMBER)
        licence_text = licence.read().decode("utf-8") if licence else ""

    print(f"en-US utterances       : {len(rows)}")
    print(f"MASSIVE intents        : {len({r['intent'] for r in rows})}")
    print(f"mapped to MONDAY       : {len(MASSIVE_TO_MONDAY)}")

    df = map_rows(rows)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    if licence_text:
        OUT_LICENSE.write_text(licence_text, encoding="utf-8")

    kept = len(df)
    print(f"kept after mapping     : {kept} ({kept / len(rows):.0%})")
    print()
    print(df["intent"].value_counts().to_string())
    print()
    print(f"Wrote {OUT_CSV.relative_to(PROJECT_ROOT)}")
    if licence_text:
        print(f"Wrote {OUT_LICENSE.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
