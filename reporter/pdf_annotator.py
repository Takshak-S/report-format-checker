"""
reporter/pdf_annotator.py

Generates an annotated copy of the original PDF with violations
highlighted directly on the pages using PyMuPDF annotations.

Color scheme:
  - CRITICAL → Red highlight
  - MAJOR    → Orange highlight
  - MINOR    → Yellow highlight
  - WARNING  → Light blue
  - SUGGESTION/INFO → Gray
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from utils.error_model import ViolationCollector, Violation
from utils.constants import Severity


# ── Annotation colors (RGB, 0-1 range) ───────────────────────────────────────

_COLORS = {
    Severity.CRITICAL: {
        "highlight": (1.0, 0.75, 0.75),
        "stroke":    (0.85, 0.1, 0.1),
    },
    Severity.MAJOR: {
        "highlight": (1.0, 0.85, 0.6),
        "stroke":    (0.8, 0.4, 0.0),
    },
    Severity.MINOR: {
        "highlight": (1.0, 0.93, 0.6),
        "stroke":    (0.8, 0.6, 0.0),
    },
    Severity.WARNING: {
        "highlight": (0.8, 0.9, 1.0),
        "stroke":    (0.2, 0.5, 0.8),
    },
    Severity.SUGGESTION: {
        "highlight": (0.9, 0.9, 0.9),
        "stroke":    (0.5, 0.5, 0.5),
    },
    Severity.INFO: {
        "highlight": (0.95, 0.95, 0.95),
        "stroke":    (0.6, 0.6, 0.6),
    }
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_popup_text(v: Violation) -> str:
    """Build concise, explainable text for the annotation popup."""
    parts = [f"[{v.severity}] {v.category}"]
    parts.append(f"Rule: {v.description}")
    
    if v.expected or v.detected:
        parts.append(f"Expected: {v.expected or 'N/A'}")
        parts.append(f"Detected: {v.detected or 'N/A'}")
        
    if v.confidence > 0:
        parts.append(f"Confidence: {round(v.confidence * 100, 1)}%")
        
    if v.reason:
        parts.append(f"Reason: {v.reason}")
        
    if v.signals:
        parts.append("Signals:")
        for s in v.signals:
            parts.append(f"  - {s}")
            
    if v.suggested_fix:
        parts.append(f"Fix: {v.suggested_fix}")
        
    return "\n".join(parts)


def _search_text_on_page(page: fitz.Page, text: str) -> list[fitz.Rect]:
    if not text or len(text.strip()) < 3:
        return []

    clean = text.strip()

    for length in (len(clean), 60, 40, 25, 15):
        if length > len(clean):
            continue
        search_str = clean[:length].strip()
        if len(search_str) < 3:
            continue
        hits = page.search_for(search_str, quads=False)
        if hits:
            return hits[:1] 

    return []


def _add_line_highlight(
    page: fitz.Page,
    rect: fitz.Rect,
    violation: Violation,
    colors: dict,
    note_y: float,
) -> float:
    if rect.is_empty or rect.is_infinite:
        return note_y

    if violation.category == "Page Layout":
        annot = page.add_rect_annot(rect)
    else:
        annot = page.add_highlight_annot(rect)
        
    annot.set_colors(stroke=colors["stroke"])
    if violation.category != "Page Layout":
        annot.set_opacity(0.45)
    annot.update()

    popup_text = _build_popup_text(violation)
    margin_width = 160
    text_rect = fitz.Rect(page.rect.width - margin_width, rect.y0, page.rect.width - 5, rect.y0 + 50)
    
    if note_y > text_rect.y0:
        text_rect = fitz.Rect(page.rect.width - margin_width, note_y, page.rect.width - 5, note_y + 50)

    note = page.add_freetext_annot(
        text_rect, popup_text, fontsize=7, fontname="helv", 
        text_color=colors["stroke"], fill_color=(1.0, 1.0, 1.0)
    )
    note.update()

    lines = len(popup_text.split('\n'))
    return text_rect.y0 + (lines * 10) + 10


def _add_page_note(
    page: fitz.Page,
    violation: Violation,
    colors: dict,
    note_y: float,
) -> float:
    popup_text = _build_popup_text(violation)
    margin_width = 160
    text_rect = fitz.Rect(page.rect.width - margin_width, note_y, page.rect.width - 5, note_y + 50)

    note = page.add_freetext_annot(
        text_rect, popup_text, fontsize=7, fontname="helv", 
        text_color=colors["stroke"], fill_color=(1.0, 1.0, 1.0)
    )
    note.update()

    lines = len(popup_text.split('\n'))
    return note_y + (lines * 10) + 10


def _add_legend(page: fitz.Page) -> None:
    legend_text = (
        "PDF Format Checker — Annotation Legend\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Red = CRITICAL (must fix)\n"
        "Orange = MAJOR\n"
        "Yellow = MINOR\n"
        "Blue = WARNING\n"
        "Gray = SUGGESTION / INFO\n"
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
    original_path = Path(original_pdf_path)
    if output_path is None:
        output_path = original_path.parent / f"{original_path.stem}_annotated.pdf"
    output_path = Path(output_path)

    doc = fitz.open(str(original_path))
    by_page = collector.by_page()

    if doc.page_count > 0:
        _add_legend(doc[0])

    unanchored: list[Violation] = []

    for page_num, violations in sorted(by_page.items()):
        if page_num == -1:
            continue  # handled below as document-level notes
        if page_num < 1 or page_num > doc.page_count:
            # No valid page (e.g. page 0 from caption continuity): render as
            # a document-level note on page 1 rather than dropping it.
            unanchored.extend(violations)
            continue

        page = doc[page_num - 1]
        note_y = 50.0

        for v in violations:
            colors = _COLORS.get(v.severity, _COLORS[Severity.INFO])

            highlighted = False
            if v.bbox:
                rect = fitz.Rect(*v.bbox)
                note_y = _add_line_highlight(page, rect, v, colors, note_y)
                highlighted = True
                
            elif v.location:
                rects = _search_text_on_page(page, v.location)
                if rects:
                    note_y = _add_line_highlight(page, rects[0], v, colors, note_y)
                    highlighted = True

            if not highlighted and v.detail:
                import re
                quoted = re.findall(r"'([^']{4,60})'", v.detail)
                for q in quoted:
                    rects = _search_text_on_page(page, q)
                    if rects:
                        note_y = _add_line_highlight(page, rects[0], v, colors, note_y)
                        highlighted = True
                        break

            if not highlighted:
                note_y = _add_page_note(page, v, colors, note_y)

    doc_level = by_page.get(-1, []) + unanchored
    if doc_level and doc.page_count > 0:
        page = doc[0]
        note_y = 40.0
        for v in doc_level:
            colors = _COLORS.get(v.severity, _COLORS[Severity.INFO])
            note_y = _add_page_note(page, v, colors, note_y)

    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()

    return output_path
