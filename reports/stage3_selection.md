# Stage 3 — skill-selection accuracy, by model

Real utterances from Amazon MASSIVE, **restricted to the ones stages 1
and 2 fail to route** — so this measures the model, not the patterns.
Each MASSIVE intent carries a set of acceptable skills, because several
readings are genuinely defensible; the sets are in `reports/stage3_selection.py`
with the reasoning attached.

Selection accuracy only. Whether the skill then *worked* is task success,
and belongs to Phase 14.

| model | n | correct | wrong | answered instead | declined | accuracy | p50 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llama3.2:3b` | 339 | 224 | 106 | 8 | 1 | **66.1%** | 0.7s | 0.9s |
| `llama3.1:8b` | 339 | 218 | 121 | 0 | 0 | **64.3%** | 1.8s | 2.2s |

Regenerate with `py -3.12 -m reports.stage3_selection --model <name>`.
