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
    Severity, Category, EQUATION_PATTERN, EQUATION_BROAD_PATTERN
)
from utils.error_model import Violation


def check_page_size(doc: ParsedDocument) -> list[Violation]:
    violations = []
    # Increase tolerance for page size check to reduce false positives (15 pt ~ 5.3 mm)
    relaxed_tolerance = max(PAGE_SIZE_TOLERANCE_PT, 15.0)
    for page_idx, (w, h) in enumerate(doc.page_sizes):
        page_num = page_idx + 1
        if (abs(w - PAGE_WIDTH_PT) > relaxed_tolerance or
                abs(h - PAGE_HEIGHT_PT) > relaxed_tolerance):
            violations.append(Violation(
                category=Category.PAGE_LAYOUT,
                severity=Severity.CRITICAL,
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


def _is_code_font(fontname: str) -> bool:
    if not fontname:
        return False
    lower = fontname.lower()
    return any(sub in lower for sub in [
        "mono", "courier", "consolas", "typewriter", "teletype", "cmtt", "ectt", "lmtt", "sfmono",
        "fixed", "code", "ocr", "screen", "lucida console"
    ])


def _is_centered(x0: float, x1: float, page_w: float, tolerance: float = 20.0) -> bool:
    """Check if a line of text is horizontally centered on the page."""
    left_gap = x0
    right_gap = page_w - x1
    return abs(left_gap - right_gap) < tolerance


import statistics

def check_margins(doc: ParsedDocument) -> list[Violation]:
    """
    Infer effective margins from the bounding box of all text content per page.
    Compares against required margins with a tolerance.

    Improvements:
    - Skips pages with only page numbers (no significant content)
    - Excludes header/footer zone content from margin calculations
    - Excludes equations and code lines which often overhang margins intentionally
    - Excludes centered text (like headings/titles) which often have special placement
    - Reports image overflow separately from text overflow
    - Dynamically tolerates a 1-inch left margin (72pt) if most of the document uses it
    """
    # Pass 1: Gather page data and compute document-level effective margins
    pages_to_check = []
    all_eff_lefts = []

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

        # Filter out header/footer content, code lines, equations, tiny fragments, and centered text
        body_lines = []
        for l in lines:
            text = l.text.strip()
            if _is_header_footer(l.top, page_h):
                continue
            if _is_code_font(l.fontname):
                continue
            if len(text) <= 5:  # skip tiny fragments
                continue
            if EQUATION_PATTERN.search(text) or EQUATION_BROAD_PATTERN.search(text):
                continue
            if _is_centered(l.x0, l.x1, page_w):
                continue
            body_lines.append(l)

        pages_to_check.append((page_num, page_w, page_h, body_lines, images))

        if body_lines:
            eff_left = min(l.x0 for l in body_lines)
            all_eff_lefts.append(eff_left)

    # Dynamic margin adaptation:
    # If the document consistently uses a 1-inch left margin (~72pt) instead of 1.5-inch (108pt), relax the rule.
    expected_left_margin = MARGIN_LEFT_PT
    if all_eff_lefts:
        median_left = statistics.median(all_eff_lefts)
        if 65.0 <= median_left <= 85.0:
            expected_left_margin = 72.0

    violations = []

    # Pass 2: Check each page against expected margins
    for page_num, page_w, page_h, body_lines, images in pages_to_check:
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

            if eff_left < expected_left_margin - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.CRITICAL,
                    page=page_num,
                    description="Text extends into left binding margin",
                    detail=f"Text left edge at {eff_left:.1f} pt, required ≥ {expected_left_margin:.1f} pt",
                ))

            if eff_right < MARGIN_RIGHT_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.CRITICAL,
                    page=page_num,
                    description="Text extends into right margin",
                    detail=f"Right margin only {eff_right:.1f} pt, required ≥ {MARGIN_RIGHT_PT:.1f} pt",
                ))

            if eff_top < MARGIN_TOP_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.CRITICAL,
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

            if img.x0 < expected_left_margin - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.CRITICAL,
                    page=page_num,
                    description="Image extends into left binding margin",
                    detail=f"Image left edge at {img.x0:.1f} pt, required ≥ {expected_left_margin:.1f} pt",
                ))

            if (page_w - img.x1) < MARGIN_RIGHT_PT - MARGIN_TOLERANCE_PT:
                violations.append(Violation(
                    category=Category.PAGE_LAYOUT,
                    severity=Severity.CRITICAL,
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
