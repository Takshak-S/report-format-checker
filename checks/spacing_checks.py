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
    HEADER_ZONE_PT, FOOTER_ZONE_PT,
    FONT_SIZE_BODY,
    Severity, Category,
)
from utils.error_model import Violation


# ── Line spacing ──────────────────────────────────────────────────────────────

def _expected_spacing(line_height: float) -> float:
    """Expected gap between lines = line_height × 1.5."""
    return line_height * LINE_SPACING_FACTOR


def _is_body_text(line: LineInfo) -> bool:
    """Check if a line is body text (12pt ± tolerance, not in header/footer)."""
    return line.size is not None and 10.5 <= line.size <= 13.5


def check_line_spacing(doc: ParsedDocument) -> list[Violation]:
    violations = []

    for page_num in range(1, doc.page_count + 1):
        lines = doc.lines_on_page(page_num)
        if len(lines) < 2:
            continue

        page_h = doc.page_sizes[page_num - 1][1] if page_num <= len(doc.page_sizes) else 841.89

        # Filter to body text lines, excluding header/footer zones
        body_lines = [
            l for l in lines
            if _is_body_text(l)
            and l.top >= HEADER_ZONE_PT
            and l.top <= (page_h - FOOTER_ZONE_PT)
        ]
        if len(body_lines) < 3:
            continue

        # Compute baseline-to-baseline distances (top-to-top) for more reliable spacing
        # (bottom-to-top gaps can be near-zero or negative due to ascender/descender overlap)
        baseline_gaps = []
        for i in range(1, len(body_lines)):
            prev = body_lines[i - 1]
            curr = body_lines[i]
            btb = curr.top - prev.top   # baseline-to-baseline (top-to-top)
            if 5 < btb < 80:   # ignore large gaps (paragraph breaks, figures, images)
                baseline_gaps.append((btb, prev, curr))

        if not baseline_gaps:
            continue

        # Expected baseline-to-baseline for 12pt text at 1.5× spacing = 12 × 1.5 = 18pt
        # But PDF char height is typically ~14pt for 12pt font, so leading ≈ 14 × 1.5 ≈ 21pt
        # Acceptable range: 14–25pt
        avg_btb = statistics.median([g[0] for g in baseline_gaps])
        min_expected_btb = 14.0   # floor for 1.5× spacing at 12pt
        max_expected_btb = 25.0   # ceiling

        tight_count = sum(1 for g, _, _ in baseline_gaps if g < min_expected_btb)
        if tight_count > len(baseline_gaps) * 0.40:
            violations.append(Violation(
                category=Category.SPACING,
                severity=Severity.WARNING,
                page=page_num,
                description="Line spacing appears tighter than 1.5× on this page",
                detail=f"Median baseline-to-baseline: {avg_btb:.1f} pt (expected 18–21 pt for 1.5×/12pt)",
            ))

        wide_count = sum(1 for g, _, _ in baseline_gaps if g > max_expected_btb)
        if wide_count > len(baseline_gaps) * 0.40:
            violations.append(Violation(
                category=Category.SPACING,
                severity=Severity.INFO,
                page=page_num,
                description="Line spacing appears wider than 1.5× on this page",
                detail=f"Median baseline-to-baseline: {avg_btb:.1f} pt (expected 18–21 pt for 1.5×/12pt)",
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
        page_h = doc.page_sizes[page_num - 1][1] if page_num <= len(doc.page_sizes) else 841.89

        # Only consider full-width body lines (not short headings, captions, or header/footer)
        expected_right = page_w - MARGIN_RIGHT_PT
        min_line_width = (expected_right - MARGIN_LEFT_PT) * 0.75  # at least 75% of text width (raised from 70%)

        full_lines = [
            l for l in lines
            if _is_body_text(l)
            and (l.x1 - l.x0) > min_line_width
            and l.top >= HEADER_ZONE_PT
            and l.top <= (page_h - FOOTER_ZONE_PT)
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
