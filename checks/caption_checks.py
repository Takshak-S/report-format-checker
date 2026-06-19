"""
checks/caption_checks.py

Checks:
  1. Figure captions are placed BELOW their image
  2. Table titles are placed ABOVE their table
  3. Caption format: "Figure X.Y: Description" / "Table X.Y: Description"
  4. Chapter-wise numbering of figures and tables (e.g. Figure 2.1, Figure 2.2)
  5. Every figure/table is cited in the body text
"""
from __future__ import annotations

import re
from ingestion.pdf_loader import ParsedDocument, LineInfo, ImageInfo, TableInfo
from utils.constants import (
    FIGURE_CAPTION_PATTERN, TABLE_CAPTION_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_caption_number(text: str) -> tuple[int, int] | None:
    """Extract (chapter, number) from 'Figure 2.3: ...' → (2, 3)."""
    m = re.search(r"(\d+)\.(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _get_caption_lines(doc: ParsedDocument) -> list[LineInfo]:
    return [
        l for l in doc.lines
        if FIGURE_CAPTION_PATTERN.match(l.text.strip())
        or TABLE_CAPTION_PATTERN.match(l.text.strip())
    ]


def _is_figure_caption(text: str) -> bool:
    return bool(FIGURE_CAPTION_PATTERN.match(text.strip()))


def _is_table_caption(text: str) -> bool:
    return bool(TABLE_CAPTION_PATTERN.match(text.strip()))


def _is_caption_continuation(text: str) -> bool:
    """
    Check if a line is likely a continuation of a multi-line caption
    (doesn't start with 'Figure' or 'Table' and is relatively short).
    """
    stripped = text.strip()
    if not stripped:
        return False
    if FIGURE_CAPTION_PATTERN.match(stripped) or TABLE_CAPTION_PATTERN.match(stripped):
        return False
    # Continuation lines are typically short and don't start with heading patterns
    return len(stripped) < 120 and not re.match(r"^\d+\.\d+", stripped)


# ── Caption format check ──────────────────────────────────────────────────────

# Accept Figure/Fig. X.Y followed by :, –, -, or . separator then description
CAPTION_FORMAT_FIGURE = re.compile(
    r"^(?:Figure|Fig\.?)\s+\d+\.\d+\s*[:–\-.]\s*.+", re.IGNORECASE
)
CAPTION_FORMAT_TABLE = re.compile(
    r"^(?:Table|Tab\.?)\s+\d+\.\d+\s*[:–\-.]\s*.+", re.IGNORECASE
)

# Patterns to detect lines starting with Figure/Table that need format checking
FIGURE_START_PATTERN = re.compile(r"^(?:Figure|Fig\.?)\s+", re.IGNORECASE)
TABLE_START_PATTERN = re.compile(r"^(?:Table|Tab\.?)\s+", re.IGNORECASE)


def check_caption_format(doc: ParsedDocument) -> list[Violation]:
    violations = []
    for line in doc.lines:
        text = line.text.strip()
        if FIGURE_START_PATTERN.match(text):
            if not CAPTION_FORMAT_FIGURE.match(text):
                # Don't flag continuation lines
                if not _is_caption_continuation(text):
                    violations.append(Violation(
                        category=Category.CAPTIONS,
                        severity=Severity.WARNING,
                        page=line.page_num,
                        description="Figure caption format incorrect",
                        detail=f"Expected 'Figure X.Y: Description', found: '{text[:60]}'",
                    ))
        elif TABLE_START_PATTERN.match(text):
            if not CAPTION_FORMAT_TABLE.match(text):
                if not _is_caption_continuation(text):
                    violations.append(Violation(
                        category=Category.CAPTIONS,
                        severity=Severity.WARNING,
                        page=line.page_num,
                        description="Table caption format incorrect",
                        detail=f"Expected 'Table X.Y: Description', found: '{text[:60]}'",
                    ))
    return violations


# ── Figure caption position (must be BELOW image) ────────────────────────────

# Wider tolerance for figure-caption proximity (30pt — images may have whitespace)
FIGURE_CAPTION_PROXIMITY_PT = 30.0

def check_figure_caption_position(doc: ParsedDocument) -> list[Violation]:
    """
    For each figure caption, check there is an image whose bottom (y1)
    is above the caption's top coordinate on the same page.
    """
    violations = []

    for line in doc.lines:
        text = line.text.strip()
        if not _is_figure_caption(text):
            continue

        page_images = doc.images_on_page(line.page_num)
        if not page_images:
            # No image on this page at all
            violations.append(Violation(
                category=Category.CAPTIONS,
                severity=Severity.WARNING,
                page=line.page_num,
                description="Figure caption found but no image detected on this page",
                location=text[:60],
            ))
            continue

        # Check if any image is above the caption (image.y1 <= caption.top + tolerance)
        images_above = [img for img in page_images if img.y1 <= line.top + FIGURE_CAPTION_PROXIMITY_PT]
        if not images_above:
            violations.append(Violation(
                category=Category.CAPTIONS,
                severity=Severity.ERROR,
                page=line.page_num,
                description="Figure caption is not placed below its image",
                detail="No image found above this caption on the page",
                location=text[:60],
            ))

    return violations


# ── Table caption position (must be ABOVE table) ─────────────────────────────

# Wider tolerance for table-caption proximity (30pt)
TABLE_CAPTION_PROXIMITY_PT = 30.0

def check_table_caption_position(doc: ParsedDocument) -> list[Violation]:
    """
    For each table caption, check there is a table whose top (bbox[1])
    is below the caption's bottom coordinate on the same page.
    """
    violations = []

    for line in doc.lines:
        text = line.text.strip()
        if not _is_table_caption(text):
            continue

        page_tables = doc.tables_on_page(line.page_num)
        if not page_tables:
            violations.append(Violation(
                category=Category.CAPTIONS,
                severity=Severity.WARNING,
                page=line.page_num,
                description="Table caption found but no table detected on this page",
                location=text[:60],
            ))
            continue

        # Check if any table is below the caption (table.bbox[1] >= caption.bottom - tolerance)
        tables_below = [t for t in page_tables if t.bbox[1] >= line.bottom - TABLE_CAPTION_PROXIMITY_PT]
        if not tables_below:
            violations.append(Violation(
                category=Category.CAPTIONS,
                severity=Severity.ERROR,
                page=line.page_num,
                description="Table title is not placed above its table",
                detail="No table found below this caption on the page",
                location=text[:60],
            ))

    return violations


# ── Chapter-wise numbering check ─────────────────────────────────────────────

def check_caption_numbering(doc: ParsedDocument) -> list[Violation]:
    """
    Figures and tables must be numbered chapter-wise and sequentially.
    e.g., Figure 2.1, Figure 2.2, Figure 2.3 — not Figure 2.1, Figure 2.3.
    """
    violations = []

    figure_counters: dict[int, int] = {}  # chapter → last number
    table_counters:  dict[int, int] = {}

    caption_lines = sorted(
        _get_caption_lines(doc), key=lambda l: (l.page_num, l.top)
    )

    for line in caption_lines:
        text = line.text.strip()
        nums = _extract_caption_number(text)
        if not nums:
            continue
        ch, num = nums

        if _is_figure_caption(text):
            expected = figure_counters.get(ch, 0) + 1
            if num != expected:
                violations.append(Violation(
                    category=Category.CAPTIONS,
                    severity=Severity.WARNING,
                    page=line.page_num,
                    description="Figure numbering is not sequential chapter-wise",
                    detail=f"Expected Figure {ch}.{expected}, found '{text[:50]}'",
                ))
            figure_counters[ch] = num

        elif _is_table_caption(text):
            expected = table_counters.get(ch, 0) + 1
            if num != expected:
                violations.append(Violation(
                    category=Category.CAPTIONS,
                    severity=Severity.WARNING,
                    page=line.page_num,
                    description="Table numbering is not sequential chapter-wise",
                    detail=f"Expected Table {ch}.{expected}, found '{text[:50]}'",
                ))
            table_counters[ch] = num

    return violations


# ── Citation check (figure/table referenced in body text) ────────────────────

def check_caption_citations(doc: ParsedDocument) -> list[Violation]:
    """
    Every Figure X.Y and Table X.Y label that appears in captions
    should also be referenced somewhere in the body text.
    """
    violations = []
    full_text = "\n".join(doc.raw_text_by_page)

    caption_lines = _get_caption_lines(doc)

    for line in caption_lines:
        text = line.text.strip()
        nums = _extract_caption_number(text)
        if not nums:
            continue
        ch, num = nums
        kind = "Figure" if _is_figure_caption(text) else "Table"

        # Also search for Fig./Tab. abbreviations
        if kind == "Figure":
            ref_pattern = re.compile(
                rf"(?:Figure|Fig\.?)\s+{ch}\.{num}", re.IGNORECASE
            )
        else:
            ref_pattern = re.compile(
                rf"(?:Table|Tab\.?)\s+{ch}\.{num}", re.IGNORECASE
            )

        # Count occurrences — the caption itself counts as 1, need at least 2
        matches = ref_pattern.findall(full_text)
        if len(matches) < 2:
            violations.append(Violation(
                category=Category.CAPTIONS,
                severity=Severity.WARNING,
                page=line.page_num,
                description=f"{kind} {ch}.{num} is not cited in the body text",
                location=text[:60],
            ))

    return violations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_caption_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_caption_format(doc))
    v.extend(check_figure_caption_position(doc))
    v.extend(check_table_caption_position(doc))
    v.extend(check_caption_numbering(doc))
    v.extend(check_caption_citations(doc))
    return v
