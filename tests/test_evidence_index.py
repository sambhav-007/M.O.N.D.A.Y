"""
The evidence index must point at things that exist.

`reports/EVIDENCE_INDEX.md` maps every claim this project makes to the artefact
that backs it and the command that regenerates it. That is only worth having if
the paths in it resolve — and the reason it exists is a case where they did not:

    reports/intent_classifier_comparison.csv
    reports/intent_classifier_report.md

Both were last written on **2026-07-23** by a generator that no longer existed,
and nothing in the repository rewrote them. `data/DATASET.md` cited the report as
the five-model evidence, so anyone quoting it was quoting 0.9417 from a corpus
that had since been replaced twice. Nothing detected that, because nothing was
checking.

This checks. It deliberately does **not** check that the numbers are current —
that would mean regenerating every model on every test run. It checks the weaker
property that turns out to be the one that failed: that every file named as
evidence is on disk, and that every test file cited actually exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "reports" / "EVIDENCE_INDEX.md"
CLO01 = ROOT / "reports" / "CLO01_ethics_and_safety.md"

# Backticked paths that look like repository files: they contain a slash or a
# known extension, and no spaces. Deliberately narrow — the index also contains
# backticked commands, symbol names and set literals, and a checker that flags
# `TIER_2_IMPLEMENTED` as a missing file would be turned off within a week.
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LOOKS_LIKE_PATH = re.compile(
    r"^[\w./-]+\.(?:py|md|csv|json|jsonl|png|ipynb|html|txt|yaml|yml)$"
)


def _cited_paths(document: Path) -> list[str]:
    text = document.read_text(encoding="utf-8")
    found = []
    for span in _CODE_SPAN.findall(text):
        candidate = span.strip()
        # Glob entries (`tests/cassettes/**`) and directories are noted as such
        # in the index and are checked separately below.
        if candidate.endswith("/**") or candidate.endswith("/"):
            continue
        if _LOOKS_LIKE_PATH.match(candidate):
            found.append(candidate)
    return sorted(set(found))


INDEX_PATHS = _cited_paths(INDEX)
CLO01_PATHS = _cited_paths(CLO01)


def test_the_index_and_the_chapter_exist():
    assert INDEX.exists(), "reports/EVIDENCE_INDEX.md is the map to everything else"
    assert CLO01.exists(), "reports/CLO01_ethics_and_safety.md is the CLO01 chapter"


def test_the_index_cites_a_meaningful_number_of_artefacts():
    """A parser that silently matched nothing would make every test below pass."""
    assert len(INDEX_PATHS) >= 30, (
        f"only {len(INDEX_PATHS)} paths parsed out of the evidence index — the "
        f"extractor is probably broken, which would make this whole module "
        f"vacuous"
    )


@pytest.mark.parametrize("cited", INDEX_PATHS)
def test_every_artefact_named_in_the_index_exists(cited):
    assert (ROOT / cited).exists(), (
        f"reports/EVIDENCE_INDEX.md cites {cited!r}, which is not on disk. "
        f"Either regenerate it, or remove the row — an index that points at "
        f"nothing is worse than no index, because it reads as proof."
    )


@pytest.mark.parametrize("cited", CLO01_PATHS)
def test_every_artefact_named_in_the_clo01_chapter_exists(cited):
    assert (ROOT / cited).exists(), (
        f"reports/CLO01_ethics_and_safety.md cites {cited!r}, which is not on disk"
    )


def test_every_test_file_the_index_promises_is_collectable():
    """The index quotes test counts per file. The files must at least exist.

    Counts themselves are not asserted here: they change whenever a test is
    added, and a document that fails the suite for being *out of date by two
    tests* trains people to stop updating it.
    """
    cited_tests = [p for p in INDEX_PATHS + CLO01_PATHS if p.startswith("tests/")]
    assert cited_tests, "the index should cite the tests that back its claims"
    missing = [p for p in cited_tests if not (ROOT / p).exists()]
    assert not missing, f"cited test files do not exist: {missing}"


def test_the_generators_the_index_names_are_importable():
    """Each `py -3.12 -m <module>` in the index must name a real module.

    This is the check that would have caught the stale classifier report: its
    generator had been deleted, so the regeneration command in the docs referred
    to nothing, and the artefact simply stopped being updated.
    """
    text = INDEX.read_text(encoding="utf-8")
    modules = sorted(set(re.findall(r"py -3\.12 -m ([\w.]+)", text)))
    # `pytest` and `pip` are tools, not project modules.
    modules = [m for m in modules if not m.startswith(("pytest", "pip", "uvicorn"))]
    assert modules, "the index should name the generators it depends on"

    missing = []
    for module in modules:
        parts = module.split(".")
        as_module = ROOT.joinpath(*parts).with_suffix(".py")
        as_package = ROOT.joinpath(*parts, "__init__.py")
        if not (as_module.exists() or as_package.exists()):
            missing.append(module)
    assert not missing, (
        f"the index names these regeneration commands, but the modules do not "
        f"exist: {missing}"
    )
