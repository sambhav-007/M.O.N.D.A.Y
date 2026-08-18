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
| `llama3.2:3b` | 171 | 110 | 54 | 4 | 3 | **64.3%** | 1.0s | 1.4s |

Regenerate with `py -3.12 -m reports.stage3_selection --model <name>`.
