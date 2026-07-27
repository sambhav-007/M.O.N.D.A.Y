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
from datagen.commands import generate_commands


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate MONDAY synthetic datasets")
    ap.add_argument("--commands", type=int, default=10000, help="number of labeled commands")
    ap.add_argument("--sessions", type=int, default=3000, help="number of action-log sessions")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cmds = generate_commands(n=args.commands, seed=args.seed)
    p1 = save_csv(cmds, "commands.csv")
    print(f"[2.1] commands       -> {p1}  ({len(cmds)} rows, {cmds.intent.nunique()} classes)")

    tasks, sessions = generate_logs(n_sessions=args.sessions, seed=args.seed)
    p2 = save_csv(tasks, "action_tasks.csv")
    p3 = save_csv(sessions, "action_sessions.csv")
    print(f"[2.2/2.5] tasks      -> {p2}  ({len(tasks)} rows)")
    print(f"[2.4] sessions       -> {p3}  ({len(sessions)} baskets)")


if __name__ == "__main__":
    main()
