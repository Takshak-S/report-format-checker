"""
checks/layout_checks.py

Checks:
  1. Page size (A4)
  2. Margins (Left 1.5", Right/Top/Bottom 1") inferred from content bounding boxes
  3. Content overflow (text/images outside margin boundaries)
"""
from __future__ import annotations

from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    PAGE_WIDTH_PT, PAGE_HEIGHT_PT, PAGE_SIZE_TOLERANCE_PT,
    MARGIN_LEFT_PT, MARGIN_RIGHT_PT, MARGIN_TOP_PT, MARGIN_BOTTOM_PT,
    MARGIN_TOLERANCE_PT, Severity, Category,
)
from utils.error_model import Violation


def check_page_size(doc: ParsedDocument) -> list[Violation]:
    violations = []
    for page_idx, (w, h) in enumerate(doc.page_sizes):
        page_num = page_idx + 1
        if (abs(w - PAGE_WIDTH_PT) > PAGE_SIZE_TOLERANCE_PT or
                abs(h - PAGE_HEIGHT_PT) > PAGE_SIZE_TOLERANCE_PT):
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.ERROR,
                page=page_num,
                description="Page size is not A4",
                detail=f"Found {w:.1f}×{h:.1f} pt, expected {PAGE_WIDTH_PT}×{PAGE_HEIGHT_PT} pt",
            ))
    return violations


def check_margins(doc: ParsedDocument) -> list[Violation]:
    """
    Infer effective margins from the bounding box of all text content per page.
    Compares against required margins with a tolerance.
    """
    violations = []

    for page_idx in range(doc.page_count):
        page_num  = page_idx + 1
        page_w, page_h = doc.page_sizes[page_idx]
        lines     = doc.lines_on_page(page_num)
        images    = doc.images_on_page(page_num)

        # Skip pages with no extractable content
        if not lines and not images:
            continue

        # Collect all content x/y extents
        all_x0 = [l.x0 for l in lines] + [i.x0 for i in images]
        all_x1 = [l.x1 for l in lines] + [i.x1 for i in images]
        all_y0 = [l.top for l in lines] + [i.y0 for i in images]
        all_y1 = [l.bottom for l in lines] + [i.y1 for i in images]

        if not all_x0:
            continue

        eff_left   = min(all_x0)
        eff_right  = page_w - max(all_x1)
        eff_top    = min(all_y0)
        eff_bottom = page_h - max(all_y1)

        # Check content overflow (margin too small)
        if eff_left < MARGIN_LEFT_PT - MARGIN_TOLERANCE_PT:
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.ERROR,
                page=page_num,
                description="Content extends into left binding margin",
                detail=f"Content left edge at {eff_left:.1f} pt, required ≥ {MARGIN_LEFT_PT:.1f} pt",
            ))
        elif eff_left > MARGIN_LEFT_PT + 20:
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.WARNING,
                page=page_num,
                description="Left margin appears wider than 1.5\"",
                detail=f"Effective left margin: {eff_left:.1f} pt (expected ~{MARGIN_LEFT_PT:.1f} pt)",
            ))

        if eff_right < MARGIN_RIGHT_PT - MARGIN_TOLERANCE_PT:
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.ERROR,
                page=page_num,
                description="Content extends into right margin",
                detail=f"Right margin only {eff_right:.1f} pt, required ≥ {MARGIN_RIGHT_PT:.1f} pt",
            ))

        if eff_top < MARGIN_TOP_PT - MARGIN_TOLERANCE_PT:
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.ERROR,
                page=page_num,
                description="Content extends into top margin",
                detail=f"Top margin only {eff_top:.1f} pt, required ≥ {MARGIN_TOP_PT:.1f} pt",
            ))

        if eff_bottom < MARGIN_BOTTOM_PT - MARGIN_TOLERANCE_PT:
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.WARNING,
                page=page_num,
                description="Content extends into bottom margin",
                detail=f"Bottom margin only {eff_bottom:.1f} pt, required ≥ {MARGIN_BOTTOM_PT:.1f} pt",
            ))

    return violations


def run_layout_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_page_size(doc))
    v.extend(check_margins(doc))
    return v
