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
    HEADER_ZONE_PT, FOOTER_ZONE_PT,
    Severity, Category,
)
from utils.error_model import Violation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_times_new_roman(fontname: str) -> bool:
    """
    Check if the font name is a variant of Times New Roman or a
    metric-compatible equivalent (Nimbus Roman, Liberation Serif, Tinos, etc.).
    """
    lower = fontname.lower().strip()
    # Direct alias match
    if any(alias == lower for alias in FONT_ALIASES):
        return True
    # Substring match for compound names (e.g., 'timesnewromanpsmt-bold')
    TNR_SUBSTRINGS = [
        "timesnewroman", "times new roman", "times-new-roman",
        "timesnewromanps", "times-roman",
        # TNR-equivalent font families
        "nimbusromno9l", "nimbus roman", "nimbusrom",
        "liberationserif", "liberation serif",
        "freeserif", "tinos",
    ]
    if any(alias in lower for alias in TNR_SUBSTRINGS):
        return True
    # Standalone "times" — only match if it's the whole name or prefix
    if lower == "times" or lower.startswith("times,") or lower.startswith("times-"):
        return True
    return False


def _classify_line(line: LineInfo) -> str:
    """Return element type label for a line based on text pattern and size."""
    text = line.text.strip()

    # Captions first (most specific pattern)
    if FIGURE_CAPTION_PATTERN.match(text) or TABLE_CAPTION_PATTERN.match(text):
        return "caption"

    # Level 0: 16pt, UPPERCASE, no decimal prefix — require min length to avoid false positives
    if (HEADING_L0_PATTERN.fullmatch(text)
            and line.size >= FONT_SIZE_HEADING_L0 - FONT_SIZE_TOLERANCE
            and len(text) > 6):
        return "heading_l0"

    # Level 1: 14pt, decimal prefix + UPPERCASE
    if HEADING_L1_PATTERN.match(text) and abs(line.size - FONT_SIZE_HEADING_L1) <= FONT_SIZE_TOLERANCE:
        return "heading_l1"

    # Also catch 14pt uppercase lines without numbering (but require min 2 words, min 8 chars)
    if (abs(line.size - FONT_SIZE_HEADING_L1) <= FONT_SIZE_TOLERANCE
            and text.isupper()
            and len(text) > 8
            and len(text.split()) >= 2):
        return "heading_l1"

    # Level 2: 12pt, Title Case, two-decimal prefix
    if HEADING_L2_PATTERN.match(text):
        return "heading_l2"

    # Level 3: Bold+italic at 12pt
    if line.size and _size_ok(line.size, 12.0) and line.bold and line.italic:
        return "heading_l3"

    return "body"


def _size_ok(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= FONT_SIZE_TOLERANCE


def _is_page_number(text: str) -> bool:
    """Check if text is a standalone page number (Roman or Arabic)."""
    text = text.strip()
    # Arabic numerals
    if re.fullmatch(r"\d{1,4}", text):
        return True
    # Roman numerals
    if re.fullmatch(r"[ivxlcdm]+", text, re.IGNORECASE):
        return True
    return False


def _is_in_header_footer(line: LineInfo, page_height: float) -> bool:
    """Check if a line is in the header or footer zone."""
    return line.top < HEADER_ZONE_PT or line.top > (page_height - FOOTER_ZONE_PT)


def _is_centered(line: LineInfo, page_width: float, tolerance: float = 20.0) -> bool:
    """
    Check if a line is horizontally centered on the page.
    Centered text (e.g. CERTIFICATE, title pages) should be skipped
    since it follows different formatting rules.
    """
    line_mid = (line.x0 + line.x1) / 2.0
    page_mid = page_width / 2.0
    if abs(line_mid - page_mid) > tolerance:
        return False
    # Also verify roughly equal margins on both sides
    left_margin = line.x0
    right_margin = page_width - line.x1
    return abs(left_margin - right_margin) < tolerance * 2


# ── Per-line font check ───────────────────────────────────────────────────────

def _check_line_font(line: LineInfo) -> list[Violation]:
    violations = []
    element = _classify_line(line)

    if _is_code_font(line.fontname):
        return violations

    # ── Font family check (applies to all elements)
    if not _is_times_new_roman(line.fontname):
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.CRITICAL,
            page=line.page_num,
            description=f"Wrong font family in {element}",
            detail=f"Found '{line.fontname}', expected Times New Roman",
            location=line.text[:60],
            bbox=(line.x0, line.top, line.x1, line.bottom),
        ))

    # ── Font size check
    expected_size_map = {
        "body":       FONT_SIZE_BODY,
        "heading_l0": FONT_SIZE_HEADING_L0,
        "heading_l1": FONT_SIZE_HEADING_L1,
        "heading_l2": FONT_SIZE_BODY,
        "heading_l3": FONT_SIZE_BODY,
        "caption":    FONT_SIZE_CAPTION,
    }
    expected_size = expected_size_map.get(element, FONT_SIZE_BODY)
    if not _size_ok(line.size, expected_size):
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.WARNING,
            page=line.page_num,
            description=f"Wrong font size in {element}",
            detail=f"Found {line.size} pt, expected {expected_size} pt",
            location=line.text[:60],
            bbox=(line.x0, line.top, line.x1, line.bottom),
        ))

    # ── Bold check for L1 headings
    if element == "heading_l1" and not line.bold:
        violations.append(Violation(
            category=Category.FONT,
            severity=Severity.INFO,
            page=line.page_num,
            description="Level-1 heading should be bold",
            location=line.text[:60],
            bbox=(line.x0, line.top, line.x1, line.bottom),
        ))

    return violations


def _is_code_font(fontname: str) -> bool:
    if not fontname:
        return False
    lower = fontname.lower()
    return any(sub in lower for sub in [
        "mono", "courier", "consolas", "typewriter", "teletype", "cmtt", "ectt", "lmtt", "sfmono",
        "fixed", "code", "ocr", "screen", "lucida console"
    ])


# ── Main entry point ──────────────────────────────────────────────────────────

def run_font_checks(doc: ParsedDocument) -> list[Violation]:
    """Check font name and size for every line in the document."""
    violations = []

    for line in doc.lines:
        text = line.text.strip()
        if not text:
            continue

        # Skip very short lines (page numbers, decorators)
        if len(text) < 4:
            continue

        # Skip standalone page numbers
        if _is_page_number(text):
            continue

        # Skip monospaced / code block fonts
        if _is_code_font(line.fontname):
            continue

        # Skip header/footer zone lines (they follow different formatting)
        page_idx = line.page_num - 1
        if page_idx < len(doc.page_sizes):
            page_w, page_h = doc.page_sizes[page_idx]
            if _is_in_header_footer(line, page_h):
                continue
            # Skip centered text (title pages, certificates, etc.)
            if _is_centered(line, page_w):
                continue

        violations.extend(_check_line_font(line))

    return violations

