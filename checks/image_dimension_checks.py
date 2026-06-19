"""
checks/image_dimension_checks.py

Checks:
  1. Significant images meet minimum rendered size on page
  2. Images do not exceed maximum page coverage ratio
  3. Pixel dimensions reported for quality assessment
"""
from __future__ import annotations

from ingestion.pdf_loader import ParsedDocument, ImageInfo
from utils.constants import (
    MIN_IMAGE_RENDERED_PT, MAX_IMAGE_PAGE_RATIO, MIN_IMAGE_PIXELS,
    Severity, Category,
)
from utils.error_model import Violation


def _is_decorative(img: ImageInfo) -> bool:
    rendered_w = img.x1 - img.x0
    rendered_h = img.y1 - img.y0
    if img.width_px < 20 or img.height_px < 20:
        return True
    if rendered_w < 20 or rendered_h < 20:
        return True
    if rendered_w * rendered_h < 5184:
        return True
    return False


def check_image_rendered_dimensions(doc: ParsedDocument) -> list[Violation]:
    violations = []

    for img in doc.images:
        if _is_decorative(img):
            continue

        rendered_w = img.x1 - img.x0
        rendered_h = img.y1 - img.y0
        page_w, page_h = doc.page_sizes[img.page_num - 1]

        if rendered_w < MIN_IMAGE_RENDERED_PT or rendered_h < MIN_IMAGE_RENDERED_PT:
            violations.append(Violation(
                category=Category.IMAGE_DIMS,
                severity=Severity.WARNING,
                page=img.page_num,
                description="Image rendered size may be too small for clarity",
                detail=(
                    f"Rendered {rendered_w:.0f}×{rendered_h:.0f} pt "
                    f"(min {MIN_IMAGE_RENDERED_PT:.0f} pt per side)"
                ),
            ))

        if rendered_w > page_w * MAX_IMAGE_PAGE_RATIO or rendered_h > page_h * MAX_IMAGE_PAGE_RATIO:
            violations.append(Violation(
                category=Category.IMAGE_DIMS,
                severity=Severity.WARNING,
                page=img.page_num,
                description="Image exceeds recommended page coverage",
                detail=(
                    f"Rendered {rendered_w:.0f}×{rendered_h:.0f} pt on "
                    f"{page_w:.0f}×{page_h:.0f} pt page (max {MAX_IMAGE_PAGE_RATIO:.0%})"
                ),
            ))

    return violations


def check_image_pixel_dimensions(doc: ParsedDocument) -> list[Violation]:
    violations = []

    for img in doc.images:
        if _is_decorative(img):
            continue

        if img.width_px < MIN_IMAGE_PIXELS or img.height_px < MIN_IMAGE_PIXELS:
            violations.append(Violation(
                category=Category.IMAGE_DIMS,
                severity=Severity.ERROR,
                page=img.page_num,
                description="Image pixel dimensions below minimum quality threshold",
                detail=f"Found {img.width_px}×{img.height_px} px (min {MIN_IMAGE_PIXELS} px per side)",
            ))
        else:
            rendered_w = img.x1 - img.x0
            rendered_h = img.y1 - img.y0
            violations.append(Violation(
                category=Category.IMAGE_DIMS,
                severity=Severity.INFO,
                page=img.page_num,
                description="Image dimensions recorded",
                detail=(
                    f"Pixels: {img.width_px}×{img.height_px}, "
                    f"Rendered: {rendered_w:.0f}×{rendered_h:.0f} pt"
                ),
            ))

    return violations


def run_image_dimension_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_image_rendered_dimensions(doc))
    v.extend(check_image_pixel_dimensions(doc))
    return v
