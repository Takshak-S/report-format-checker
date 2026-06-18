"""
checks/spacing_checks.py

Checks:
  1. Line spacing (1.5×)
  2. Paragraph alignment (justified) — inferred from right-edge variance
"""
from __future__ import annotations

import statistics
from ingestion.pdf_loader import ParsedDocument, LineInfo
from utils.constants import (
    LINE_SPACING_FACTOR, LINE_SPACING_TOLERANCE,
    JUSTIFICATION_TOLERANCE_PT,
    MARGIN_LEFT_PT, MARGIN_RIGHT_PT,
    Severity, Category,
)
from utils.error_model import Violation


# ── Line spacing ──────────────────────────────────────────────────────────────

def _expected_spacing(line_height: float) -> float:
    """Expected gap between lines = line_height × 1.5."""
    return line_height * LINE_SPACING_FACTOR


def check_line_spacing(doc: ParsedDocument) -> list[Violation]:
    violations = []

    for page_num in range(1, doc.page_count + 1):
        lines = doc.lines_on_page(page_num)
        if len(lines) < 2:
            continue

        # Filter out heading lines and captions for spacing check (they may differ)
        body_lines = [l for l in lines if l.size and 11.0 <= l.size <= 13.0]
        if len(body_lines) < 3:
            continue

        # Compute gaps between consecutive body lines
        gaps = []
        for i in range(1, len(body_lines)):
            prev = body_lines[i - 1]
            curr = body_lines[i]
            gap = curr.top - prev.bottom
            if 0 < gap < 80:   # ignore large gaps (paragraph breaks, figures)
                gaps.append((gap, prev, curr))

        if not gaps:
            continue

        # Expected gap for 12pt text at 1.5× spacing ≈ 6–8 pts inter-line gap
        # (line height ≈ 14 pts, spacing = 14 × 1.5 = 21 pts, gap = 21 - 14 = 7 pts)
        avg_gap = statistics.median([g[0] for g in gaps])
        min_expected = 4.0   # absolute floor for 1.5× spacing at 12pt
        max_expected = 14.0  # absolute ceiling

        tight_count = sum(1 for g, _, _ in gaps if g < min_expected)
        if tight_count > len(gaps) * 0.3:
            violations.append(Violation(
                category=Category.SPACING,
                severity=Severity.WARNING,
                page=page_num,
                description="Line spacing appears tighter than 1.5× on this page",
                detail=f"Median inter-line gap: {avg_gap:.1f} pt (expected ~7 pt for 1.5×/12pt)",
            ))

    return violations


# ── Text alignment (justified) ────────────────────────────────────────────────

def check_alignment(doc: ParsedDocument) -> list[Violation]:
    """
    For each page, collect right-edge (x1) values of body text lines.
    High variance → not justified.
    """
    violations = []
    page_w_map = {i + 1: doc.page_sizes[i][0] for i in range(doc.page_count)}

    for page_num in range(1, doc.page_count + 1):
        lines = doc.lines_on_page(page_num)
        page_w = page_w_map.get(page_num, 595.28)

        # Only consider full-width body lines (not short headings or captions)
        expected_right = page_w - MARGIN_RIGHT_PT
        min_line_width = (expected_right - MARGIN_LEFT_PT) * 0.70  # at least 70% of text width

        full_lines = [
            l for l in lines
            if l.size and 11.0 <= l.size <= 13.0
            and (l.x1 - l.x0) > min_line_width
        ]

        if len(full_lines) < 5:
            continue

        right_edges = [l.x1 for l in full_lines]
        try:
            stdev = statistics.stdev(right_edges)
        except statistics.StatisticsError:
            continue

        if stdev > JUSTIFICATION_TOLERANCE_PT:
            violations.append(Violation(
                category=Category.ALIGNMENT,
                severity=Severity.WARNING,
                page=page_num,
                description="Body text may not be fully justified",
                detail=(
                    f"Right-edge std deviation: {stdev:.1f} pt "
                    f"(threshold: {JUSTIFICATION_TOLERANCE_PT} pt)"
                ),
            ))

    return violations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_spacing_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_line_spacing(doc))
    v.extend(check_alignment(doc))
    return v
