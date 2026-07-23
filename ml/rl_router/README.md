# 2.5 RL Agent-Routing Optimizer — CLO05 (reinforcement learning)

**Owner:** AI/ML specialist · **Reuses:** Lectures 28–30 (agent/environment/reward/policy)

When the Intent Classifier (2.1) is uncertain, learn over time which routing
strategy leads to task success. **Multi-armed bandit** — right-sized for a
semester project, not deep RL.

## Data
`data/synthetic/action_tasks.csv` — columns `routing_arm` and `outcome`
(`success`/`corrected`). Reward = 1 if `success` (task completed without user
correction), else 0. Ground-truth arm success rates are baked in
(`direct_dispatch` 0.82 · `planner_llm` 0.90 · `cached_plan` 0.68) so a working
bandit should converge toward `planner_llm`.

## Method
ε-greedy and/or UCB bandit over the 3 routing arms.

## Graded evidence (`notebooks/2_5_rl_router.ipynb`)
- **Cumulative reward over time** vs a fixed-routing baseline
- **Regret curve**
- The required **comparative report**: Supervised (2.1/2.2) vs Unsupervised (2.3)
  vs RL (2.5) — what each is good for, where they overlap, where RL was the only
  viable choice. Write this in `reports/comparative_report.md`.
