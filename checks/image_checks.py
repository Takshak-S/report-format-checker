"""
checks/image_checks.py

Checks:
  1. Embedded image DPI >= 600 (via PyMuPDF xres/yres)
  2. Fallback DPI estimation via Pillow when xres=0
  3. Graph axis label presence via pytesseract OCR on rasterized pages
"""
from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

from ingestion.pdf_loader import ParsedDocument, ImageInfo
from utils.constants import MIN_IMAGE_DPI, Severity, Category
from utils.error_model import Violation

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# ── DPI check ─────────────────────────────────────────────────────────────────

def _estimate_dpi_from_bytes(img_info: ImageInfo) -> int | None:
    """Use Pillow to read DPI from image bytes when PyMuPDF returns 0."""
    if not PIL_AVAILABLE or not img_info.image_bytes:
        return None
    try:
        with Image.open(io.BytesIO(img_info.image_bytes)) as im:
            dpi_info = im.info.get("dpi")
            if dpi_info:
                return int(min(dpi_info))
    except Exception:
        pass
    return None


def check_image_dpi(doc: ParsedDocument) -> list[Violation]:
    violations = []

    for img in doc.images:
        xres = img.xres
        yres = img.yres

        # If PyMuPDF returned 0, try Pillow fallback
        if xres == 0 or yres == 0:
            estimated = _estimate_dpi_from_bytes(img)
            if estimated is not None:
                xres = yres = estimated
            else:
                # Cannot determine DPI — report as info
                violations.append(Violation(
                    category=Category.IMAGES,
                    severity=Severity.INFO,
                    page=img.page_num,
                    description="Could not determine image DPI",
                    detail=f"Image at ({img.x0:.0f}, {img.y0:.0f}) — verify manually that DPI ≥ {MIN_IMAGE_DPI}",
                ))
                continue

        min_dpi = min(xres, yres)
        if min_dpi < MIN_IMAGE_DPI:
            violations.append(Violation(
                category=Category.IMAGES,
                severity=Severity.ERROR,
                page=img.page_num,
                description=f"Image DPI below required minimum ({MIN_IMAGE_DPI} DPI)",
                detail=f"Found {xres}×{yres} DPI at position ({img.x0:.0f}, {img.y0:.0f})",
            ))

    return violations


# ── Graph axis label check via OCR ────────────────────────────────────────────

def _rasterize_page(pdf_path: Path, page_num: int, dpi: int = 150) -> bytes | None:
    """
    Rasterize a single PDF page to PNG bytes using pdftoppm.
    Returns PNG bytes or None if pdftoppm is unavailable.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_prefix = str(Path(tmpdir) / "page")
            result = subprocess.run(
                [
                    "pdftoppm", "-r", str(dpi),
                    "-f", str(page_num), "-l", str(page_num),
                    "-png", str(pdf_path), out_prefix,
                ],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                return None
            # pdftoppm outputs page-NNNN.png
            import glob
            files = glob.glob(f"{out_prefix}-*.png")
            if not files:
                return None
            return Path(files[0]).read_bytes()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _has_axis_labels_via_ocr(png_bytes: bytes) -> dict:
    """
    Run OCR on a rasterized page and look for typical axis label indicators.
    Returns dict with 'x_axis_ok', 'y_axis_ok', 'ocr_text'.
    """
    if not PIL_AVAILABLE or not TESSERACT_AVAILABLE:
        return {"x_axis_ok": None, "y_axis_ok": None, "ocr_text": ""}

    try:
        with Image.open(io.BytesIO(png_bytes)) as im:
            text = pytesseract.image_to_string(im, config="--psm 6")
    except Exception:
        return {"x_axis_ok": None, "y_axis_ok": None, "ocr_text": ""}

    text_lower = text.lower()

    # Heuristic: check for common axis label words
    x_keywords = ["x-axis", "x axis", "xlabel", "x (", "(x)", "time", "date",
                   "frequency", "input", "epoch", "iteration", "sample"]
    y_keywords = ["y-axis", "y axis", "ylabel", "y (", "(y)", "accuracy",
                   "loss", "value", "count", "score", "rate", "output"]

    x_ok = any(kw in text_lower for kw in x_keywords)
    y_ok = any(kw in text_lower for kw in y_keywords)

    return {"x_axis_ok": x_ok, "y_axis_ok": y_ok, "ocr_text": text[:300]}


def check_graph_axes(doc: ParsedDocument) -> list[Violation]:
    """
    For each page containing an image, rasterize and OCR to check for axis labels.
    Only flags pages that appear to contain chart/graph content.
    """
    violations = []

    if not TESSERACT_AVAILABLE:
        violations.append(Violation(
            category=Category.GRAPHS,
            severity=Severity.INFO,
            page=-1,
            description="pytesseract not available — graph axis label check skipped",
            detail="Install tesseract-ocr and pytesseract to enable this check",
        ))
        return violations

    # Pages with images are candidates for graph checks
    pages_with_images = sorted({img.page_num for img in doc.images})

    for page_num in pages_with_images:
        png_bytes = _rasterize_page(doc.path, page_num)
        if png_bytes is None:
            continue

        result = _has_axis_labels_via_ocr(png_bytes)
        x_ok = result["x_axis_ok"]
        y_ok = result["y_axis_ok"]

        # Only report if we detected what looks like a chart but labels are missing
        # (heuristic: if one axis found but not the other, likely a chart)
        if x_ok is not None and y_ok is not None:
            if x_ok and not y_ok:
                violations.append(Violation(
                    category=Category.GRAPHS,
                    severity=Severity.WARNING,
                    page=page_num,
                    description="Graph may be missing Y-axis label",
                    detail="X-axis label detected but Y-axis label not found via OCR",
                ))
            elif y_ok and not x_ok:
                violations.append(Violation(
                    category=Category.GRAPHS,
                    severity=Severity.WARNING,
                    page=page_num,
                    description="Graph may be missing X-axis label",
                    detail="Y-axis label detected but X-axis label not found via OCR",
                ))

    return violations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_image_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_image_dpi(doc))
    v.extend(check_graph_axes(doc))
    return v
