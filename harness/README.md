# Thin demo harness

A minimal integration that shows each trained model in its production role —
enough for the **live demo (CLO06)** without building the full MONDAY product.

Intended flow (build in phase 4, once models exist):

```
command ──▶ 2.1 classify ──high conf──▶ dispatch to agent
                 │
              low conf ──▶ 2.5 RL router picks strategy ──▶ dispatch
                 │
  Tier-2 task ──▶ 2.2 ETA shown in a mock confirmation prompt
  memory store ─▶ 2.3 cluster assignment
  session end ──▶ 2.4 mining suggests an automation
```

Keep it a single CLI script (`harness/demo.py`) that loads the saved models
(`*.joblib`) and walks a scripted session end-to-end. No web server, no LLM
required for the demo — stub the agent calls with print statements.
