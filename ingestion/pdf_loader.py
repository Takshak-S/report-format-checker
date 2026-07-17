"""
ingestion/pdf_loader.py

Loads a PDF using pdfplumber and PyMuPDF, extracts raw features, 
and uses DocumentReconstructor to build the Document Object Model (DOM).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import fitz          # PyMuPDF
fitz.TOOLS.mupdf_display_errors(False)  # Silence xref formatting warnings
import pdfplumber

from nlp.dom import DocumentModel
from nlp.reconstruction import DocumentReconstructor

def _has_text_layer(pdf_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["pdffonts", str(pdf_path)],
            capture_output=True, text=True, timeout=15,
        )
        lines = result.stdout.strip().splitlines()
        # pdffonts header is 2 lines; if <= 2 lines -> no fonts -> scanned
        return len(lines) > 2
    except Exception:
        return True   # assume text layer if tool unavailable

def _extract_images(fitz_doc: fitz.Document) -> list[dict]:
    images = []
    for page_idx in range(len(fitz_doc)):
        page = fitz_doc[page_idx]
        page_num = page_idx + 1
        img_list = page.get_images(full=True)
        for img in img_list:
            xref = img[0]
            try:
                base = fitz_doc.extract_image(xref)
                rects = page.get_image_rects(xref)
                bbox = rects[0] if rects else fitz.Rect(0, 0, 0, 0)
                images.append({
                    'page': page_num,
                    'xref': xref,
                    'x0': bbox.x0, 'y0': bbox.y0, 'x1': bbox.x1, 'y1': bbox.y1,
                    'width_px': base.get("width", 0),
                    'height_px': base.get("height", 0),
                    'xres': base.get("xres", 0),
                    'yres': base.get("yres", 0),
                    'colorspace': base.get("colorspace", ""),
                })
            except Exception:
                pass
    return images

def load_pdf(pdf_path: str | Path) -> DocumentModel:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    has_text = _has_text_layer(path)
    
    raw_chars = []
    raw_tables = []
    page_sizes = []
    raw_text_by_page = []

    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            page_sizes.append((page.width, page.height))
            raw_text_by_page.append(page.extract_text() or "")
            
            if has_text and page.chars:
                for c in page.chars:
                    if not c.get("text", "").strip():
                        continue
                    raw_chars.append({
                        'page': page_num,
                        'text': c['text'],
                        'fontname': c.get('fontname', ''),
                        'size': c.get('size', 0),
                        'x0': c['x0'], 'y0': c['top'], 'x1': c['x1'], 'y1': c['bottom'],
                        'top': c['top']
                    })
                    
            try:
                tables = page.extract_tables()
                found_tables = page.find_tables()
                for i, tbl in enumerate(tables):
                    bbox = found_tables[i].bbox if i < len(found_tables) else (0, 0, 0, 0)
                    raw_tables.append({
                        'page': page_num,
                        'bbox': bbox,
                        'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3],
                        'rows': tbl
                    })
            except Exception:
                pass

    fitz_doc = fitz.open(str(path))
    raw_images = _extract_images(fitz_doc)
    # toc = fitz_doc.get_toc() # Can be used later for TOC mapping
    fitz_doc.close()

    reconstructor = DocumentReconstructor()
    dom = reconstructor.build_from_raw(
        page_sizes=page_sizes,
        raw_chars=raw_chars,
        raw_images=raw_images,
        raw_tables=raw_tables,
        has_text_layer=has_text
    )
    
    dom.raw_text = "\n\n".join(raw_text_by_page)
    return dom
