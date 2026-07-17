"""
checks/chapter_checks.py

Checks:
  1. All 8 mandatory chapters are present
  2. Chapters appear in the correct order
  3. Uses fuzzy matching to handle minor title variations
  4. Cross-references against PyMuPDF TOC for better detection
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ingestion.pdf_loader import ParsedDocument
from checks.heading_checks import extract_headings, DetectedHeading
from utils.constants import MANDATORY_CHAPTERS, Severity, Category
from utils.error_model import Violation


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_chapter_text(text: str) -> str:
    """
    Strip common prefixes like 'Chapter 1:', '1.', etc.
    and trailing whitespace/punctuation for cleaner matching.
    """
    # Strip "Chapter N" or "CHAPTER N" prefix
    text = re.sub(r"^(?:chapter\s+\d+[\s.:–-]*)", "", text, flags=re.IGNORECASE)
    # Strip leading numbering
    text = re.sub(r"^\d+[.\s]+", "", text)
    return text.strip().rstrip(".:–-").strip()


def _find_chapter_in_headings(
    chapter_name: str,
    headings: list[DetectedHeading],
    threshold: float = 0.65,   # lowered from 0.72 for more tolerance
) -> DetectedHeading | None:
    """
    Return the best-matching L0/L1 heading for a mandatory chapter name.
    Also handles two-line chapter titles (e.g., "CHAPTER 1" + "INTRODUCTION").
    """
    best_score = 0.0
    best_heading = None

    for idx, h in enumerate(headings):
        if h.level not in (0, 1):
            continue
        clean_text = _normalize_chapter_text(h.text)
        score = _similarity(chapter_name, clean_text)

        # If current heading is a "CHAPTER N" line, try merging with the next heading
        if re.match(r"^CHAPTER\s*\d+\s*$", h.text.strip(), re.IGNORECASE) and idx + 1 < len(headings):
            next_h = headings[idx + 1]
            if next_h.level in (0, 1) and next_h.page_num == h.page_num:
                merged_text = _normalize_chapter_text(next_h.text)
                merged_score = _similarity(chapter_name, merged_text)
                if merged_score > score:
                    score = merged_score
                    if score > best_score:
                        best_score = score
                        best_heading = next_h
                    continue

        if score > best_score:
            best_score = score
            best_heading = h

    return best_heading if best_score >= threshold else None


def _find_chapter_in_toc(
    chapter_name: str,
    toc: list[tuple[int, str, int]],
    threshold: float = 0.65,
) -> tuple[str, int] | None:
    """
    Search PyMuPDF's TOC for a matching chapter entry.
    Returns (toc_title, page_num) or None.
    """
    best_score = 0.0
    best_entry = None

    for level, title, page in toc:
        if level > 2:   # only check top-level TOC entries
            continue
        clean_title = _normalize_chapter_text(title)
        score = _similarity(chapter_name, clean_title)
        if score > best_score:
            best_score = score
            best_entry = (title, page)

    return best_entry if best_score >= threshold else None


def run_chapter_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []
    headings = extract_headings(doc)

    found_chapters: list[tuple[str, int]] = []   # (chapter_name, page_num)

    for chapter in MANDATORY_CHAPTERS:
        # First try heading detection
        match = _find_chapter_in_headings(chapter, headings)
        if match is not None:
            found_chapters.append((chapter, match.page_num))
            continue

        # Fallback: try TOC entries
        if doc.toc:
            toc_match = _find_chapter_in_toc(chapter, doc.toc)
            if toc_match is not None:
                found_chapters.append((chapter, toc_match[1]))
                continue

        # Not found anywhere
        violations.append(Violation(
            category=Category.CHAPTERS,
            severity=Severity.CRITICAL,
            page=-1,
            description=f"Mandatory chapter missing: '{chapter}'",
            detail="Not found in document headings or table of contents",
        ))

    # Check order
    if len(found_chapters) > 1:
        pages = [page for _, page in found_chapters]
        for i in range(1, len(pages)):
            if pages[i] < pages[i - 1]:
                c_curr = found_chapters[i][0]
                c_prev = found_chapters[i - 1][0]
                violations.append(Violation(
                    category=Category.CHAPTERS,
                    severity=Severity.CRITICAL,
                    page=pages[i],
                    description="Mandatory chapters are out of order",
                    detail=f"'{c_curr}' (p.{pages[i]}) appears before '{c_prev}' (p.{pages[i-1]})",
                ))

    return violations
