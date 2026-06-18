"""
checks/chapter_checks.py

Checks:
  1. All 8 mandatory chapters are present
  2. Chapters appear in the correct order
  3. Uses fuzzy matching to handle minor title variations
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


def _find_chapter_in_headings(
    chapter_name: str,
    headings: list[DetectedHeading],
    threshold: float = 0.72,
) -> DetectedHeading | None:
    """Return the best-matching L0/L1 heading for a mandatory chapter name."""
    best_score = 0.0
    best_heading = None

    # Strip leading numbering for comparison
    strip_pattern = re.compile(r"^\d+[\.\s]+")

    for h in headings:
        if h.level not in (0, 1):
            continue
        clean_text = strip_pattern.sub("", h.text).strip()
        score = _similarity(chapter_name, clean_text)
        if score > best_score:
            best_score = score
            best_heading = h

    return best_heading if best_score >= threshold else None


def run_chapter_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []
    headings = extract_headings(doc)

    found_chapters: list[tuple[str, DetectedHeading]] = []

    for chapter in MANDATORY_CHAPTERS:
        match = _find_chapter_in_headings(chapter, headings)
        if match is None:
            violations.append(Violation(
                category=Category.CHAPTERS,
                severity=Severity.ERROR,
                page=-1,
                description=f"Mandatory chapter missing: '{chapter}'",
                detail="Not found in document headings (checked L0 and L1 headings)",
            ))
        else:
            found_chapters.append((chapter, match))

    # Check order
    if len(found_chapters) > 1:
        pages = [h.page_num for _, h in found_chapters]
        for i in range(1, len(pages)):
            if pages[i] < pages[i - 1]:
                c_curr = found_chapters[i][0]
                c_prev = found_chapters[i - 1][0]
                violations.append(Violation(
                    category=Category.CHAPTERS,
                    severity=Severity.ERROR,
                    page=pages[i],
                    description="Mandatory chapters are out of order",
                    detail=f"'{c_curr}' (p.{pages[i]}) appears before '{c_prev}' (p.{pages[i-1]})",
                ))

    if not violations:
        # All 8 chapters present and in order
        pass

    return violations
