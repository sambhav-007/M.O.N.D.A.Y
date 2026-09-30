# M.O.N.D.A.Y — Dataset Card

_Course: 24CSE0316 — Artificial Intelligence and Machine Learning._
_Last verified against the files on disk: 2026-08-13._

## Summary

Four datasets, all committed to the repository. Three are **generated**; one is
**real**, and the intent corpus that trains component 2.1 is a mixture of the
two. Which rows are which is recorded in the file itself, in a `source` column —
no downstream number has to take the mix on trust.

| File | Rows | Cols | Size | Provenance | Feeds |
|---|---|---|---|---|---|
| [`synthetic/commands.csv`](synthetic/commands.csv) | 17,488 | 3 | 1.1 MB | 6,847 real + 10,641 generated | **2.1** Intent Classifier (CLO04) |
| [`external/massive_en_us.csv`](external/massive_en_us.csv) | 11,180 | 4 | 788 KB | **real** — Amazon MASSIVE, en-US | source pool for the above |
| [`synthetic/action_tasks.csv`](synthetic/action_tasks.csv) | 7,655 | 10 | 544 KB | generated | **2.2** ETA Regression (CLO03), **2.5** RL Router (CLO05) |
| [`synthetic/action_sessions.csv`](synthetic/action_sessions.csv) | 3,000 | 2 | 108 KB | generated | **2.4** Association Rule Mining (CLO05) |

All four are tracked in git — a fresh clone has them without running anything,
and without touching the network.

## Regenerating

```bash
py -3.12 -m datagen.generate
```

Deterministic: `seed=42`. Re-running reproduces the files byte-for-byte, so a
reported metric can be traced back to the exact data that produced it. Sizes are
adjustable — `--per-class 1500 --sessions 1500`.

Re-deriving the real half is a separate, deliberate step, because it downloads
39.5 MB and its output is already committed:

```bash
py -3.12 -m datagen.fetch_massive
```

The generators live in [`datagen/`](../datagen/):

| File | Role |
|---|---|
| `datagen/config.py` | Shared vocabulary — intents, agent mapping, task timing profiles. Single source of truth |
| `datagen/commands.py` | Templates + fillers + noise, and `build_corpus()` which mixes them with the real half |
| `datagen/massive.py` | Maps MASSIVE's 60 intents onto MONDAY's 7 — one entry per intent, with the reason |
| `datagen/fetch_massive.py` | Downloads MASSIVE and derives `external/massive_en_us.csv`. Run once; the output is committed |
| `datagen/action_logs.py` | Builds `action_tasks.csv` and `action_sessions.csv` |
| `datagen/generate.py` | Entry point that writes all three synthetic files |

---

## 1. `commands.csv` — labelled natural-language commands

**Task**: multi-class text classification. **Used by**: component 2.1.

| Column | Type | Description |
|---|---|---|
| `text` | string | A user command as typed, e.g. `tl;dr the PDF asap` |
| `intent` | categorical | One of 7 labels |
| `source` | categorical | `massive` (real) or `generated` |

**Class balance and provenance**, per class:

| Intent | Real (MASSIVE) | Generated | Total |
|---|---|---|---|
| browser | 1,700 | 850 | 2,550 |
| communication | 1,700 | 830 | 2,530 |
| desktop_automation | 1,700 | 848 | 2,548 |
| memory_query | 789 | 1,694 | 2,483 |
| llm_fallback | 826 | 1,680 | 2,506 |
| document_intel | 0 | 2,451 | 2,451 |
| chitchat | 132 | 2,288 | 2,420 |

`document_intel` gets **nothing** from MASSIVE, and that is not an oversight:
MASSIVE is a voice-assistant corpus, and nobody dictates "summarise chapter 3 of
the PDF" to a smart speaker. That class is wholly generated, and it is the one to
watch if document accuracy on real commands ever slips.

**Deliberate difficulty.** 6% of the *generated* rows have their label flipped at
random (`label_noise=0.06`), and classes share filler vocabulary on purpose. An
earlier version of the generator produced trivially separable data and the
classifier scored a meaningless **1.000**. The noise is applied to generated rows
only — corrupting real human labels to make a benchmark harder would be
vandalism, and MASSIVE's ambiguity is already the genuine article.

**Why the corpus was rebuilt on 2026-08-13.** The generated-only version had
9,996 rows, but they came from **117 sentence skeletons** over a **924-word
vocabulary** — the row count was slot permutation, not linguistic variety. Whole
capabilities the app advertises in `/help` (battery, my ip, kill, recall, bitcoin
price, iss location, proactive) appeared in **no template at all**. Measured
against the app's own commands, the classifier scored **0.657 accuracy at 0.549
mean confidence**, against 0.929 macro-F1 on its own held-out split. See
[`reports/real_command_evidence.md`](../reports/real_command_evidence.md).

