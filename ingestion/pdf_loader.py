"""
ingestion/pdf_loader.py

Loads a PDF and builds the shared ParsedDocument object that all checks consume.
Uses:
  - pdfplumber  → text, char metadata (font, size, bbox), tables
  - PyMuPDF     → page dimensions, embedded images + DPI, TOC
  - pypdf       → metadata fallback
"""
from __future__ import annotations

import io
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz          # PyMuPDF
import pdfplumber
from pypdf import PdfReader


# ── Data classes returned by the loader ───────────────────────────────────────

@dataclass
class CharInfo:
    """Single character with full layout metadata from pdfplumber."""
    text:     str
    fontname: str
    size:     float
    bold:     bool
    italic:   bool
    x0: float; y0: float; x1: float; y1: float
    top: float   # distance from page top (pdfplumber coordinate)


@dataclass
class LineInfo:
    """A logical line aggregated from consecutive CharInfo objects."""
    text:      str
    chars:     list[CharInfo]
    page_num:  int          # 1-based
    top:       float        # top coord of first char
    bottom:    float        # bottom coord of last char
    x0:        float        # leftmost x
    x1:        float        # rightmost x
    fontname:  str          # dominant fontname
    size:      float        # dominant size
    bold:      bool
    italic:    bool

    @property
    def mid_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class ImageInfo:
    """Embedded image metadata from PyMuPDF."""
    page_num: int           # 1-based
    xref:     int           # PyMuPDF xref id
    x0: float; y0: float; x1: float; y1: float   # bbox on page
    width_px:  int
    height_px: int
    xres:      int          # DPI horizontal
    yres:      int          # DPI vertical
    colorspace: str
    image_bytes: Optional[bytes] = None   # raw bytes for Pillow if needed


@dataclass
class TableInfo:
    """A table detected by pdfplumber."""
    page_num: int
    bbox:    tuple[float, float, float, float]   # (x0, y0, x1, y1)
    rows:    list[list[Optional[str]]]


@dataclass
class ParsedDocument:
    """Full parsed representation of the PDF consumed by all check modules."""
    path:        Path
    page_count:  int
    page_sizes:  list[tuple[float, float]]   # (width, height) per page in pts
    lines:       list[LineInfo]              # all text lines across all pages
    images:      list[ImageInfo]
    tables:      list[TableInfo]
    toc:         list[tuple[int, str, int]]  # (level, title, page) from PyMuPDF
    raw_text_by_page: list[str]             # plain text per page (1-indexed, idx 0 = page 1)
    has_text_layer: bool                    # False → scanned PDF

    def lines_on_page(self, page_num: int) -> list[LineInfo]:
        return [l for l in self.lines if l.page_num == page_num]

    def images_on_page(self, page_num: int) -> list[ImageInfo]:
        return [i for i in self.images if i.page_num == page_num]

    def tables_on_page(self, page_num: int) -> list[TableInfo]:
        return [t for t in self.tables if t.page_num == page_num]


# ── Font name normalisation ────────────────────────────────────────────────────

def _normalize_font(raw: str) -> tuple[str, bool, bool]:
    """
    Strip subset prefix (e.g. 'ABCDEF+TimesNewRoman-Bold') and infer
    bold/italic from the suffix.
    Returns (clean_name_lower, is_bold, is_italic).
    """
    name = re.sub(r"^[A-Z]{6}\+", "", raw)   # remove 6-char subset prefix
    lower = name.lower()
    bold   = any(kw in lower for kw in ("bold", "-bd", ",bold"))
    italic = any(kw in lower for kw in ("italic", "oblique", "-it", ",italic"))
    clean  = re.sub(r"[-,]?(bold|italic|oblique|bd|it)", "", lower).strip("-,")
    return clean, bold, italic


# ── Line aggregation from pdfplumber chars ────────────────────────────────────

# Y-proximity threshold for grouping characters into lines (widened from 3.0)
LINE_GROUP_TOLERANCE = 4.0


def _aggregate_lines(plumber_page, page_num: int) -> list[LineInfo]:
    """
    Group pdfplumber characters into logical lines by Y-coordinate proximity,
    then compute dominant font/size for each line.
    """
    chars_raw = plumber_page.chars
    if not chars_raw:
        return []

    chars: list[CharInfo] = []
    for c in chars_raw:
        if not c.get("text", "").strip():
            continue
        raw_font = c.get("fontname", "")
        clean_font, bold, italic = _normalize_font(raw_font)
        chars.append(CharInfo(
            text=c["text"],
            fontname=clean_font,
            size=round(c.get("size", 0), 2),
            bold=bold,
            italic=italic,
            x0=c["x0"], y0=c["y0"], x1=c["x1"], y1=c["y1"],
            top=c["top"],
        ))

    if not chars:
        return []

    # Sort by top then x0
    chars.sort(key=lambda c: (round(c.top, 1), c.x0))

    # Group into lines: chars with top within LINE_GROUP_TOLERANCE pts are on the same line
    lines: list[LineInfo] = []
    current_group: list[CharInfo] = [chars[0]]

    for ch in chars[1:]:
        if abs(ch.top - current_group[0].top) < LINE_GROUP_TOLERANCE:
            current_group.append(ch)
        else:
            lines.append(_make_line(current_group, page_num))
            current_group = [ch]
    if current_group:
        lines.append(_make_line(current_group, page_num))

    return lines


def _dominant(values: list) -> any:
    """Return most frequent value in list."""
    if not values:
        return None
    return max(set(values), key=values.count)


