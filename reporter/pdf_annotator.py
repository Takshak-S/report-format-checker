"""
reporter/pdf_annotator.py

Generates an annotated copy of the original PDF with violations
highlighted directly on the pages using PyMuPDF annotations.

Color scheme:
  - ERROR   → Red highlight on the specific line/word
  - WARNING → Yellow/amber highlight on the specific line/word
  - INFO    → Skipped (only in Excel report)

Uses PyMuPDF's native text search to find exact text positions,
ensuring highlights are precise (line/word level, not page-level blocks).
Violation details are shown as small margin icons with click-to-read popups.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from utils.error_model import ViolationCollector, Violation
from utils.constants import Severity


# ── Annotation colors (RGB, 0-1 range) ───────────────────────────────────────

_COLORS = {
    Severity.ERROR: {
        "highlight": (1.0, 0.75, 0.75),   # light red fill
        "stroke":    (0.85, 0.1, 0.1),     # red border
    },
    Severity.WARNING: {
        "highlight": (1.0, 0.93, 0.6),    # light amber fill
        "stroke":    (0.8, 0.6, 0.0),      # amber border
    },
}

# Margin note positioning
_NOTE_X_OFFSET = 18  # pt from right edge of page


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_popup_text(v: Violation) -> str:
    """Build concise text for the annotation popup / tooltip."""
    parts = [f"[{v.severity}] {v.category}", v.description]
    if v.detail:
        parts.append(f"→ {v.detail}")
    return "\n".join(parts)


def _search_text_on_page(page: fitz.Page, text: str) -> list[fitz.Rect]:
    """
    Search for text on a page using progressively shorter prefixes.
    Returns list of matching rects (usually 1).
    """
    if not text or len(text.strip()) < 3:
        return []

    clean = text.strip()

    # Try exact match first, then progressively shorter prefixes
    for length in (len(clean), 60, 40, 25, 15):
        if length > len(clean):
            continue
        search_str = clean[:length].strip()
        if len(search_str) < 3:
            continue
        hits = page.search_for(search_str, quads=False)
        if hits:
            return hits[:1]  # return only the first match

    return []


def _add_line_highlight(
    page: fitz.Page,
    rect: fitz.Rect,
    violation: Violation,
    colors: dict,
    note_y: float,
) -> float:
    """
    Add a highlight annotation on the text rect, plus a small margin
    icon with the violation details as a popup.
    Returns the updated note_y position.
    """
    if rect.is_empty or rect.is_infinite:
        return note_y

    # 1) Add highlight on the text (no content text — keeps it clean)
    highlight = page.add_highlight_annot(rect)
    highlight.set_colors(stroke=colors["stroke"])
    highlight.set_opacity(0.45)
    highlight.update()

    # 2) Add a small margin note icon linked to the highlight
    popup_text = _build_popup_text(violation)
    note_x = page.rect.width - _NOTE_X_OFFSET
    point = fitz.Point(note_x, rect.y0)

    note = page.add_text_annot(point, popup_text, icon="Comment")
    note.set_colors(stroke=colors["stroke"])
    note.update()

    return note_y


def _add_page_note(
    page: fitz.Page,
    violation: Violation,
    colors: dict,
    note_y: float,
) -> float:
    """
    Add a sticky-note icon in the right margin for page-level violations
    that don't have specific text to highlight.
    Returns the updated note_y position.
    """
    popup_text = _build_popup_text(violation)
    note_x = page.rect.width - _NOTE_X_OFFSET
    point = fitz.Point(note_x, note_y)

    note = page.add_text_annot(point, popup_text, icon="Note")
    note.set_colors(stroke=colors["stroke"])
    note.update()

    return note_y + 25  # space out stacked notes


def _add_legend(page: fitz.Page) -> None:
    """Add a small color-coded legend icon on the first page."""
    legend_text = (
        "PDF Format Checker — Annotation Legend\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Red highlights  = ERRORS (must fix)\n"
        "Yellow highlights = WARNINGS (should fix)\n"
        "Click margin icons to read details.\n"
    )
    point = fitz.Point(15, 15)
    annot = page.add_text_annot(point, legend_text, icon="Help")
    annot.set_colors(stroke=(0.2, 0.2, 0.7))
    annot.update()


# ── Public API ───────────────────────────────────────────────────────────────

def generate_annotated_pdf(
    collector: ViolationCollector,
    original_pdf_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    Create an annotated copy of the original PDF with violations highlighted.

    Strategy for each violation (ERROR/WARNING only, INFO skipped):
      1. If `location` text is set → search for it on the page → highlight the
         found line/word with a colored highlight annotation.
      2. If no text match → add a margin sticky-note icon with details.

    Args:
        collector: ViolationCollector with all findings.
        original_pdf_path: Path to the original PDF file.
        output_path: Where to save the annotated PDF.

    Returns:
        Path to the saved annotated PDF.
    """
    original_path = Path(original_pdf_path)
    if output_path is None:
        output_path = original_path.parent / f"{original_path.stem}_annotated.pdf"
    output_path = Path(output_path)

    doc = fitz.open(str(original_path))

    # Group violations by page, skip INFO severity
    by_page = collector.by_page()

    # Add legend on first page
    if doc.page_count > 0:
        _add_legend(doc[0])

    for page_num, violations in sorted(by_page.items()):
        if page_num < 1 or page_num > doc.page_count:
            continue

        page = doc[page_num - 1]  # 0-indexed
        note_y = 50.0  # starting y for margin notes on this page

        for v in violations:
            # Skip INFO violations
            if v.severity == Severity.INFO:
                continue

            colors = _COLORS.get(v.severity)
            if not colors:
                continue

            highlighted = False

            # Strategy 1: Search for `location` text on the page
            if v.location:
                rects = _search_text_on_page(page, v.location)
                if rects:
                    note_y = _add_line_highlight(page, rects[0], v, colors, note_y)
                    highlighted = True

            # Strategy 2: Search for key phrases from `description` or `detail`
            if not highlighted and v.detail:
                # Try to find quoted text from detail (e.g. "Found 'Arial'")
                import re
                quoted = re.findall(r"'([^']{4,60})'", v.detail)
                for q in quoted:
                    rects = _search_text_on_page(page, q)
                    if rects:
                        note_y = _add_line_highlight(page, rects[0], v, colors, note_y)
                        highlighted = True
                        break

            # Strategy 3: Fall back to a margin sticky note
            if not highlighted:
                note_y = _add_page_note(page, v, colors, note_y)

    # Handle document-level violations (page == -1) — add to first page
    doc_level = by_page.get(-1, [])
    if doc_level and doc.page_count > 0:
        page = doc[0]
        note_y = 40.0

        for v in doc_level:
            if v.severity == Severity.INFO:
                continue
            colors = _COLORS.get(v.severity)
            if not colors:
                continue
            note_y = _add_page_note(page, v, colors, note_y)

    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()

    return output_path
