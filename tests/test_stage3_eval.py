"""
The stage-3 eval key must name skills that exist.

`reports/stage3_selection.py` scores the model by comparing the skill it picked
against a set of acceptable ones per MASSIVE intent. A typo in that key does not
fail loudly — it scores every answer for that intent as **wrong**, and the
report then blames the model for the benchmark's mistake. Phase 8 exists to make
model choice a measurement rather than a coin toss, so the measurement needs a
guard of its own.

Nothing here runs a model. It checks the key against the live registry.
"""

from __future__ import annotations

import pytest

from core.planner import MasterPlanner
from reports.stage3_selection import ACCEPTABLE, PER_INTENT, SEED


@pytest.fixture(scope="module")
def registry():
    planner = MasterPlanner()
    planner.enable_voice = False
    return planner.router.registry


def test_every_acceptable_skill_exists(registry):
    known = {s.name for s in registry.skills}
    for massive_intent, accepted in ACCEPTABLE.items():
        unknown = accepted - known
        assert not unknown, f"{massive_intent} accepts skills that do not exist: {unknown}"


def test_every_acceptable_skill_is_reachable_by_the_model(registry):
    """A key naming a skill stage 3 is not offered is unscoreable by construction.

    Tier-2 skills are excluded from `llm_reachable_skills()` on purpose, and a
    benchmark that expected one would be asking the model to do the thing the
    containment rules forbid.
    """
    reachable = {s.name for s in registry.llm_reachable_skills()}
    for massive_intent, accepted in ACCEPTABLE.items():
        unreachable = accepted - reachable
        assert not unreachable, (
            f"{massive_intent} expects {unreachable}, which stage 3 is never offered"
        )


def test_no_intent_accepts_everything():
    """An entry that accepts half the registry scores nothing.

    Four was chosen because `qa_currency` and `recommendation_*` genuinely have
    three defensible answers, and a fifth would mean the intent is too vague to
    key at all — in which case it belongs out of the set, not loosened into it.
    """
    for massive_intent, accepted in ACCEPTABLE.items():
        assert 1 <= len(accepted) <= 4, (
            f"{massive_intent} accepts {len(accepted)} skills; key it tighter or drop it"
        )


def test_the_sample_is_deterministic():
    """Two models must be asked the same questions, or the comparison is noise."""
    assert isinstance(SEED, int)
    assert PER_INTENT >= 3


def test_the_two_price_lookups_are_not_both_acceptable_for_one_intent():
    """`crypto_price` and `stock_price` were the eval's clearest finding: the 3B
    sent five of six share questions to the crypto tool. Accepting either would
    have hidden that."""
    for massive_intent, accepted in ACCEPTABLE.items():
        assert not {"crypto_price", "stock_price"} <= accepted, (
            f"{massive_intent} accepts both price lookups, so it cannot detect the confusion"
        )
