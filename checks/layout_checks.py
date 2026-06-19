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
    MARGIN_TOLERANCE_PT, HEADER_ZONE_PT, FOOTER_ZONE_PT,
    Severity, Category,
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


def _is_header_footer(y_pos: float, page_height: float) -> bool:
    """Check if a Y coordinate falls in the header or footer zone."""
    return y_pos < HEADER_ZONE_PT or y_pos > (page_height - FOOTER_ZONE_PT)


def _is_page_number_only(lines: list, images: list) -> bool:
    """
    Returns True if the page contains only very short text (likely page number)
    and no images — these pages should be skipped for margin analysis.
    """
    if images:
        return False
    if not lines:
        return True
    significant = [l for l in lines if len(l.text.strip()) > 5]
    return len(significant) == 0


def check_margins(doc: ParsedDocument) -> list[Violation]:
    """
    Infer effective margins from the bounding box of all text content per page.
    Compares against required margins with a tolerance.

    Improvements:
    - Skips pages with only page numbers (no significant content)
    - Excludes header/footer zone content from margin calculations
    - Reports image overflow separately from text overflow
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

        # Skip pages containing only page numbers
        if _is_page_number_only(lines, images):
            continue

        # Filter out header/footer content for text margin check
        body_lines = [
            l for l in lines
            if not _is_header_footer(l.top, page_h)
            and len(l.text.strip()) > 3   # skip tiny fragments
        ]

        # ── Text-based margin check ──────────────────────────────────────────
        if body_lines:
            text_x0 = [l.x0 for l in body_lines]
            text_x1 = [l.x1 for l in body_lines]
            text_y0 = [l.top for l in body_lines]
            text_y1 = [l.bottom for l in body_lines]

            eff_left   = min(text_x0)
            eff_right  = page_w - max(text_x1)
            eff_top    = min(text_y0)
            eff_bottom = page_h - max(text_y1)

            if eff_left < MARGIN_LEFT_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.ERROR,
                    page=page_num,
                    description="Text extends into left binding margin",
                    detail=f"Text left edge at {eff_left:.1f} pt, required ≥ {MARGIN_LEFT_PT:.1f} pt",
                ))
            elif eff_left > MARGIN_LEFT_PT + 25:
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
                    description="Text extends into right margin",
                    detail=f"Right margin only {eff_right:.1f} pt, required ≥ {MARGIN_RIGHT_PT:.1f} pt",
                ))

            if eff_top < MARGIN_TOP_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.ERROR,
                    page=page_num,
                    description="Text extends into top margin",
                    detail=f"Top margin only {eff_top:.1f} pt, required ≥ {MARGIN_TOP_PT:.1f} pt",
                ))

            if eff_bottom < MARGIN_BOTTOM_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.WARNING,
                    page=page_num,
                    description="Text extends into bottom margin",
                    detail=f"Bottom margin only {eff_bottom:.1f} pt, required ≥ {MARGIN_BOTTOM_PT:.1f} pt",
                ))

        # ── Image-based margin check (separate reporting) ────────────────────
        for img in images:
            # Skip tiny/decorative images (< 20×20 rendered pt)
            img_w = img.x1 - img.x0
            img_h = img.y1 - img.y0
            if img_w < 20 or img_h < 20:
                continue

            if img.x0 < MARGIN_LEFT_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.ERROR,
                    page=page_num,
                    description="Image extends into left binding margin",
                    detail=f"Image left edge at {img.x0:.1f} pt, required ≥ {MARGIN_LEFT_PT:.1f} pt",
                ))

            if (page_w - img.x1) < MARGIN_RIGHT_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.ERROR,
                    page=page_num,
                    description="Image extends into right margin",
                    detail=f"Image right edge at {img.x1:.1f} pt, right margin only {page_w - img.x1:.1f} pt",
                ))

            if img.y0 < MARGIN_TOP_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.WARNING,
                    page=page_num,
                    description="Image extends into top margin",
                    detail=f"Image top at {img.y0:.1f} pt, required ≥ {MARGIN_TOP_PT:.1f} pt",
                ))

            if (page_h - img.y1) < MARGIN_BOTTOM_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.WARNING,
                    page=page_num,
                    description="Image extends into bottom margin",
                    detail=f"Image bottom at {img.y1:.1f} pt, bottom margin only {page_h - img.y1:.1f} pt",
                ))

    return violations


def run_layout_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_page_size(doc))
    v.extend(check_margins(doc))
    return v
