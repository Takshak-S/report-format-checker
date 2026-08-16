"""
utils/noise_filter.py

Post-processing pass that suppresses false positives and redundant findings
before reporting:

  1. Confidence gate      — drop / demote findings from low-confidence blocks.
  2. Deduplication        — collapse repeated identical findings (same rule,
                            same page) into a single finding with a count.
  3. Consistency reclass  — if the same rule fires on a majority of content
                            pages it is a systemic issue: collapse into one
                            document-level finding instead of N page findings.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List

from nlp.dom import DocumentModel
from utils.error_model import Violation, ViolationCollector

_LOW_CONFIDENCE_DROP = 0.40
_LOW_CONFIDENCE_DEMOTE = 0.60
_SYSTEMIC_PAGE_FRACTION = 0.5
_MIN_PAGES_FOR_SYSTEMIC = 2

_SEVERITY_RANK = {
    "CRITICAL": 0, "MAJOR": 1, "MINOR": 2, "WARNING": 3,
    "SUGGESTION": 4, "INFO": 5,
}


def _demote(severity: str) -> str:
    order = ["CRITICAL", "MAJOR", "MINOR", "WARNING", "SUGGESTION", "INFO"]
    idx = order.index(severity) if severity in order else -1
    return order[idx + 1] if 0 <= idx < len(order) - 1 else severity


def _worst(violations: List[Violation]) -> Violation:
    return min(violations, key=lambda v: _SEVERITY_RANK.get(v.severity, 9))


def apply_noise_filter(collector: ViolationCollector, doc: DocumentModel) -> ViolationCollector:
    """Return a new collector with noise-reduced findings."""
    result = ViolationCollector()

    # Content pages = pages carrying any paragraph or image.
    content_pages = set()
    for page in doc.pages:
        if page.get_paragraphs() or page.get_images():
            content_pages.add(page.page_num)

    # ── Step 1: confidence gate ────────────────────────────────────────────
    kept: List[Violation] = []
    for v in collector.all:
        if v.page > 0 and 0.0 < v.confidence < _LOW_CONFIDENCE_DROP:
            continue
        v = _clone_with_severity(v, _demote(v.severity)) if (
            v.page > 0 and _LOW_CONFIDENCE_DROP <= v.confidence < _LOW_CONFIDENCE_DEMOTE
        ) else v
        kept.append(v)

    # ── Step 2: dedup identical (category, description, page) ──────────────
    by_key: dict[tuple, List[Violation]] = defaultdict(list)
    for v in kept:
        key = (v.category, v.description, v.page)
        by_key[key].append(v)

    deduped: List[Violation] = []
    for group in by_key.values():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            representative = _worst(group)
            representative = _clone_with_count(representative, len(group))
            deduped.append(representative)

    # ── Step 3: systemic collapse ──────────────────────────────────────────
    # Group by rule (ignoring page); if the rule hits a majority of content
    # pages, it is systemic → one document-level finding.
    if content_pages:
        by_rule: dict[tuple, List[Violation]] = defaultdict(list)
        for v in deduped:
            if v.page > 0:
                by_rule[(v.category, v.description)].append(v)

        collapsed_ids = set()
        for rule, group in by_rule.items():
            distinct_pages = {v.page for v in group}
            if (len(distinct_pages) >= _MIN_PAGES_FOR_SYSTEMIC
                    and len(distinct_pages) / len(content_pages) >= _SYSTEMIC_PAGE_FRACTION):
                representative = _worst(group)
                collapsed = Violation(
                    category=representative.category,
                    severity=representative.severity,
                    page=-1,
                    description=representative.description,
                    detail=(representative.detail or "") + _count_suffix(len(group)),
                    expected=representative.expected,
                    detected=representative.detected,
                    confidence=representative.confidence,
                    signals=representative.signals,
                    reason=representative.reason,
                    suggested_fix=representative.suggested_fix,
                    location=None,
                    bbox=None,
                )
                result.add(collapsed)
                collapsed_ids.update(id(v) for v in group)

        for v in deduped:
            if id(v) not in collapsed_ids:
                result.add(v)
        return result

    for v in deduped:
        result.add(v)
    return result


def _clone_with_count(v: Violation, count: int) -> Violation:
    v.detail = ((v.detail + " | ") if v.detail else "") + f"{count} instance(s) on this page"
    return v


def _clone_with_severity(v: Violation, severity: str) -> Violation:
    v.severity = severity
    return v


def _count_suffix(count: int) -> str:
    return f" | {count} finding(s) across the document"
