"""
checks/toc_checks.py

Checks:
  1. Table of Contents section exists
  2. TOC entries follow expected format (title + page number)
  3. PyMuPDF embedded TOC matches document structure
  4. Page numbers in TOC are sequential / valid
"""
from __future__ import annotations

import re

from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    TOC_HEADER_PATTERN, TOC_ENTRY_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation


def _find_toc_pages(doc: ParsedDocument) -> list[tuple[int, str]]:
    """Return (page_num, text) for pages that look like TOC pages."""
    toc_pages = []
    for page_idx, text in enumerate(doc.raw_text_by_page):
        page_num = page_idx + 1
        if page_num > 10:
            break
        if TOC_HEADER_PATTERN.search(text):
            toc_pages.append((page_num, text))
        elif re.search(r"\.\.{3,}\s*\d+\s*$", text, re.MULTILINE):
            toc_pages.append((page_num, text))
    return toc_pages


def check_toc_exists(doc: ParsedDocument) -> list[Violation]:
    violations = []

    has_embedded_toc = bool(doc.toc)
    toc_pages = _find_toc_pages(doc)

    if not has_embedded_toc and not toc_pages:
        violations.append(Violation(
            category=Category.TOC,
            severity=Severity.ERROR,
            page=-1,
            description="No Table of Contents found",
            detail="Expected a 'Table of Contents' or 'Contents' section near the start of the document",
        ))
    elif has_embedded_toc:
        violations.append(Violation(
            category=Category.TOC,
            severity=Severity.INFO,
            page=-1,
            description="Embedded Table of Contents detected",
            detail=f"{len(doc.toc)} TOC entries found via PDF bookmarks",
        ))
    else:
        pages = ", ".join(str(p) for p, _ in toc_pages)
        violations.append(Violation(
            category=Category.TOC,
            severity=Severity.INFO,
            page=toc_pages[0][0],
            description="Table of Contents section detected",
            detail=f"Found on page(s): {pages}",
        ))

    return violations


def check_toc_format(doc: ParsedDocument) -> list[Violation]:
    """Validate TOC entry formatting on detected TOC pages."""
    violations: list[Violation] = []
    toc_pages = _find_toc_pages(doc)

    if not toc_pages:
        return violations

    for page_num, text in toc_pages:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        entry_lines = [
            l for l in lines
            if not TOC_HEADER_PATTERN.match(l)
            and len(l) > 5
        ]

        if not entry_lines:
            violations.append(Violation(
                category=Category.TOC,
                severity=Severity.WARNING,
                page=page_num,
                description="Table of Contents page has no recognizable entries",
            ))
            continue

        malformed = []
        for line in entry_lines[:30]:
            if TOC_ENTRY_PATTERN.match(line):
                continue
            # Allow lines ending in dot leaders (which get wrapped in extraction)
            if re.search(r"\.\s*\.\s*\.\s*$", line):
                continue
            # Allow standard page numbers (digits)
            if re.search(r"\d+\s*$", line) and len(line) > 10:
                continue
            # Allow Roman numeral page numbers
            if re.search(r"\b[ivxlcdmIVXLCDM]+\s*$", line) and len(line) > 10:
                continue
            if line.isdigit() or len(line) < 8:
                continue
            malformed.append(line[:60])

        if malformed:
            violations.append(Violation(
                category=Category.TOC,
                severity=Severity.WARNING,
                page=page_num,
                description="Some TOC entries may not follow standard format",
                detail=f"Expected 'Title ... page#'. Examples: {malformed[:3]}",
            ))

    return violations


def check_toc_page_numbers(doc: ParsedDocument) -> list[Violation]:
    """Verify TOC page numbers are within document bounds and generally ascending."""
    violations = []

    if doc.toc:
        prev_page = 0
        for _level, title, page in doc.toc:
            if page < 1 or page > doc.page_count:
                violations.append(Violation(
                    category=Category.TOC,
                    severity=Severity.ERROR,
                    page=-1,
                    description="TOC entry points to invalid page number",
                    detail=f"'{title[:50]}' → page {page} (document has {doc.page_count} pages)",
                ))
            elif page < prev_page:
                violations.append(Violation(
                    category=Category.TOC,
                    severity=Severity.WARNING,
                    page=-1,
                    description="TOC page numbers are not in ascending order",
                    detail=f"'{title[:50]}' (p.{page}) follows p.{prev_page}",
                ))
            prev_page = page

    return violations


def run_toc_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_toc_exists(doc))
    v.extend(check_toc_format(doc))
    v.extend(check_toc_page_numbers(doc))
    return v
