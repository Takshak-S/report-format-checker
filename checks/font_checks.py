"""
checks/font_checks.py

Checks every line's font name and size against the spec:
  - Body text       : Times New Roman, 12 pt
  - Level-1 headings: TNR, Bold, UPPERCASE, 14 pt
  - Level-0 titles  : TNR, UPPERCASE, 16 pt
  - Captions        : TNR, 10 pt
"""
from __future__ import annotations

import re
from ingestion.pdf_loader import ParsedDocument, LineInfo
from utils.constants import (
    FONT_ALIASES, FONT_SIZE_BODY, FONT_SIZE_HEADING_L1, FONT_SIZE_HEADING_L0,
    FONT_SIZE_CAPTION, FONT_SIZE_TOLERANCE,
    FIGURE_CAPTION_PATTERN, TABLE_CAPTION_PATTERN,
    HEADING_L0_PATTERN, HEADING_L1_PATTERN, HEADING_L2_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_times_new_roman(fontname: str) -> bool:
    lower = fontname.lower()
    return any(alias in lower for alias in FONT_ALIASES)


def _classify_line(line: LineInfo) -> str:
    """Return element type label for a line based on text pattern and size."""
    text = line.text.strip()
    if FIGURE_CAPTION_PATTERN.match(text) or TABLE_CAPTION_PATTERN.match(text):
        return "caption"
    if HEADING_L0_PATTERN.fullmatch(text) and line.size >= FONT_SIZE_HEADING_L0 - FONT_SIZE_TOLERANCE:
        return "heading_l0"
    if HEADING_L1_PATTERN.match(text):
        return "heading_l1"
    if HEADING_L2_PATTERN.match(text):
        return "heading_l2"
    return "body"


def _size_ok(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= FONT_SIZE_TOLERANCE


# ── Per-line font check ───────────────────────────────────────────────────────

def _check_line_font(line: LineInfo) -> list[Violation]:
    violations = []
    element = _classify_line(line)

    # ── Font family check (applies to all elements)
    if not _is_times_new_roman(line.fontname):
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.ERROR,
            page=line.page_num,
            description=f"Wrong font family in {element}",
            detail=f"Found '{line.fontname}', expected Times New Roman",
            location=line.text[:60],
        ))

    # ── Font size check
    expected_size_map = {
        "body":       FONT_SIZE_BODY,
        "heading_l0": FONT_SIZE_HEADING_L0,
        "heading_l1": FONT_SIZE_HEADING_L1,
        "heading_l2": FONT_SIZE_BODY,
        "caption":    FONT_SIZE_CAPTION,
    }
    expected_size = expected_size_map[element]
    if not _size_ok(line.size, expected_size):
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.WARNING,
            page=line.page_num,
            description=f"Wrong font size in {element}",
            detail=f"Found {line.size} pt, expected {expected_size} pt",
            location=line.text[:60],
        ))

    # ── Bold check for L1 headings
    if element == "heading_l1" and not line.bold:
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.WARNING,
            page=line.page_num,
            description="Level-1 heading should be bold",
            location=line.text[:60],
        ))

    # ── Bold+Italic check for L3 (sub-sub-headings detected by size=12, bold+italic)
    if line.size and _size_ok(line.size, 12.0) and line.bold and line.italic:
        # This is a sub-sub-heading — font is correct, no further check needed
        pass

    return violations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_font_checks(doc: ParsedDocument) -> list[Violation]:
    """Check font name and size for every line in the document."""
    violations = []
    for line in doc.lines:
        if not line.text.strip():
            continue
        # Skip very short lines (page numbers, decorators)
        if len(line.text.strip()) < 3:
            continue
        violations.extend(_check_line_font(line))
    return violations