The current CSV contains **4,639 unique whitespace-delimited tokens**. The
classifier scores **1.000 on the advertised-command coverage set** and **0.649
on the held-out paraphrase set**; the latter is the meaningful generalisation
number because those phrasings are not in the generator.

**A cap worth knowing about.** `build_synthetic_dataset` capped the corpus at
**500 rows per class**, so the 9,996-row file was fitted on 2,800 rows — 72%
discarded before the model saw it. Growing a dataset does nothing while that cap
binds. It is now `ml.intent_classifier.SAMPLES_PER_CLASS = 2500`, named in one
place and asserted by `tests/test_intent_corpus.py`.

---

## 1b. `external/massive_en_us.csv` — the real half

**Source**: [Amazon MASSIVE 1.0](https://github.com/alexa/massive), the
multilingual extension of SLURP. 16,521 English utterances spoken to a virtual
assistant by human workers, across 18 scenarios and 60 intents.

**Licence**: Apache 2.0, reproduced verbatim at
[`external/MASSIVE_LICENSE.txt`](external/MASSIVE_LICENSE.txt).

**Citation**: FitzGerald et al., *MASSIVE: A 1M-Example Multilingual Natural
Language Understanding Dataset with 51 Typologically-Diverse Languages*, ACL
2023. <https://arxiv.org/abs/2204.08582>

| Column | Type | Description |
|---|---|---|
| `text` | string | The utterance, unmodified |
| `intent` | categorical | The MONDAY label it was mapped to |
| `source` | constant | `massive` |
| `massive_intent` | categorical | The original label, kept so the mapping is auditable |

**The mapping is the contribution**, and it lives in `datagen/massive.py` with a
reason on every line. 35 of MASSIVE's 60 intents are mapped; the other 25 are
listed with the reason they were refused. The governing rule is that **an
utterance is kept only if MONDAY has somewhere to send it** — a real command
mapped to a class the app cannot serve does not make the classifier better, it
makes it confidently wrong.

Worked examples of both directions:

- `audio_volume_up` → `desktop_automation`. 387 real phrasings of a headline
  feature that had six templated ones.
- `qa_stock` / `qa_currency` → `browser`. `bitcoin price` used to classify
  `desktop_automation` at 0.26.
- `general_quirky` → `llm_fallback`. MASSIVE's own catch-all for utterances that
  fit no intent is exactly what this project means by the low-confidence bucket.
- `transport_ticket` → **dropped**. There is no booking capability.
- `play_music` → **dropped**. `open spotify` is a launcher command; there is no
  playback control.

`tests/test_intent_corpus.py` asserts every one of the 60 is either mapped or
explicitly refused, so a future MASSIVE release adding an intent fails a test
rather than being silently discarded.

MASSIVE's own train/dev/test split is deliberately **not** reused — this project
makes its own, and mixing two evaluation protocols would make neither reportable.

---

## 2. `action_tasks.csv` — per-task execution log

**Tasks**: regression (`duration_sec`) and bandit reward (`outcome`).
**Used by**: components 2.2 and 2.5.

| Column | Type | Description |
|---|---|---|
| `session_id` | int | Groups tasks into a user session |
| `task_type` | categorical | 10 types (`run_script`, `open_app`, `send_email`, …) |
| `agent` | categorical | Which of 5 agents handled it |
| `step_count` | int | Sub-steps the task took |
| `hour` | int | Hour of day, 0–23 |
| `historical_avg` | float | Prior mean duration for this task type |
| `duration_sec` | float | **Regression target** |
| `tier` | int | Security tier, 1 or 2 (PRD §9) |
| `routing_arm` | categorical | `direct_dispatch` / `cached_plan` / `planner_llm` |
| `outcome` | categorical | `success` (6,176) / `corrected` (1,479) — the bandit reward |

Durations are drawn from documented per-task profiles in `datagen/config.py`
(base seconds + seconds per step) with noise added. Those numbers are stated
**assumptions of the simulation, not measurements** — the file says so directly.

---

## 3. `action_sessions.csv` — transaction baskets

**Task**: frequent-itemset / association rule mining. **Used by**: component 2.4.

| Column | Type | Description |
|---|---|---|
| `session_id` | int | Session identifier |
| `items` | string | Space-separated action names, e.g. `open_app run_script send_email` |

Standard market-basket shape, one basket per session, mined with Apriori and
FP-Growth.

---

## Component 2.3 has no file — and that is worth stating

**Memory clustering (2.3)** does not read a CSV. It generates its data in memory
each run: 700 samples drawn as Gaussian clusters around 7 topic centroids —
*Machine Learning Coursework, Project Monday Development, Job Applications &
Internships, Personal Finance & Shopping, Research Papers & References,
Communication & Emails, Desktop Files & Organisation*.

So if asked "where is the dataset for clustering", the honest answer is that it
is synthesised at runtime by `ml/memory_clustering.py` rather than stored. It can
be exported to `data/synthetic/` on request; it simply has not been, because
nothing needed it on disk.

At runtime the same component clusters the **real** memory store
(`data/memory.db`), which is the user's own saved notes and is not committed.

---

## Provenance — why this mixture, and the honest limitations

**Why generation at all.** The project routes commands to agents that act on a
real desktop — sending email, opening applications, terminating processes. A
collected corpus would consist of one team's commands on their own machines,
carrying their filenames, contacts and habits. Generation gives balanced classes,
a known ground truth, reproducibility from a seed, and no personal data. It is
also the *only* source for the app's own surface: no public corpus contains
`kill notepad`, `summarise notes.txt`, `iss location` or `subject "…" body "…"`.

**Why real data as well.** What generation cannot buy is how people actually
phrase things. This card previously argued that the honest improvement was
"widening the generator's vocabulary rather than downloading an unrelated public
corpus". Half of that was right and half was wrong, and the measurement is what
settled it: widening the generator was necessary, but a *related* public corpus
existed. MASSIVE is the same kind of data — utterances spoken to a virtual
assistant — and it covers volume control, date and time, factoid QA, weather,
news, email, calendar and lists, which is most of what MONDAY does.

**The limitations, stated rather than discovered:**

- **The action logs are simulated end to end.** Durations, outcomes and
  co-occurrence patterns in `action_tasks.csv` / `action_sessions.csv` come from
  the assumptions in `datagen/config.py`. Components 2.2, 2.4 and 2.5 learn those
  assumptions well; they have not been validated against real usage. This is
  unchanged — only the *command* corpus gained real data.
- **The held-out macro-F1 is still a within-corpus number.** 0.919 (SVM) says the
  model learned the corpus, not that the corpus resembles a user. The number for
  that question is the paraphrase set — **0.649** — and it is reported separately
  and deliberately in
  [`reports/real_command_evidence.md`](../reports/real_command_evidence.md).
- **The coverage set is not a benchmark.** It scores 1.000, and it would be
  dishonest to quote that as accuracy: the generator's templates were written
  from the same capability list the set is drawn from. It measures coverage. The
  two are reported side by side precisely so the distinction cannot be lost, and
  `tests/test_intent_corpus.py` fails if a paraphrase ever leaks into training.
- **`document_intel` and `chitchat` are almost entirely generated**, because
  MASSIVE has essentially nothing for either. Their real-world accuracy is the
  least well evidenced of the seven.
- **MASSIVE is spoken, not typed.** Its utterances carry no file paths, no URLs
  and no punctuation-heavy syntax, so the two halves have genuinely different
  surface statistics. That is why the generated floor per class
  (`MIN_GENERATED_PER_CLASS = 800`) exists and is asserted by a test.

**A second real external dataset is also used**, though not for training:
`data/public_apis.json` (158 KB) is an index of ~780 public APIs derived from the
[public-api-lists](https://github.com/public-api-lists/public-api-lists)
repository, cached locally and searched with TF-IDF by `PublicApiAgent`.

---

## Evidence produced from this data

Generated into [`reports/`](../reports/) by the component modules:

| Artefact | From | Regenerate with |
|---|---|---|
| `intent_classifier_report.md` / `intent_classifier_comparison.csv` | 2.1 — five-model comparison on the held-out split | `py -3.12 -m ml.intent_classifier` |
| `real_command_evidence.md` / `real_command_accuracy.csv` | 2.1 — coverage and paraphrase sets on real commands | `py -3.12 -m reports.real_command_evidence` |
| `routing_accuracy.csv` / `routing_evidence.md` | End-to-end routing, 74/74 | `py -3.12 -m reports.routing_evidence` |
| `2_6_shap_equivalence.md` | 2.6 — exact Shapley values verified against `shap.LinearExplainer` | `py -3.12 -m ml.xai_explainer` |
| `figures/` | Confusion matrices, regression fits, cluster plots, rule tables | `py -3.12 -m reports.generate_all_evidence` |

> Until 2026-08-13 the first row pointed at a file last written on 2026-07-23 by
> a generator that no longer existed — it reported 0.9417 for a corpus that had
> since been replaced twice, and nothing in the repo would have rewritten it.
> `ml.intent_classifier.run()` now writes both artefacts, so the published
> comparison and the live corpus cannot drift apart again.