def _make_line(chars: list[CharInfo], page_num: int) -> LineInfo:
    chars.sort(key=lambda c: c.x0)

    # Build text with space insertion for gaps between characters
    # When chars have a horizontal gap > ~25% of average char width, insert a space
    text_parts = []
    if chars:
        avg_char_width = sum(c.x1 - c.x0 for c in chars) / len(chars) if chars else 5.0
        space_threshold = max(avg_char_width * 0.25, 1.5)  # at least 1.5pt gap = space

        text_parts.append(chars[0].text)
        for i in range(1, len(chars)):
            gap = chars[i].x0 - chars[i - 1].x1
            if gap > space_threshold:
                text_parts.append(" ")
            text_parts.append(chars[i].text)

    text = "".join(text_parts).strip()

    # For dominant font/size calculation, filter out superscript/subscript characters
    # (chars significantly smaller than the dominant size)
    sizes = [c.size for c in chars]
    raw_dominant_size = _dominant(sizes) or 12.0

    # Only consider "normal-sized" characters for dominant calculations
    # (chars within 70% of the dominant size)
    normal_chars = [
        c for c in chars
        if c.size >= raw_dominant_size * 0.70
    ] or chars  # fallback to all if filter removes everything

    fonts = [c.fontname for c in normal_chars]
    normal_sizes = [c.size for c in normal_chars]
    bolds   = [c.bold for c in normal_chars]
    italics = [c.italic for c in normal_chars]

    return LineInfo(
        text=text,
        chars=chars,
        page_num=page_num,
        top=min(c.top for c in chars),
        bottom=max(c.y1 for c in chars),
        x0=min(c.x0 for c in chars),
        x1=max(c.x1 for c in chars),
        fontname=_dominant(fonts),
        size=_dominant(normal_sizes),
        # Use 60% majority for bold/italic (more robust than 50%)
        bold=sum(bolds) > len(bolds) * 0.6,
        italic=sum(italics) > len(italics) * 0.6,
    )


# ── Image extraction via PyMuPDF ──────────────────────────────────────────────

def _extract_images(fitz_doc: fitz.Document) -> list[ImageInfo]:
    images: list[ImageInfo] = []
    for page_idx in range(len(fitz_doc)):
        page = fitz_doc[page_idx]
        page_num = page_idx + 1
        img_list = page.get_images(full=True)
        for img in img_list:
            xref = img[0]
            try:
                base = fitz_doc.extract_image(xref)
                # Get bbox on page via get_image_bbox
                rects = page.get_image_rects(xref)
                bbox = rects[0] if rects else fitz.Rect(0, 0, 0, 0)
                images.append(ImageInfo(
                    page_num=page_num,
                    xref=xref,
                    x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1,
                    width_px=base.get("width", 0),
                    height_px=base.get("height", 0),
                    xres=base.get("xres", 0),
                    yres=base.get("yres", 0),
                    colorspace=base.get("colorspace", ""),
                    image_bytes=base.get("image"),
                ))
            except Exception:
                pass
    return images


# ── Table extraction via pdfplumber ──────────────────────────────────────────

def _extract_tables(plumber_pdf: pdfplumber.PDF) -> list[TableInfo]:
    tables: list[TableInfo] = []
    for page_idx, page in enumerate(plumber_pdf.pages):
        page_num = page_idx + 1
        try:
            raw_tables = page.extract_tables()
            page_tables = page.find_tables()
            for i, tbl in enumerate(raw_tables):
                bbox = page_tables[i].bbox if i < len(page_tables) else (0, 0, 0, 0)
                tables.append(TableInfo(
                    page_num=page_num,
                    bbox=bbox,
                    rows=tbl,
                ))
        except Exception:
            pass
    return tables


# ── Check for text layer ──────────────────────────────────────────────────────

def _has_text_layer(pdf_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["pdffonts", str(pdf_path)],
            capture_output=True, text=True, timeout=15,
        )
        lines = result.stdout.strip().splitlines()
        # pdffonts header is 2 lines; if ≤2 lines → no fonts → scanned
        return len(lines) > 2
    except Exception:
        return True   # assume text layer if tool unavailable


# ── Main loader entry point ───────────────────────────────────────────────────

def load_pdf(pdf_path: str | Path) -> ParsedDocument:
    """
    Parse a PDF into a ParsedDocument.
    Raises FileNotFoundError if the path doesn't exist.
    Raises ValueError for password-protected or corrupt PDFs.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    has_text = _has_text_layer(path)

    # ── pdfplumber pass ───────────────────────────────────────────────────────
    all_lines: list[LineInfo] = []
    all_tables: list[TableInfo] = []
    raw_text_by_page: list[str] = []
    page_sizes: list[tuple[float, float]] = []

    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            page_sizes.append((page.width, page.height))
            raw_text_by_page.append(page.extract_text() or "")
            if has_text:
                all_lines.extend(_aggregate_lines(page, page_num))

        # Tables extracted separately (needs bbox from find_tables)
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            try:
                raw_tables = page.extract_tables()
                found_tables = page.find_tables()
                for i, tbl in enumerate(raw_tables):
                    bbox = found_tables[i].bbox if i < len(found_tables) else (0, 0, 0, 0)
                    all_tables.append(TableInfo(
                        page_num=page_num,
                        bbox=bbox,
                        rows=tbl,
                    ))
            except Exception:
                pass

    # ── PyMuPDF pass ─────────────────────────────────────────────────────────
    fitz_doc = fitz.open(str(path))
    images    = _extract_images(fitz_doc)
    toc       = fitz_doc.get_toc()   # [(level, title, page), ...]
    page_count = len(fitz_doc)
    fitz_doc.close()

    return ParsedDocument(
        path=path,
        page_count=page_count,
        page_sizes=page_sizes,
        lines=all_lines,
        images=images,
        tables=all_tables,
        toc=toc,
        raw_text_by_page=raw_text_by_page,
        has_text_layer=has_text,
    )
