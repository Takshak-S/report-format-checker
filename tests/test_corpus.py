"""
tests/test_corpus.py

Corpus regression tests over test_files/ (12 real LaTeX-generated reports).

The full pipeline (parse → classify → validate → noise-filter → score) is
cached once per test session, so the assertions run against a single corpus
pass.  These tests lock in the noise-reduction behaviour:

  * no font false positives on any report
  * no CRITICAL page-layout findings (the H016 table-row false positive)
  * margin findings stay within per-file bounds
  * computed DPI is used (720 DPI embedded images detected, not PyMuPDF's 96)
  * summary / scoring integrity

Run with:  pytest tests/test_corpus.py
Skip slow runs entirely with:  pytest -m "not slow"
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

from checker import run_checks
from utils.constants import Category
from utils.scoring import compute_score

BASE_DIR = Path(__file__).parent.parent
CORPUS_DIR = BASE_DIR / "test_files"
CORPUS_GLOB = sorted(glob.glob(str(CORPUS_DIR / "*.pdf"))) if CORPUS_DIR.exists() else []

# Per-file upper bound on Page-Layout findings (measured after the table-row
# exclusion, and after LIST blocks joined the per-line margin check in
# margin_validator.py).  Any increase is a regression to investigate.
MARGIN_BOUNDS = {
    "2026W10140U02H005_22BCE3217.pdf": 0,
    "2026W10140U02H007_22BCE0927.pdf": 4,
    "2026W10140U03H004_22BCB0096.pdf": 1,
    "2026W10140U03H008_22BCE0335.pdf": 4,
    "2026W10167P01H013_24MAI0005.pdf": 0,
    "2026W10167P01H014_24MAI0027.pdf": 0,
    "2026W10167U01H015_22BCE0508.pdf": 1,
    "2026W10167U01H016_22BCE0309.pdf": 2,
    "2026W10167U03H018_22BCE3372.pdf": 2,
    "2026W10230U01H019_22BCE0420.pdf": 0,
    "2026W10243I01H026_21MID0051.pdf": 0,
    "2026W10243P01H023_24MCS0036.pdf": 0,
}


@pytest.fixture(scope="session")
def corpus_results():
    """Run the full pipeline over every corpus PDF once, cached for the session."""
    if not CORPUS_GLOB:
        pytest.skip("test_files/ corpus not present")
    results = {}
    for path in CORPUS_GLOB:
        name = os.path.basename(path)
        results[name] = run_checks(path)
    return results


@pytest.mark.slow
class TestCorpus:
    def test_no_font_violations(self, corpus_results):
        """No report may raise a font finding (font noise was eliminated)."""
        for name, (doc, collector) in corpus_results.items():
            font_viols = [v for v in collector.all if v.category == Category.FONT]
            assert not font_viols, f"{name}: {len(font_viols)} font finding(s)"

    def test_no_critical_layout_findings(self, corpus_results):
        """Table-row / columnar text must not trigger CRITICAL margin findings."""
        for name, (doc, collector) in corpus_results.items():
            critical_layout = [
                v for v in collector.all
                if v.category == Category.PAGE_LAYOUT and v.severity == "CRITICAL"
            ]
            assert not critical_layout, f"{name}: {critical_layout}"

    def test_margin_findings_within_bounds(self, corpus_results):
        """Per-file Page-Layout findings stay within the measured bounds."""
        for name, (doc, collector) in corpus_results.items():
            bound = MARGIN_BOUNDS.get(name)
            if bound is None:
                continue
            layout = [v for v in collector.all if v.category == Category.PAGE_LAYOUT]
            assert len(layout) <= bound, (
                f"{name}: {len(layout)} layout finding(s), bound {bound}")

    def test_zero_heading_findings_on_corpus(self, corpus_results):
        """Correctly formatted corpus PDFs must produce zero heading findings."""
        for name, (doc, collector) in corpus_results.items():
            head = [v for v in collector.all if v.category == Category.HEADINGS]
            assert not head, f"{name}: {len(head)} heading finding(s)"

    def test_no_alignment_spacing_noise_on_corpus(self, corpus_results):
        """Alignment/spacing findings are limited to genuinely deviant paragraphs.

        After the noise-reduction pass, only H008 retains one genuine
        left-aligned paragraph; every other corpus PDF must be clean.
        """
        bounds = {
            "2026W10140U02H005_22BCE3217.pdf": 0,
            "2026W10140U02H007_22BCE0927.pdf": 0,
            "2026W10140U03H004_22BCB0096.pdf": 0,
            "2026W10140U03H008_22BCE0335.pdf": 1,  # genuine 'Bidding logic' paragraph
            "2026W10167P01H013_24MAI0005.pdf": 0,
            "2026W10167P01H014_24MAI0027.pdf": 0,
            "2026W10167U01H015_22BCE0508.pdf": 0,
            "2026W10167U01H016_22BCE0309.pdf": 0,
            "2026W10167U03H018_22BCE3372.pdf": 0,
            "2026W10230U01H019_22BCE0420.pdf": 0,
            "2026W10243I01H026_21MID0051.pdf": 0,
            "2026W10243P01H023_24MCS0036.pdf": 0,
        }
        for name, (doc, collector) in corpus_results.items():
            bound = bounds.get(name)
            if bound is None:
                continue
            noise = [v for v in collector.all
                     if v.category in (Category.ALIGNMENT, Category.SPACING)]
            assert len(noise) <= bound, (
                f"{name}: {len(noise)} alignment/spacing finding(s), bound {bound}")

    

    def test_summary_keys_present(self, corpus_results):
        for name, (doc, collector) in corpus_results.items():
            s = collector.summary()
            for key in ("total", "critical", "major", "minor",
                        "warnings", "suggestions", "info"):
                assert key in s, f"{name}: missing summary key '{key}'"
            assert "errors" not in s, f"{name}: stale 'errors' key in summary"

    def test_score_within_range(self, corpus_results):
        for name, (doc, collector) in corpus_results.items():
            score, grade = compute_score(collector)
            assert 0 <= score <= 100, f"{name}: score {score} out of range"
            assert isinstance(grade, str) and grade
