# Component 2.1 — the stopword counterfactual

The XAI layer (2.6) found that the top attributions for the `browser`
class are `on`, `my`, `me`, `for`, `to`: the shipped classifier leans on
function words. `build_pipelines()` sets no `stop_words`, so English
stopwords are in the vocabulary and are carrying signal.

**The shipped model is not changed by this study.** Adopting the variant
would move the published macro-F1, the confusion matrix and the
five-model comparison. This reports the delta instead, which is the
decision recorded in `handoff.md` §6.

## 1. Held-out performance

| Variant | macro-F1 | Vocabulary |
|---|---|---|
| shipped (no `stop_words`) | **0.9101** | 8,000 |
| `stop_words="english"` | 0.8945 | 8,000 |
| **delta** | **-0.0157** | +0 |

## 2. Real commands and unseen paraphrases

The held-out slice measures how well a model learned the corpus. These
two sets measure something else, and the distinction has already caught
this project once: the corpus was rebuilt because a 0.929 held-out
macro-F1 sat beside **0.657** on the app's own commands.

*Coverage* is the app's own commands, drawn from the same capability list
the generator's templates were written from — so the overlap is by
construction and a high score there is a coverage check, not accuracy.
*Paraphrase* is the generalisation number: written after the corpus was
built and deliberately never fed back into the generator.

| Variant | coverage acc | coverage conf | paraphrase acc | paraphrase conf |
|---|---|---|---|---|
| shipped | 1.000 | 0.813 | 0.703 | 0.547 |
| stopwords_removed | 0.970 | 0.801 | 0.703 | 0.627 |

Paraphrase delta: **+0.000**

## 3. Attributions

The reason the study exists. A metric that barely moves and an
explanation that gets cleaner are different claims, and only the second
is what the 2.6 finding was about.

### Two rankings, and the difference between them matters

**Mean |SHAP|** is `|β·(x − E[x])|` averaged over real commands: what
actually carries the decision in practice. **Coefficient** is `β`: how
far one unit of a feature moves the log-odds — what is decisive *when it
appears*. They disagree here, and the disagreement is the finding.

A content word like `news` has a large coefficient and appears in a
handful of commands. A function word like `you` has a modest coefficient
and appears in a great many. Ranking on coefficients alone makes the
shipped model look perfectly healthy — its top `browser` coefficients are
`news`, `weather`, `research` — and would have made this study appear to
contradict the 2.6 finding. The stopwords sit at the top of the
*attribution* ranking, which is the one that describes what the model does
to real input, and the one `reports/2_6_xai_intent_top_features.csv`
publishes.

Bigrams count as function words only when **every** token is one: `on my`
carries no more meaning than `on`, but `search for` does — the content
word is the signal.

### `browser`

**Mean |SHAP| — what carries the decision**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `my` | 0.154464 | `list` | 0.100149 |
| 2 | `you` | 0.10054 | `weather` | 0.073072 |
| 3 | `please` | 0.082991 | `news` | 0.070903 |
| 4 | `is` | 0.066176 | `time` | 0.056174 |
| 5 | `what` | 0.062797 | `sec` | 0.046956 |
| 6 | `weather` | 0.062456 | `thanks` | 0.042173 |
| 7 | `news` | 0.057138 | `meeting` | 0.042029 |
| 8 | `in` | 0.055903 | `want` | 0.040172 |

Function words in the top 8: **75%** shipped → **0%** with stopwords removed.

**Coefficient — what is decisive when present**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `news` | 5.4972 | `news` | 5.3353 |
| 2 | `weather` | 3.2803 | `research` | 3.5285 |
| 3 | `research` | 3.2571 | `search` | 3.4721 |
| 4 | `search` | 3.0572 | `stock` | 3.0734 |
| 5 | `stock` | 2.8597 | `google` | 2.9637 |
| 6 | `com` | 2.8388 | `web` | 2.9132 |
| 7 | `price` | 2.6527 | `price` | 2.8073 |
| 8 | `where` | 2.5235 | `weather` | 2.7543 |

Function words in the top 8: **12%** shipped → **0%** with stopwords removed.

### `document_intel`

**Mean |SHAP| — what carries the decision**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `the` | 0.125835 | `pdf` | 0.118707 |
| 2 | `pdf` | 0.092595 | `summarize` | 0.050467 |
| 3 | `is` | 0.082655 | `today` | 0.043933 |
| 4 | `in` | 0.061647 | `minutes` | 0.037397 |
| 5 | `please` | 0.050196 | `syllabus` | 0.036476 |
| 6 | `for me` | 0.041851 | `invoice` | 0.033204 |
| 7 | `summarize` | 0.040543 | `summarise` | 0.032115 |
| 8 | `my` | 0.039734 | `summary` | 0.02942 |

