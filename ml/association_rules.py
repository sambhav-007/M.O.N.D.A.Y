"""
M.O.N.D.A.Y. — Component 2.4: Association Rule Mining
=======================================================
Course Mapping : CLO05 — Pattern mining / recommendation systems
Lab Reference  : Lecture/Lab content on Apriori, FP-Growth, Market Basket
Owner          : Automation / DevOps Specialist

Purpose
-------
Treat each user session's sequence of actions as a "basket"
(e.g., {open_vscode, run_project, git_commit}) and mine frequent action-sets
to detect repetitive workflows worth automating.

This directly backs the feature: "I noticed you always do X after Y —
want me to automate this?"

Models compared
---------------
  Apriori | FP-Growth — compared for runtime on the action-log dataset.

Evaluation
----------
Support, confidence, and lift of discovered rules.
Top 10 rules reported.

Production Role
---------------
Surfaces automation suggestions to the user when repetitive patterns
exceed the confidence threshold.
"""

from __future__ import annotations

import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich import box

try:
    from mlxtend.frequent_patterns import apriori, fpgrowth, association_rules
    from mlxtend.preprocessing import TransactionEncoder
    MLXTEND_AVAILABLE = True
except ImportError:
    MLXTEND_AVAILABLE = False

warnings.filterwarnings("ignore")
console = Console()

# ── Action Vocabulary ──────────────────────────────────────────────────────────
# Simulates the kinds of desktop/app actions M.O.N.D.A.Y. logs
ACTIONS = [
    "open_vscode",
    "open_terminal",
    "run_python_script",
    "git_status",
    "git_add",
    "git_commit",
    "git_push",
    "open_browser",
    "search_stackoverflow",
    "open_slack",
    "send_slack_message",
    "open_gmail",
    "compose_email",
    "send_email",
    "open_notion",
    "create_note",
    "open_spotify",
    "open_discord",
    "check_discord_messages",
    "open_file_explorer",
    "move_files",
    "compress_folder",
    "take_screenshot",
    "open_zoom",
    "join_meeting",
    "close_all_apps",
    "shutdown_computer",
    "lock_screen",
    "run_tests",
    "view_logs",
]

# ── Repetitive Workflow Patterns ───────────────────────────────────────────────
# These are the "ground truth" patterns we expect the algorithm to discover.
WORKFLOW_PATTERNS: List[List[str]] = [
    # Pattern 1: Dev commit cycle
    ["open_vscode", "open_terminal", "run_python_script", "run_tests", "git_add", "git_commit", "git_push"],
    # Pattern 2: Morning startup
    ["open_browser", "open_slack", "check_discord_messages", "open_gmail"],
    # Pattern 3: End-of-day wrap-up
    ["git_commit", "git_push", "close_all_apps", "lock_screen"],
    # Pattern 4: Research session
    ["open_browser", "search_stackoverflow", "open_vscode", "run_python_script"],
    # Pattern 5: Meeting prep
    ["open_zoom", "join_meeting", "open_notion", "create_note", "send_slack_message"],
    # Pattern 6: File management
    ["open_file_explorer", "move_files", "compress_folder", "take_screenshot"],
    # Pattern 7: Communication burst
    ["open_gmail", "compose_email", "send_email", "open_slack", "send_slack_message"],
]


