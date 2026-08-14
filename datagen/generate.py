"""One command to (re)build every synthetic dataset.

    python -m datagen.generate            # defaults
    python -m datagen.generate --commands 4000 --sessions 1500

Writes to data/synthetic/:
    commands.csv        -> 2.1 Intent Classifier
    action_tasks.csv    -> 2.2 ETA Regression, 2.5 RL Router
    action_sessions.csv -> 2.4 Association Mining
"""

from __future__ import annotations

import argparse

from common.io import save_csv
from datagen.action_logs import generate_logs
from datagen.commands import build_corpus


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate MONDAY synthetic datasets")
    ap.add_argument("--per-class", type=int, default=2500,
                    help="target rows per intent for commands.csv")
    ap.add_argument("--sessions", type=int, default=3000, help="number of action-log sessions")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cmds = build_corpus(per_class=args.per_class, seed=args.seed)
    p1 = save_csv(cmds, "commands.csv")
    by_source = cmds.groupby("source").size().to_dict()
    real = by_source.get("massive", 0)
    print(f"[2.1] commands       -> {p1}  ({len(cmds)} rows, {cmds.intent.nunique()} classes)")
    print(f"      provenance     :  {real} real (MASSIVE) + "
          f"{by_source.get('generated', 0)} generated")
    if real == 0:
        print("      NOTE: data/external/massive_en_us.csv is missing, so this "
              "corpus is generated only.\n"
              "            Run `py -3.12 -m datagen.fetch_massive` to derive it.")

    tasks, sessions = generate_logs(n_sessions=args.sessions, seed=args.seed)
    p2 = save_csv(tasks, "action_tasks.csv")
    p3 = save_csv(sessions, "action_sessions.csv")
    print(f"[2.2/2.5] tasks      -> {p2}  ({len(tasks)} rows)")
    print(f"[2.4] sessions       -> {p3}  ({len(sessions)} baskets)")


if __name__ == "__main__":
    main()