Function words in the top 8: **75%** shipped → **0%** with stopwords removed.

**Coefficient — what is decisive when present**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `pdf` | 4.7491 | `pdf` | 5.1334 |
| 2 | `summarize` | 4.2217 | `summarize` | 4.4468 |
| 3 | `summarise` | 3.6369 | `conclusion` | 4.274 |
| 4 | `read` | 3.3457 | `summary` | 4.2113 |
| 5 | `txt` | 3.2507 | `total` | 3.8613 |
| 6 | `minutes` | 2.7375 | `summarise` | 3.5106 |
| 7 | `resume` | 2.6488 | `whitepaper` | 3.3667 |
| 8 | `report` | 2.6396 | `minutes` | 3.3086 |

Function words in the top 8: **0%** shipped → **0%** with stopwords removed.

### `chitchat`

**Mean |SHAP| — what carries the decision**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `you` | 0.150107 | `weather` | 0.128055 |
| 2 | `please` | 0.100111 | `hi` | 0.109227 |
| 3 | `hi` | 0.085025 | `list` | 0.105255 |
| 4 | `the` | 0.074919 | `thanks` | 0.094392 |
| 5 | `hello` | 0.06807 | `need` | 0.087557 |
| 6 | `thanks` | 0.067281 | `hello` | 0.080788 |
| 7 | `in` | 0.060779 | `quick` | 0.077381 |
| 8 | `my` | 0.057092 | `sec` | 0.076369 |

Function words in the top 8: **62%** shipped → **0%** with stopwords removed.

**Coefficient — what is decisive when present**

| Rank | shipped | | `stop_words="english"` | |
|---|---|---|---|---|
| 1 | `hi` | 6.3773 | `hi` | 6.7157 |
| 2 | `joke` | 6.1962 | `joke` | 5.4414 |
| 3 | `hello` | 4.5287 | `weather` | 4.8267 |
| 4 | `good` | 3.5666 | `ai` | 4.0599 |
| 5 | `jokes` | 3.5103 | `hello` | 4.0501 |
| 6 | `how is` | 3.2932 | `good` | 3.6165 |
| 7 | `you` | 3.2914 | `jokes` | 3.3098 |
| 8 | `hi the` | 3.0915 | `want` | 2.8927 |

Function words in the top 8: **25%** shipped → **0%** with stopwords removed.

## 4. Reading this

Two questions, answered separately, because they can disagree:

- **Would it cost accuracy?** Held-out macro-F1 moves -0.0157; the
  paraphrase set is the honest generalisation figure and moves
  +0.000.
- **Would it buy a better explanation?** The mean |SHAP| tables above.
  If the function words are simply replaced by *other* function words,
  or by corpus artefacts, the 2.6 finding is about the corpus rather than
  about the vectoriser configuration — and removing stopwords would be a
  cosmetic change to the explanation rather than a real one.

There is a third question this study cannot answer, and it is worth
naming rather than leaving implied: *why* function words carry so much
attribution. The likeliest reason is the corpus rather than the model —
the generated half is built from templates with fixed politeness prefixes
and suffixes (`please`, `asap`, `thanks`, `for me`), so a class's
characteristic filler is genuinely predictive **of the generator**.
Amazon MASSIVE, the real half, has no such regularity. Testing that would
mean measuring attribution separately on the generated and real rows,
which is a larger study than this one.

Whatever the numbers say, the shipped model is unchanged. This is
evidence for the report, not a migration plan.

## 5. Verdict

- Held-out macro-F1: **-0.0157**
- Paraphrase accuracy (the generalisation figure): **+0.000**
- Coverage accuracy: **-0.030**
- Function words among the top-8 attributions, averaged over the three classes examined: **71%** → **0%**

The explanation improves a great deal and the generalisation figure does
not move. That is a stronger result than the held-out delta alone
suggests, and it points at the corpus: if the function words were
carrying real signal about user intent, removing them would cost
something on unseen phrasings. It costs nothing there, and costs a little
on the two sets that share vocabulary with the generator — which is what
you would expect if what the stopwords predict is the template, not the
intent.

It remains a counterfactual. Adopting it would move every published 2.1
number, and the decision recorded in `handoff.md` §6 is to report the
delta and leave the shipped model alone. This is that report; the
recommendation for anyone continuing the work is that the corpus is the
thing to change, not the vectoriser.

_Generated by `py -3.12 -m reports.stopword_counterfactual`._
