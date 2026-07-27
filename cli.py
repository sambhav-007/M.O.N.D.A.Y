"""
M.O.N.D.A.Y. — Interactive Terminal AI Assistant Shell
========================================================
Course: Artificial Intelligence and Machine Learning (24CSE0316)
Team: Siddhant Bhatia, Sambhav Sehgal, Samarth Sharma, Shivansh Chandel

Usage
-----
    python cli.py
    # or
    python -m cli
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

from core.planner import MasterPlanner
from core.security import get_action_history

console = Console()


def print_banner() -> None:
    """Prints the M.O.N.D.A.Y. terminal header banner."""
    banner = r"""
[bold orange1]   __  ___  ____  _  ______  ___  __  ___[/]
[bold orange1]  /  |/  / / __ \/ |/ / _  \/ _ \/ / / / [/]
[bold orange1] / /|_/ / / /_/ /    / // / / __ / /_/ /  [/]
[bold orange1]/_/  /_/  \____/_/|_/____/\/_/ /_\____/   [/]
[dim]Modular Operational Neural Desktop Assistant for You[/]
[cyan]Course 24CSE0316 · AI & Machine Learning Project[/]
"""
    console.print(Panel(banner, border_style="gold1", box=box.ROUNDED))

    # Print active ML matrix status
    ml_status = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", show_header=True)
    ml_status.add_column("Component", style="bold white", min_width=18)
    ml_status.add_column("CLO", justify="center", style="bold yellow")
    ml_status.add_column("Technique", style="dim")
    ml_status.add_column("Status", justify="center", style="bold green")

    ml_status.add_row("2.1 Intent Classifier", "CLO04", "Logistic Reg / SVM / KNN / DT", "✓ Active")
    ml_status.add_row("2.2 Task ETA Regressor", "CLO03", "Polynomial Regression (deg=2)", "✓ Active")
    ml_status.add_row("2.3 Memory Clusterer", "CLO04", "K-Means / DBSCAN + PCA", "✓ Active")
    ml_status.add_row("2.4 Workflow Miner", "CLO05", "Apriori / FP-Growth", "✓ Active")
    ml_status.add_row("2.5 RL Router Bandit", "CLO05", "ε-greedy Multi-Armed Bandit", "✓ Active")

    console.print(ml_status)
    console.print("\n[bold green]✓ Real Multi-Agent Worker Engine Online.[/] Type [bold cyan]'help'[/] for commands or [bold cyan]'exit'[/] to quit.\n")


def print_help() -> None:
    """Prints command cheat sheet."""
    table = Table(title="[bold gold1]M.O.N.D.A.Y. Command Reference[/]", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Category", style="bold white", min_width=16)
    table.add_column("Example Command", min_width=36)
    table.add_column("Target Agent / Tool", style="dim")

    table.add_row("Voice Engine", "speak M.O.N.D.A.Y. online", "VoiceAgent — Text-to-Speech synthesis")
    table.add_row("Desktop OS", "organize C:\\path\\to\\folder", "ComputerAgent — Sort by extension")
    table.add_row("Desktop OS", "screenshot", "ComputerAgent — Capture primary screen")
    table.add_row("Desktop OS", "open vscode (or notepad, calc)", "ComputerAgent — Launch app")
    table.add_row("Desktop OS", "health", "ComputerAgent — CPU/RAM/Disk stats")
    table.add_row("Document RAG", "summarize sample.pdf (or path)", "DocumentAgent — Extractive summary")
    table.add_row("Web Research", "search Next.js 16 features", "BrowserAgent — Live DDG web search")
    table.add_row("Web Research", "research AI agent architectures", "BrowserAgent — Multi-source report")
    table.add_row("Memory Matrix", "remember professor's email is priyanka@vitbhopal.ac.in", "MemoryAgent — Store fact")
    table.add_row("Memory Matrix", "recall professor", "MemoryAgent — TF-IDF recall")
    table.add_row("Proactive ML", "proactive", "Memory (2.3) + Habit (2.4) suggestions")
    table.add_row("Communication", "draft email to professor@vit.ac.in", "CommsAgent — Prepare email draft")
    table.add_row("Audit Logs", "history", "Security Engine — Audit action log")

    console.print(table)


def run_interactive_shell() -> None:
    """Main interactive terminal loop."""
    print_banner()

    with console.status("[bold gold1]Initializing M.O.N.D.A.Y. Master Planner & Workers...[/]"):
        planner = MasterPlanner()

    while True:
        try:
            user_input = Prompt.ask("\n[bold orange1]monday[/] [bold cyan]>[/]").strip()

            if not user_input:
                continue

            cmd_lower = user_input.lower()

            if cmd_lower in ["exit", "quit", "q"]:
                console.print("\n[bold gold1]Shutting down M.O.N.D.A.Y. Goodbye![/]")
                break

            if cmd_lower in ["help", "?", "commands"]:
                print_help()
                continue

            if cmd_lower in ["proactive", "suggestions"]:
                console.rule("[bold gold1]Proactive AI Suggestions[/]")
                sug_mem = planner.memory_agent.get_proactive_suggestions()
                sug_hab = planner.habit_agent.detect_habits_and_suggest()

                console.print("\n[bold cyan]🧠 Memory Topic Suggestions (Component 2.3 Clustering):[/]")
                for s in sug_mem.get("suggestions", []):
                    console.print(f"  {s.get('prompt')}")

                console.print("\n[bold cyan]⚡ Workflow Habit Suggestions (Component 2.4 Association Mining):[/]")
                for h in sug_hab.get("suggestions", []):
                    console.print(f"  {h.get('prompt')}")
                continue

            if cmd_lower in ["train-voice", "train voice", "voice-train"]:
                console.print("\n[bold gold1]🎙️ Training M.O.N.D.A.Y. Voice Model on mondayvoice.mp3...[/]")
                res = planner.voice_agent.train_voice()
                console.print(f"[bold green]{res.get('message')}[/]")
                continue

            if cmd_lower in ["history", "log", "audit"]:
                history = get_action_history(limit=10)
                table = Table(title="[bold gold1]Recent Action Audit Log[/]", box=box.SIMPLE_HEAD)
                table.add_column("Timestamp", style="dim")
                table.add_column("Action", style="bold white")
                table.add_column("Target")
                table.add_column("Tier", justify="center")
                table.add_column("Status", justify="center")

                for h in history:
                    tier_str = f"[green]T1[/]" if h.get("tier") == 1 else f"[red]T2[/]"
                    table.add_row(
                        h.get("timestamp", "")[:19].replace("T", " "),
                        h.get("action", ""),
                        str(h.get("target", ""))[:30],
                        tier_str,
                        "[green]Success[/]" if h.get("status") == "success" else "[red]Failed[/]",
                    )
                console.print(table)
                continue

            # ── Process Command through Master Planner ─────────────────────────
            with console.status("[bold cyan]Processing through ML Pipeline...[/]"):
                res = planner.process_command(user_input)

            intent_info = res.get("intent_classification", {})
            routing_info = res.get("rl_routing", {})
            result = res.get("execution_result", {})

            # Display Pipeline Inspection
            console.print(
                f"[dim]Classifier (CLO04): [bold]{intent_info.get('predicted_intent')}[/] "
                f"({intent_info.get('confidence'):.1%}) | "
                f"RL Router (CLO05): [{routing_info.get('strategy')}][/dim]"
            )

            # Check if Tier 2 Approval is required
            if result.get("tier_2_gated", False):
                console.print(f"\n[bold red]{result.get('confirmation_prompt')}[/]")
                approved = Confirm.ask("Do you approve this Tier 2 action?")
                if approved:
                    with console.status("[bold cyan]Executing approved Tier 2 action...[/]"):
                        res = planner.process_command(user_input, user_approved=True)
                        result = res.get("execution_result", {})
                else:
                    console.print("[yellow]Action cancelled by user.[/]")
                    continue

            # Display Result
            if result.get("success", False):
                msg = result.get("message", "Action completed.")
                console.print(f"\n[bold green]{msg}[/]")

                # Render specialized output widgets
                if "breakdown" in result:
                    table = Table(title="Organized Files Breakdown", box=box.SIMPLE)
                    table.add_column("Category", style="bold cyan")
                    table.add_column("Count", justify="right")
                    table.add_column("Files", style="dim")
                    for cat, files in result["breakdown"].items():
                        table.add_row(cat, str(len(files)), ", ".join(files[:3]) + ("..." if len(files) > 3 else ""))
                    console.print(table)

                if "summary" in result and isinstance(result["summary"], str):
                    console.print(Panel(result["summary"], title=f"Summary: {result.get('document', '')}", border_style="cyan"))

                if "report" in result:
                    console.print(Panel(result["report"], title=f"Research Report: {result.get('topic', '')}", border_style="gold1"))

                if "matches" in result and isinstance(result["matches"], list):
                    for m in result["matches"]:
                        console.print(f"  • [bold]{m.get('key')}[/]: {m.get('value')} [dim]({m.get('topic')})[/dim]")

                if "results" in result and isinstance(result["results"], list):
                    for r in result["results"][:4]:
                        console.print(f"  • [bold]{r.get('title')}[/]\n    [dim]{r.get('snippet')}[/dim]\n    [blue]{r.get('url')}[/blue]")

            else:
                err = result.get("error", "Failed to execute command.")
                console.print(f"\n[bold red]❌ Error: {err}[/]")

        except KeyboardInterrupt:
            console.print("\n[bold gold1]Use 'exit' to quit.[/]")
        except Exception as e:
            console.print(f"\n[bold red]An unexpected error occurred: {e}[/]")


if __name__ == "__main__":
    run_interactive_shell()
