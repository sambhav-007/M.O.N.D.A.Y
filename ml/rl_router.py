"""
M.O.N.D.A.Y. — Component 2.5: Reinforcement Learning — Agent Routing Optimizer
================================================================================
Course Mapping : CLO05 — RL, agent/environment/reward/policy
Lab Reference  : Lecture 28–30 (RL, agent/environment/reward/policy)
Owner          : AI/ML Specialist

Purpose
-------
When the Intent Classifier is uncertain and the Planner Agent must choose
between routing strategies, use a multi-armed ε-greedy bandit (NOT deep RL
— right-sized for a semester project) to learn over time which routing
decisions lead to task success vs. failure.

Environment / Agent / Reward framing
-------------------------------------
  Environment : M.O.N.D.A.Y. task execution context
  Agent       : RL Router
  State       : current task intent + confidence score from classifier
  Actions     : choose routing strategy (direct-dispatch / planner-routed /
                hybrid-check / clarify-user)
  Reward      : +1 task completed without user correction
                -1 task cancelled, retried, or required correction
  Policy      : ε-greedy bandit (ε decays over time = exploration → exploitation)

Comparative Report (CLO05 explicitly requires this)
----------------------------------------------------
Write-up comparing Supervised (2.1, 2.2), Unsupervised (2.3), and RL (2.5):
  - What each is good for
  - Where they overlap
  - Why RL was the only viable choice for routing optimisation

Evaluation
----------
  • Cumulative reward over time vs. fixed-routing baseline
  • Regret curve (optimal vs. actual reward)
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
from rich.console import Console
from rich.table import Table
from rich import box

warnings.filterwarnings("ignore")
console = Console()

# ── Routing Actions ───────────────────────────────────────────────────────────
ROUTING_ACTIONS = [
    "direct_dispatch",    # High-confidence: skip LLM, go straight to agent
    "planner_routed",     # Use full LLM Planner for multi-step orchestration
    "hybrid_check",       # Run cheap local model first, escalate if needed
    "clarify_user",       # Ask user to clarify before routing
]
N_ACTIONS = len(ROUTING_ACTIONS)

# ── True (hidden) expected reward per action ──────────────────────────────────
# In a real system these would emerge from actual task outcomes.
# Here we set them to simulate a realistic scenario where "direct_dispatch"
# is best for high-confidence tasks, and "planner_routed" is best otherwise.
TRUE_REWARDS: Dict[str, float] = {
    "direct_dispatch": 0.78,   # Good for obvious commands
    "planner_routed":  0.65,   # More overhead, but handles complex tasks
    "hybrid_check":    0.72,   # Safe middle ground
    "clarify_user":    0.42,   # Slow; users find it annoying
}
OPTIMAL_REWARD = max(TRUE_REWARDS.values())
OPTIMAL_ACTION = max(TRUE_REWARDS, key=TRUE_REWARDS.get)  # type: ignore


class EpsilonGreedyBandit:
    """
    ε-greedy Multi-Armed Bandit for M.O.N.D.A.Y. agent routing.

    Parameters
    ----------
    n_arms      : Number of routing strategies (arms)
    epsilon     : Initial exploration rate (0-1)
    epsilon_decay: Multiplicative decay per step (e.g., 0.995)
    epsilon_min : Floor for epsilon (minimum exploration)
    seed        : Random seed for reproducibility
    """

    def __init__(
        self,
        n_arms: int = N_ACTIONS,
        epsilon: float = 0.30,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.01,
        seed: int = 42,
    ) -> None:
        self.n_arms = n_arms
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.rng = np.random.default_rng(seed)

        # Q-table: estimated expected reward per arm
        self.q_values = np.zeros(n_arms)
        # Pull count per arm
        self.pull_counts = np.zeros(n_arms, dtype=int)
        # Total steps
        self.step = 0

    def select_action(self) -> int:
        """ε-greedy action selection."""
        if self.rng.random() < self.epsilon:
            return int(self.rng.integers(self.n_arms))  # Explore
        return int(np.argmax(self.q_values))             # Exploit

    def update(self, action: int, reward: float) -> None:
        """Incremental mean update for selected arm."""
        self.pull_counts[action] += 1
        n = self.pull_counts[action]
        self.q_values[action] += (reward - self.q_values[action]) / n
        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.step += 1

    def get_policy(self) -> str:
        """Returns current best action name."""
        return ROUTING_ACTIONS[int(np.argmax(self.q_values))]


class FixedBaselineRouter:
    """
    Baseline: always routes to 'planner_routed' (fixed strategy, no learning).
    Used to demonstrate the advantage of RL.
    """

    def select_action(self) -> int:
        return ROUTING_ACTIONS.index("planner_routed")

    def update(self, action: int, reward: float) -> None:
        pass  # No learning


def simulate_reward(action_idx: int, rng: np.random.Generator) -> float:
    """
    Simulates a stochastic reward for the chosen routing action.
    Reward is Bernoulli-distributed around the true expected value.
    """
    action_name = ROUTING_ACTIONS[action_idx]
    p_success = TRUE_REWARDS[action_name]
    return float(rng.random() < p_success)


def run_simulation(
    n_steps: int = 1000,
    bandit_epsilon: float = 0.30,
    seed: int = 42,
) -> Tuple[List[float], List[float], List[float], List[float]]:
    """
    Runs the RL bandit vs. fixed baseline for n_steps tasks.

    Returns
    -------
    rl_rewards     : per-step rewards for RL bandit
    base_rewards   : per-step rewards for fixed baseline
    rl_cumulative  : cumulative reward for RL bandit
    base_cumulative: cumulative reward for baseline
    """
    rng = np.random.default_rng(seed)

    bandit = EpsilonGreedyBandit(epsilon=bandit_epsilon, seed=seed)
    baseline = FixedBaselineRouter()

    rl_rewards: List[float] = []
    base_rewards: List[float] = []
    rl_cum: List[float] = []
    base_cum: List[float] = []
    rl_running = 0.0
    base_running = 0.0

    for _ in range(n_steps):
        # RL bandit step
        rl_action = bandit.select_action()
        rl_r = simulate_reward(rl_action, rng)
        bandit.update(rl_action, rl_r)
        rl_running += rl_r
        rl_rewards.append(rl_r)
        rl_cum.append(rl_running)

        # Baseline step
        base_action = baseline.select_action()
        base_r = simulate_reward(base_action, rng)
        base_running += base_r
        base_rewards.append(base_r)
        base_cum.append(base_running)

    return rl_rewards, base_rewards, rl_cum, base_cum


def compute_regret(rl_rewards: List[float], n_steps: int) -> List[float]:
    """
    Regret = (optimal expected reward × t) − cumulative actual reward.
    Shows how much the RL agent "missed out" compared to always choosing optimally.
    """
    regret: List[float] = []
    running_regret = 0.0
    for t, r in enumerate(rl_rewards, 1):
        running_regret += OPTIMAL_REWARD - r
        regret.append(running_regret)
    return regret


def print_bandit_state(bandit: EpsilonGreedyBandit) -> None:
    """Prints the bandit's Q-table after training."""
    table = Table(
        title="[bold gold1]Bandit Q-Table (Learned Routing Values)[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Routing Action", style="bold white", min_width=20)
    table.add_column("True Reward", justify="right")
    table.add_column("Learned Q-Value", justify="right")
    table.add_column("Pull Count", justify="right")
    table.add_column("Error", justify="right")

    best_idx = int(np.argmax(bandit.q_values))
    for i, action in enumerate(ROUTING_ACTIONS):
        true_r = TRUE_REWARDS[action]
        learned = bandit.q_values[i]
        error = abs(learned - true_r)
        is_best = i == best_idx
        style = "bold green" if is_best else ""
        mark = " ★" if is_best else ""
        table.add_row(
            f"{action}{mark}",
            f"{true_r:.3f}",
            f"{learned:.3f}",
            str(bandit.pull_counts[i]),
            f"{error:.3f}",
            style=style,
        )
    console.print(table)


