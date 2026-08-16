"""
tests/test_findings_model.py

Regression tests for the finding-model audit fixes:

  * Issue 1 — the Overall Format Score is a document-level summary metric, not
    a Violation.  It must never appear in by_category()/summary()/reporters,
    and compute_score() mathematics must be untouched.
  * Issue 2 — caption-numbering continuity findings carry real evidence:
    actual page, location snippet, previous/current caption context, bbox,
    classification signals, expected/detected, and a concrete reason.

Unit tests construct the DOM/collector directly (no test_files/ needed);
the corpus-level assertions are @pytest.mark.slow and skip when test_files/
is absent.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from checker import run_checks
from checks.caption_validator import CaptionInfo, CaptionValidator
from utils.constants import Category, Severity
from utils.error_model import Violation, ViolationCollector
from utils.scoring import compute_score, document_summary

BASE_DIR = Path(__file__).parent.parent
CORPUS_DIR = BASE_DIR / "test_files"
CORPUS_GLOB = sorted(glob.glob(str(CORPUS_DIR / "*.pdf"))) if CORPUS_DIR.exists() else []


# ── Issue 1: score is a summary metric, not a finding ─────────────────────
def _collector_with(violations):
    c = ViolationCollector()
    c.add_all(violations)
    return c


def test_compute_score_math_is_unchanged():
    c = _collector_with([
        Violation(category=Category.PAGE_LAYOUT, severity=Severity.CRITICAL,
                  page=3, description="margin"),
        Violation(category=Category.FONT, severity=Severity.WARNING,
                  page=4, description="font"),
    ])
    # 1.2 * 5 (critical page-layout) + 1.0 * 2 (warning font) = 8 → 92
    assert compute_score(c) == (92, "Excellent")


def test_overall_score_category_is_ignored_by_compute_score():
    c = _collector_with([
        Violation(category=Category.OVERALL_SCORE, severity=Severity.INFO,
                  page=-1, description="Overall format score: 100/100"),
        Violation(category=Category.CAPTIONS, severity=Severity.INFO,
                  page=5, description="Caption numbering gap: expected 4, found 7"),
    ])
    assert compute_score(c) == (100, "Excellent")


def test_score_is_not_a_finding():
    c = _collector_with([
        Violation(category=Category.CAPTIONS, severity=Severity.INFO,
                  page=59, description="Caption numbering gap: expected 4, found 7"),
    ])
    summary = c.summary()
    assert summary["total"] == 1
    assert summary["info"] == 1
    assert Category.OVERALL_SCORE not in c.by_category()
    assert all(v.category != Category.OVERALL_SCORE for v in c.all)


def test_document_summary_exposes_score():
    c = _collector_with([
        Violation(category=Category.PAGE_LAYOUT, severity=Severity.CRITICAL,
                  page=3, description="margin"),
    ])
    doc = document_summary(c)
    assert doc["score"] == 94          # 100 - 1.2*5
    assert doc["grade"] == "Excellent"
    assert doc["total"] == 1
    assert doc["critical"] == 1
    assert doc["info"] == 0


# ── Issue 2: caption continuity findings carry evidence ────────────────────
def _para(bbox=(100.0, 200.0, 500.0, 220.0),
          conf=0.9, reasons=("matches caption pattern",)):
    return SimpleNamespace(
        bbox=SimpleNamespace(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
        classification_confidence=conf,
        classification_reasons=list(reasons),
    )


def _cap(kind, text, num, page):
    return CaptionInfo(kind, text, num, page, _para())


def test_caption_gap_finding_has_evidence():
    captions = [
        _cap("table", "Table 3.1: Hardware Specification", 3, 35),
        _cap("table", "Table 3.2: Software Specification", 3, 36),
        _cap("table", "Table 7.1: Stratified 5-Fold Cross-Validation Results", 7, 59),
    ]
    violations = CaptionValidator()._check_continuity(captions)
    assert len(violations) == 1
    v = violations[0]

    assert v.category == Category.CAPTIONS
    assert v.severity == Severity.INFO
    assert v.page == 59
    assert v.description == "Caption numbering gap: expected 4, found 7"
    assert v.expected == "4"
    assert v.detected == "7"
    assert v.location == "Table 7.1: Stratified 5-Fold Cross-..."[:40] or \
        v.location.startswith("Table 7.1")
    assert "Table 3.2" in v.detail and "(p.36)" in v.detail
    assert "Table 7.1" in v.detail and "(p.59)" in v.detail
    assert v.reason is not None and "3 to 7" in v.reason
    assert v.suggested_fix is not None
    assert v.signals == ["matches caption pattern"]
    assert v.bbox == (100.0, 200.0, 500.0, 220.0)


def test_caption_continuity_no_gap():
    captions = [
        _cap("figure", "Figure 3.1: Architecture", 3, 10),
        _cap("figure", "Figure 4.1: Deployment", 4, 12),
        _cap("figure", "Figure 5.1: Testing", 5, 14),
    ]
    assert CaptionValidator()._check_continuity(captions) == []


def test_caption_duplicate_numbers_are_skipped():
    captions = [
        _cap("table", "Table 3.1: A", 3, 24),
        _cap("table", "Table 3.2: B", 3, 25),
        _cap("table", "Table 3.3: C", 3, 26),
        _cap("table", "Table 4.1: D", 4, 27),
    ]
    assert CaptionValidator()._check_continuity(captions) == []


def test_caption_without_number_is_ignored():
    captions = [
        _cap("table", "Table 3.1: A", 3, 24),
        _cap("table", "Table: Unnumbered", None, 25),
        _cap("table", "Table 7.1: D", 7, 27),
    ]
    violations = CaptionValidator()._check_continuity(captions)
    assert len(violations) == 1
    assert violations[0].page == 27


# ── Corpus-level assertions (require test_files/) ──────────────────────────
@pytest.mark.slow
@pytest.mark.skipif(not CORPUS_GLOB, reason="test_files/ corpus not present")
def test_corpus_overall_score_is_not_a_finding():
    for path in CORPUS_GLOB:
        _, collector = run_checks(path)
        assert Category.OVERALL_SCORE not in collector.by_category()
        summary = collector.summary()
        assert summary["total"] == sum(len(v) for v in collector.by_category().values())
        assert summary["total"] >= 0
        score, _ = compute_score(collector)
        assert 0 <= score <= 100


@pytest.mark.slow
@pytest.mark.skipif(not CORPUS_GLOB, reason="test_files/ corpus not present")
def test_corpus_caption_gap_findings_carry_evidence():
    for path in CORPUS_GLOB:
        _, collector = run_checks(path)
        for v in collector.all:
            if (v.category == Category.CAPTIONS
                    and v.description.startswith("Caption numbering gap")):
                assert v.page > 0, f"{os.path.basename(path)}: gap on doc-level"
                assert v.location, f"{os.path.basename(path)}: missing location"
                assert v.detail, f"{os.path.basename(path)}: missing prev/current context"
                assert v.expected and v.detected
                assert v.reason