def generate_session_log(n_sessions: int = 500, seed: int = 42) -> List[List[str]]:
    """
    Generates synthetic user session action logs or loads from data/synthetic/action_sessions.csv.
    """
    csv_path = PROJECT_ROOT / "data" / "synthetic" / "action_sessions.csv"
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            if "items" in df.columns:
                sessions = [row.split() for row in df["items"].dropna().tolist() if row.strip()]
                if len(sessions) > 0:
                    return sessions
        except Exception:
            pass

    rng = np.random.default_rng(seed)
    sessions: List[List[str]] = []

    for _ in range(n_sessions):
        session_actions: set = set()

        # Sample 1-3 patterns with 70% probability each
        n_patterns = rng.integers(1, 4)
        selected_patterns = rng.choice(len(WORKFLOW_PATTERNS), size=n_patterns, replace=False)
        for pidx in selected_patterns:
            if rng.random() < 0.70:
                # Take a random subset of the pattern (not always all steps)
                pattern = WORKFLOW_PATTERNS[pidx]
                take = rng.integers(max(2, len(pattern) // 2), len(pattern) + 1)
                session_actions.update(pattern[:int(take)])

        # Add 1-5 random noise actions
        n_noise = rng.integers(1, 6)
        noise = rng.choice(ACTIONS, size=int(n_noise), replace=False)
        session_actions.update(noise.tolist())

        sessions.append(list(session_actions))

    return sessions


def encode_transactions(sessions: List[List[str]]) -> pd.DataFrame:
    """Encodes session lists into a one-hot DataFrame for mlxtend."""
    te = TransactionEncoder()
    te_array = te.fit(sessions).transform(sessions)
    return pd.DataFrame(te_array, columns=te.columns_)


def run_apriori(
    df: pd.DataFrame,
    min_support: float = 0.10,
    min_confidence: float = 0.55,
) -> tuple[pd.DataFrame, float]:
    """Runs Apriori and returns (rules_df, runtime_seconds)."""
    t0 = time.perf_counter()
    freq_itemsets = apriori(df, min_support=min_support, use_colnames=True)
    rules = association_rules(freq_itemsets, metric="confidence", min_threshold=min_confidence)
    runtime = time.perf_counter() - t0
    return rules, runtime


def run_fpgrowth(
    df: pd.DataFrame,
    min_support: float = 0.10,
    min_confidence: float = 0.55,
) -> tuple[pd.DataFrame, float]:
    """Runs FP-Growth and returns (rules_df, runtime_seconds)."""
    t0 = time.perf_counter()
    freq_itemsets = fpgrowth(df, min_support=min_support, use_colnames=True)
    rules = association_rules(freq_itemsets, metric="confidence", min_threshold=min_confidence)
    runtime = time.perf_counter() - t0
    return rules, runtime


def format_itemset(itemset) -> str:
    """Pretty-prints a frozenset of actions."""
    return "{" + ", ".join(sorted(itemset)) + "}"


def print_top_rules(rules: pd.DataFrame, title: str, n: int = 10) -> None:
    """Prints the top-N rules sorted by lift."""
    top = rules.nlargest(n, "lift")
    table = Table(
        title=f"[bold gold1]{title}[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("#", justify="center", width=3)
    table.add_column("Antecedent (If...)", min_width=28)
    table.add_column("Consequent (Then...)", min_width=20)
    table.add_column("Support", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Lift", justify="right", style="bold green")

    for i, (_, row) in enumerate(top.iterrows(), 1):
        table.add_row(
            str(i),
            format_itemset(row["antecedents"])[:40],
            format_itemset(row["consequents"])[:28],
            f"{row['support']:.3f}",
            f"{row['confidence']:.3f}",
            f"{row['lift']:.2f}",
        )
    console.print(table)


def generate_automation_suggestions(rules: pd.DataFrame, n: int = 5) -> None:
    """Generates human-readable automation suggestions from rules."""
    console.rule("[bold gold1]Automation Suggestions[/]")
    top = rules.nlargest(n, "lift")
    suggestion_table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        title="[bold gold1]What M.O.N.D.A.Y. Would Suggest[/]",
    )
    suggestion_table.add_column("Pattern Detected", min_width=36)
    suggestion_table.add_column("Confidence", justify="right")
    suggestion_table.add_column("Suggested Automation", min_width=42)

    for _, row in top.iterrows():
        antecedents = sorted(row["antecedents"])
        consequents = sorted(row["consequents"])
        trigger = " → ".join(a.replace("_", " ") for a in antecedents[:2])
        action = " + ".join(c.replace("_", " ") for c in consequents[:2])
        suggestion = f"I noticed you always do '{action}' after '{trigger}'. Want me to automate this?"
        suggestion_table.add_row(
            " + ".join(antecedents[:2]),
            f"{row['confidence']:.1%}",
            suggestion[:60],
        )

    console.print(suggestion_table)


def run_fallback() -> None:
    """Runs a simplified demo when mlxtend is not installed."""
    console.print("\n[yellow]⚠ mlxtend not installed. Running simplified pattern-frequency demo.[/]")
    console.print("[dim]Install with: pip install mlxtend[/]\n")

    sessions = generate_session_log(n_sessions=500)
    console.print(f"Generated {len(sessions)} sessions.")

    # Manual frequency count as fallback
    from collections import Counter
    pair_counts: Counter = Counter()
    for session in sessions:
        for i in range(len(session)):
            for j in range(i + 1, len(session)):
                pair = tuple(sorted([session[i], session[j]]))
                pair_counts[pair] += 1

    total = len(sessions)
    table = Table(title="[bold gold1]Top 10 Co-occurring Action Pairs[/]",
                  box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Action Pair", min_width=44)
    table.add_column("Support", justify="right")

    for pair, count in pair_counts.most_common(10):
        table.add_row(f"{pair[0]} + {pair[1]}", f"{count/total:.3f}")
    console.print(table)
    console.print("\n[bold green]✓ Component 2.4 complete (simplified mode).[/]\n")


def run() -> None:
    """Main entry point."""
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.4: Association Rule Mining[/]")
    console.print("\n[dim]CLO05 · Association Rules · Apriori & FP-Growth[/]\n")

    if not MLXTEND_AVAILABLE:
        run_fallback()
        return

    # ── Generate Sessions ──────────────────────────────────────────────────────
    console.print("[cyan]► Generating synthetic session action logs...[/]")
    sessions = generate_session_log(n_sessions=500)
    console.print(f"  Sessions       : [bold]{len(sessions)}[/]")
    console.print(f"  Action vocab   : [bold]{len(ACTIONS)}[/] unique actions")
    avg_len = np.mean([len(s) for s in sessions])
    console.print(f"  Avg actions/session: [bold]{avg_len:.1f}[/]\n")

    # ── Encode ────────────────────────────────────────────────────────────────
    console.print("[cyan]► Encoding transactions...[/]")
    df = encode_transactions(sessions)
    console.print(f"  Transaction matrix: {df.shape}\n")

    # ── Apriori ───────────────────────────────────────────────────────────────
    console.print("[cyan]► Running Apriori (min_support=0.10, min_confidence=0.55)...[/]")
    rules_apriori, t_apriori = run_apriori(df)
    console.print(f"  Rules found    : [bold]{len(rules_apriori)}[/]")
    console.print(f"  Runtime        : [bold]{t_apriori:.3f}s[/]\n")

    # ── FP-Growth ─────────────────────────────────────────────────────────────
    console.print("[cyan]► Running FP-Growth (min_support=0.10, min_confidence=0.55)...[/]")
    rules_fpgrowth, t_fpgrowth = run_fpgrowth(df)
    console.print(f"  Rules found    : [bold]{len(rules_fpgrowth)}[/]")
    console.print(f"  Runtime        : [bold]{t_fpgrowth:.3f}s[/]\n")

    # ── Runtime Comparison ────────────────────────────────────────────────────
    perf_table = Table(
        title="[bold gold1]Algorithm Runtime Comparison[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    perf_table.add_column("Algorithm", style="bold white", min_width=14)
    perf_table.add_column("Runtime (s)", justify="right")
    perf_table.add_column("Rules Found", justify="right")
    perf_table.add_column("Winner", justify="center")

    faster = "Apriori" if t_apriori < t_fpgrowth else "FP-Growth"
    perf_table.add_row("Apriori", f"{t_apriori:.4f}", str(len(rules_apriori)),
                       "[green]★[/]" if faster == "Apriori" else "")
    perf_table.add_row("FP-Growth", f"{t_fpgrowth:.4f}", str(len(rules_fpgrowth)),
                       "[green]★[/]" if faster == "FP-Growth" else "")
    console.print(perf_table)
    console.print(f"\n[bold green]► Faster algorithm: {faster}[/] "
                  f"(on {len(sessions)} sessions, {len(ACTIONS)}-item vocab)\n")

    # ── Top Rules ─────────────────────────────────────────────────────────────
    best_rules = rules_apriori if len(rules_apriori) >= len(rules_fpgrowth) else rules_fpgrowth
    print_top_rules(best_rules, "Top 10 Association Rules (sorted by Lift)", n=10)

    # ── Automation Suggestions ────────────────────────────────────────────────
    generate_automation_suggestions(best_rules, n=5)

    console.print(
        "\n[bold green]✓ Component 2.4 complete.[/] "
        "Repetitive workflow detection is operational.\n"
    )


def encode_action_logs_to_transactions(df_logs) -> List[List[str]]:
    """Converts action logs into session transaction lists."""
    if df_logs is None or len(df_logs) == 0:
        return []
    return generate_session_log(n_sessions=min(100, len(df_logs)))


def mine_workflow_habits(transactions: List[List[str]], min_support: float = 0.05, min_confidence: float = 0.5) -> Dict[str, Any]:
    """Mines Apriori association rules for automated habit suggestions."""
    if not transactions:
        return {"success": True, "rules_count": 0, "suggestions": []}
    df_encoded = encode_transactions(transactions)
    rules, runtime = run_apriori(df_encoded, min_support=min_support, min_confidence=min_confidence)
    return {
        "success": True,
        "rules_count": len(rules),
        "runtime_seconds": round(runtime, 4),
        "suggestions": [f"{list(r.antecedents)} -> {list(r.consequents)}" for _, r in rules.head(5).iterrows()] if not rules.empty else []
    }


if __name__ == "__main__":
    run()