def print_performance_summary(
    rl_cum: List[float],
    base_cum: List[float],
    regret: List[float],
    n_steps: int,
) -> None:
    """Prints final performance comparison."""
    table = Table(
        title="[bold gold1]RL vs. Fixed Baseline — Performance Summary[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="bold white", min_width=28)
    table.add_column("RL Bandit", justify="right", style="bold green")
    table.add_column("Fixed Baseline", justify="right")
    table.add_column("Improvement", justify="right")

    rl_total = rl_cum[-1]
    base_total = base_cum[-1]
    improvement = rl_total - base_total
    success_rate_rl = rl_total / n_steps
    success_rate_base = base_total / n_steps
    final_regret = regret[-1]

    table.add_row("Total Reward", f"{rl_total:.1f}", f"{base_total:.1f}",
                  f"[green]+{improvement:.1f}[/]" if improvement > 0 else f"[red]{improvement:.1f}[/]")
    table.add_row("Task Success Rate", f"{success_rate_rl:.1%}", f"{success_rate_base:.1%}",
                  f"+{(success_rate_rl - success_rate_base):.1%}")
    table.add_row("Cumulative Regret", f"{final_regret:.1f}", "N/A (no learning)", "—")
    table.add_row("Learned Best Action", ROUTING_ACTIONS[int(np.argmax(
        EpsilonGreedyBandit(seed=42).q_values))], "planner_routed (fixed)", "—")

    console.print(table)


def print_comparative_report() -> None:
    """Prints the CLO05-required comparison of Supervised / Unsupervised / RL."""
    console.rule("[bold gold1]CLO05 Comparative Report: Supervised vs. Unsupervised vs. RL[/]")

    report = """
┌─────────────────────────────────────────────────────────────────────────────┐
│                   COMPARATIVE ANALYSIS — CLO05 REQUIREMENT                 │
├───────────────────┬────────────────────────┬───────────────────────────────┤
│ Dimension         │ Supervised (2.1 / 2.2) │ Unsupervised (2.3)            │
├───────────────────┼────────────────────────┼───────────────────────────────┤
│ Training signal   │ Labelled examples      │ No labels — structure only    │
│ Goal              │ Predict discrete class │ Discover hidden groupings     │
│                   │ or continuous value    │                               │
│ M.O.N.D.A.Y. use │ Route commands / ETA   │ Organise memory, suggest      │
│ Strengths         │ High accuracy when     │ Scales to new data without    │
│                   │ data is labelled well  │ re-labelling                  │
│ Weaknesses        │ Needs large labelled   │ No guarantee clusters are     │
│                   │ dataset; brittle to    │ meaningful; no direct metric  │
│                   │ distribution shift     │ optimisation                  │
├───────────────────┼────────────────────────┼───────────────────────────────┤
│                   │ RL (2.5)                                               │
├───────────────────┼───────────────────────────────────────────────────────┤
│ Training signal   │ Delayed reward from environment interaction            │
│ Goal              │ Maximise long-run cumulative reward                    │
│ M.O.N.D.A.Y. use │ Routing optimisation: learns which strategy works best │
│ Strengths         │ No need for labelled data; adapts online to user habit │
│ Weaknesses        │ Slow convergence; reward is sparse and noisy           │
│ Why RL only?      │ Supervised requires labelled "correct routing" pairs — │
│                   │ these don't exist upfront. Unsupervised can't optimise │
│                   │ for task success. RL is the only paradigm that learns  │
│                   │ the right action from outcome feedback.                │
└───────────────────┴───────────────────────────────────────────────────────┘
"""
    console.print(report)


def run() -> EpsilonGreedyBandit:
    """Main entry point."""
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.5: RL Agent Router[/]")
    console.print("\n[dim]CLO05 · Reinforcement Learning · Lecture 28–30[/]\n")

    N_STEPS = 1000
    console.print(f"[cyan]► Running ε-greedy bandit simulation ({N_STEPS} routing decisions)...[/]")
    console.print(f"  Routing actions : {ROUTING_ACTIONS}")
    console.print(f"  Optimal action  : [bold]{OPTIMAL_ACTION}[/] (true reward = {OPTIMAL_REWARD})\n")

    rl_rewards, base_rewards, rl_cum, base_cum = run_simulation(n_steps=N_STEPS)
    regret = compute_regret(rl_rewards, N_STEPS)

    # Reconstruct bandit for printing Q-table
    bandit = EpsilonGreedyBandit(epsilon=0.30, seed=42)
    rng = np.random.default_rng(42)
    for _ in range(N_STEPS):
        action = bandit.select_action()
        reward = simulate_reward(action, rng)
        bandit.update(action, reward)

    console.print()
    print_bandit_state(bandit)
    console.print(f"\n[bold green]► Learned best routing: {bandit.get_policy()}[/] "
                  f"(ε = {bandit.epsilon:.4f} after {N_STEPS} steps)\n")

    print_performance_summary(rl_cum, base_cum, regret, N_STEPS)

    # Reward over time (simplified text chart)
    console.print("\n[bold cyan]Cumulative Reward Progression (every 100 steps):[/]")
    progress_table = Table(box=box.SIMPLE, header_style="bold cyan")
    progress_table.add_column("Step", justify="right")
    progress_table.add_column("RL Bandit", justify="right", style="green")
    progress_table.add_column("Fixed Baseline", justify="right")
    progress_table.add_column("Regret", justify="right", style="yellow")

    for step in range(99, N_STEPS, 100):
        progress_table.add_row(
            str(step + 1),
            f"{rl_cum[step]:.1f}",
            f"{base_cum[step]:.1f}",
            f"{regret[step]:.1f}",
        )
    console.print(progress_table)

    print_comparative_report()

    console.print(
        "\n[bold green]✓ Component 2.5 complete.[/] "
        f"RL bandit converged on [{bandit.get_policy()}] as optimal routing strategy.\n"
    )
    return bandit


if __name__ == "__main__":
    run()
