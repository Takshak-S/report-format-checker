"""
utils/scoring.py

Computes an overall format quality score from collected violations.
"""
from __future__ import annotations

from utils.constants import Severity, Category
from utils.error_model import ViolationCollector

ERROR_PENALTY   = 5
WARNING_PENALTY = 2

CATEGORY_WEIGHTS = {
    Category.PAGE_LAYOUT: 1.2,
    Category.FONT:        1.0,
    Category.HEADINGS:    1.0,
    Category.CITATIONS:   1.3,
    Category.CHAPTERS:    1.5,
    Category.IMAGES:      1.1,
    Category.CAPTIONS:    1.0,
    Category.GRAMMAR:     0.8,
    Category.PLAGIARISM:  2.0,
}


def compute_score(collector: ViolationCollector) -> tuple[int, str]:
    """
    Return (score 0-100, grade label).
    Score starts at 100 and deducts weighted penalties per violation.
    """
    penalty = 0.0

    for v in collector.all:
        if v.category in (Category.RESEARCH, Category.OVERALL_SCORE):
            continue

        weight = CATEGORY_WEIGHTS.get(v.category, 1.0)
        if v.severity == Severity.CRITICAL:
            penalty += ERROR_PENALTY * weight
        elif v.severity == Severity.WARNING:
            penalty += WARNING_PENALTY * weight

    score = max(0, min(100, round(100 - penalty)))

    if score >= 90:
        grade = "Excellent"
    elif score >= 75:
        grade = "Good"
    elif score >= 60:
        grade = "Fair"
    elif score >= 40:
        grade = "Needs Improvement"
    else:
        grade = "Poor"

    return score, grade


def document_summary(collector: ViolationCollector) -> dict:
    """
    Return the document-level summary: the overall format score alongside the
    raw finding counts.  The score is a summary metric (never a Violation), so
    it is exposed here for the UI and tests.
    """
    score, grade = compute_score(collector)
    summary = collector.summary()
    summary["score"] = score
    summary["grade"] = grade
    return summary
