"""The intent corpus — provenance, coverage, and the two evaluation sets.

Component 2.1 published a 0.929 macro-F1 on a held-out slice of the corpus it
trained on. Measured on 2026-08-13 against the commands the app itself
advertises, the same model scored **0.657**, and **0.486** on paraphrases of
them. The corpus was 9,996 rows built from 117 sentence skeletons over a
924-word vocabulary, and capabilities the app ships in `/help` — battery, my ip,
kill, recall, bitcoin price, iss location, proactive — appeared in none of them.

The corpus is now half real (Amazon MASSIVE en-US, mapped by `datagen/massive.py`)
and half generated, and these tests hold the parts of that arrangement that are
easy to break silently.
"""

from __future__ import annotations

import pandas as pd
import pytest

from datagen.commands import MIN_GENERATED_PER_CLASS, TEMPLATES, build_corpus
from datagen.massive import MASSIVE_DROPPED, MASSIVE_TO_MONDAY, OUT_CSV, load_massive
from ml.intent_classifier import INTENT_CLASSES, SAMPLES_PER_CLASS
from reports.real_command_evidence import COVERAGE_SET, PARAPHRASE_SET


# ── The mapping ──────────────────────────────────────────────────────────────
def test_every_massive_intent_is_mapped_or_refused():
    """
    MASSIVE has 60 intents. Each is either mapped onto one of MONDAY's 7 or
    listed in `MASSIVE_DROPPED` with a reason. A future MASSIVE release adding
    an intent should fail here rather than be silently ignored — an unmapped
    intent is data quietly thrown away.
    """
    massive = load_massive()
    if massive is None:
        pytest.skip("data/external/massive_en_us.csv not derived on this clone")

    decided = set(MASSIVE_TO_MONDAY) | set(MASSIVE_DROPPED)
    assert len(decided) == 60, f"expected all 60 MASSIVE intents, decided on {len(decided)}"
    assert not (set(MASSIVE_TO_MONDAY) & set(MASSIVE_DROPPED)), \
        "an intent cannot be both mapped and dropped"


def test_the_mapping_only_targets_real_monday_intents():
    """A mapping to a class that does not exist would drop rows at load time."""
    targets = set(MASSIVE_TO_MONDAY.values())
    unknown = targets - set(TEMPLATES)
    assert not unknown, f"mapped to non-existent intents: {sorted(unknown)}"


def test_dropped_intents_carry_a_reason():
    for intent, reason in MASSIVE_DROPPED.items():
        assert reason.strip(), f"{intent} is dropped with no reason given"


def test_document_intel_has_no_real_data_and_that_is_recorded():
    """
    MASSIVE is a voice-assistant corpus; nobody dictates "summarise chapter 3 of
    the PDF" to a smart speaker. `document_intel` is therefore entirely
    generated, which is fine — but it must not be discovered by surprise later.
    """
    assert "document_intel" not in set(MASSIVE_TO_MONDAY.values())


# ── The corpus ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def corpus():
    return build_corpus()


def test_every_class_keeps_its_generated_floor(corpus):
    """
    The regression this floor exists for. The first version topped up with
    generation only where MASSIVE fell short — so MASSIVE filled `browser` and
    `communication` outright, those classes got 88 and 98 generated rows, and
    **every MONDAY-specific template for them was absent**. `search web for
    youtube` scored 0.29 and `whatsapp +919876543210` was misclassified at 0.26.

    MASSIVE has no bare URLs, no `subject "…" body "…"`, no WhatsApp and no
    `iss location`. Those phrasings exist only because the generator writes
    them, so the floor is coverage, not padding.
    """
    generated = corpus[corpus["source"] == "generated"]
    counts = generated.groupby("intent").size()
    for intent in TEMPLATES:
        assert counts.get(intent, 0) >= MIN_GENERATED_PER_CLASS * 0.9, (
            f"{intent} has only {counts.get(intent, 0)} generated rows; the "
            f"app's own phrasings for it are under-represented"
        )


def test_the_corpus_carries_its_provenance(corpus):
    assert set(corpus["source"].unique()) <= {"massive", "generated"}
    assert (corpus["source"] == "massive").sum() > 0, \
        "no real rows — was data/external/massive_en_us.csv derived?"


def test_the_corpus_is_deterministic():
    """`seed=42` must still reproduce the file, or a metric cannot be traced."""
    a = build_corpus(per_class=300, seed=42)
    b = build_corpus(per_class=300, seed=42)
    pd.testing.assert_frame_equal(a, b)


def test_no_duplicate_commands(corpus):
    assert corpus["text"].duplicated().sum() == 0


def test_classes_stay_balanced(corpus):
    counts = corpus.groupby("intent").size()
    assert counts.min() / counts.max() > 0.9, \
        f"class balance drifted: {counts.to_dict()}"


def test_the_training_cap_admits_the_whole_corpus():
    """
    `build_synthetic_dataset` capped at **500 rows per class**, so a 9,996-row
    corpus was fitted on 2,800 rows — 72% discarded. Growing the dataset does
    nothing until this number moves, which is why it is named and asserted
    rather than left as a default in three call sites.
    """
    assert SAMPLES_PER_CLASS >= 2500


# ── The evaluation sets ──────────────────────────────────────────────────────
def test_evaluation_sets_use_real_intent_labels():
    for name, pairs in (("coverage", COVERAGE_SET), ("paraphrase", PARAPHRASE_SET)):
        for command, intent in pairs:
            assert intent in INTENT_CLASSES, \
                f"{name}: {command!r} labelled with unknown intent {intent!r}"


def test_the_paraphrase_set_is_not_in_the_corpus(corpus):
    """
    The paraphrase set only measures generalisation for as long as none of its
    wordings are trained on. This is the mechanical version of the comment in
    `reports/real_command_evidence.py` telling you not to add templates for
    them — a well-meaning "let's cover these too" would otherwise turn the
    generalisation number into a second coverage check, silently.
    """
    corpus_texts = {t.lower().strip(" .!?") for t in corpus["text"].astype(str)}
    leaked = [c for c, _ in PARAPHRASE_SET if c.lower().strip(" .!?") in corpus_texts]
    assert not leaked, (
        f"paraphrase commands leaked into the training corpus: {leaked}. "
        f"Remove the template, or retire these from the paraphrase set."
    )


def test_the_two_sets_do_not_overlap():
    coverage = {c.lower() for c, _ in COVERAGE_SET}
    paraphrase = {c.lower() for c, _ in PARAPHRASE_SET}
    assert not (coverage & paraphrase)


# ── What the classifier does with them ───────────────────────────────────────
@pytest.fixture(scope="module")
def classifier():
    from ml.intent_classifier import get_trained_classifier

    return get_trained_classifier()


def _score(clf, pairs):
    from ml.intent_classifier import predict_intent

    ok = sum(predict_intent(clf, cmd)[0] == truth for cmd, truth in pairs)
    return ok / len(pairs)


def test_the_app_can_classify_its_own_advertised_commands(classifier):
    """
    Coverage, not generalisation — the templates were written from the same
    capability list, so this asserts the corpus covers what the app ships.
    Baseline before the corpus was rebuilt: 0.657.
    """
    assert _score(classifier, COVERAGE_SET) >= 0.95


def test_paraphrases_of_those_commands_still_land(classifier):
    """
    The number that means something. Measured 0.486 on the old corpus and 0.703
    on this one; the floor is set below the measurement so ordinary variation
    does not fail the suite, but a real regression will.

    If this falls while the coverage test above still passes, the corpus is
    being fitted to its own checklist.
    """
    assert _score(classifier, PARAPHRASE_SET) >= 0.62
