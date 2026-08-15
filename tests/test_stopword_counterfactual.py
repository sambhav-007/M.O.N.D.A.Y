"""
The stopword study must stay a study.

`reports/2_1_stopword_counterfactual.md` reports what would happen if component
2.1's vectoriser were given `stop_words="english"`: the explanation gets a great
deal cleaner (71% → 0% function words among the top attributions) at no cost to
the generalisation figure. That is a tempting enough result that someone will
eventually apply it.

They should not do it by accident. Adopting it moves the published macro-F1, the
confusion matrix, `reports/2_1_classification_report.csv`, the five-model
comparison, and the 2.6 attributions — every number derived from the shipped
model. `handoff.md` §6 records the decision to report the delta and leave the
model alone, and this makes that decision enforced rather than remembered.

Adopting it deliberately means changing `PRODUCTION_TFIDF`, regenerating every
2.1 and 2.6 artefact, and deleting this test with the commit that does so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "2_1_stopword_counterfactual.md"
CSV = ROOT / "reports" / "2_1_stopword_counterfactual.csv"


def test_the_shipped_vectoriser_still_has_no_stopword_filter():
    """The counterfactual is a counterfactual only while this holds."""
    from ml.intent_classifier import PRODUCTION_TFIDF

    assert "stop_words" not in PRODUCTION_TFIDF, (
        "PRODUCTION_TFIDF now sets stop_words, which makes "
        "reports/2_1_stopword_counterfactual.md a description of the shipped "
        "model rather than of an alternative to it. If that was deliberate, "
        "regenerate every 2.1 and 2.6 artefact and remove this test."
    )


def test_the_study_reads_the_production_config_rather_than_restating_it():
    """A study that hardcodes its own copy stops describing what it claims to.

    `reports/intent_classifier_comparison.csv` went stale for three weeks
    because nothing connected it to the code it described. The import is what
    connects this one.
    """
    source = (ROOT / "reports" / "stopword_counterfactual.py").read_text(encoding="utf-8")
    assert "from ml.intent_classifier import PRODUCTION_TFIDF" in source, (
        "the counterfactual must import the production vectoriser config, not "
        "restate it — otherwise it can drift into describing a model that is "
        "not the shipped one"
    )


def test_the_study_uses_the_same_shap_estimator_as_component_2_6():
    """Otherwise the comparison with the published attributions is not one."""
    source = (ROOT / "reports" / "stopword_counterfactual.py").read_text(encoding="utf-8")
    assert "from ml.xai_explainer import exact_linear_shap_values" in source


@pytest.mark.parametrize("artefact", [REPORT, CSV])
def test_the_artefacts_exist(artefact):
    assert artefact.exists(), (
        f"{artefact.name} is cited by reports/EVIDENCE_INDEX.md. Regenerate "
        f"with: py -3.12 -m reports.stopword_counterfactual"
    )


def test_the_report_records_both_rankings():
    """Coefficients and mean |SHAP| disagree here, and the report must say so.

    Ranking on coefficients alone makes the shipped model look healthy — its top
    `browser` coefficients are `news`, `weather`, `research` — and would have
    made the study appear to contradict the 2.6 finding. The stopwords are at
    the top of the *attribution* ranking. A version of this report that dropped
    one of the two tables would read as a refutation of the finding it was
    written to examine.
    """
    text = REPORT.read_text(encoding="utf-8")
    assert "Mean |SHAP|" in text
    assert "Coefficient" in text
    assert "shipped model is unchanged" in text
