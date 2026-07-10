"""
checks/subtopic_checks.py

Checks:
  1. Long sections under L1 headings are separated by L2/L3 subtopic headings
  2. Subtopic numbering aligns with parent chapter
  3. Each major chapter has at least one subtopic when content is substantial
"""
from __future__ import annotations

import re

from checks.heading_checks import extract_headings
from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    MIN_LINES_FOR_SUBTOPICS, MIN_WORDS_FOR_SUBTOPICS,
    HEADER_ZONE_PT, FOOTER_ZONE_PT,
    Severity, Category,
)
from utils.error_model import Violation


def _count_body_content(doc: ParsedDocument, start_page: int, start_y: float,
                        end_page: int, end_y: float) -> tuple[int, int]:
    """Return (line_count, word_count) for body text in a section range."""
    line_count = 0
    word_count = 0

    for line in doc.lines:
        if line.page_num < start_page or line.page_num > end_page:
            continue
        if line.page_num == start_page and line.top <= start_y:
            continue
        if line.page_num == end_page and line.top >= end_y:
            continue

        page_h = doc.page_sizes[line.page_num - 1][1] if line.page_num <= len(doc.page_sizes) else 841.89
        if line.top < HEADER_ZONE_PT or line.top > (page_h - FOOTER_ZONE_PT):
            continue

        text = line.text.strip()
        if len(text) < 5:
            continue
        if re.match(r"^\d+$", text):
            continue

        line_count += 1
        word_count += len(text.split())

    return line_count, word_count


def check_subtopic_separation(doc: ParsedDocument) -> list[Violation]:
    """
    Flag L1 sections that contain substantial content but no L2/L3 subtopic headings.
    """
    violations = []
    headings = extract_headings(doc)

    for idx, h in enumerate(headings):
        if h.level != 1:
            continue

        end_page, end_y = doc.page_count, float("inf")
        for next_h in headings[idx + 1:]:
            # A section under an L1 heading ends at the next L0 (new chapter) or L1 heading.
            if next_h.level in (0, 1):
                end_page, end_y = next_h.page_num, next_h.line.top
                break

        subtopics_in_section = [
            sh for sh in headings[idx + 1:]
            if sh.level in (2, 3)
            and sh.page_num >= h.page_num
            and (sh.page_num < end_page or (sh.page_num == end_page and sh.line.top < end_y))
        ]

        lines, words = _count_body_content(
            doc, h.page_num, h.line.top, end_page, end_y
        )

        if (lines >= MIN_LINES_FOR_SUBTOPICS or words >= MIN_WORDS_FOR_SUBTOPICS) and not subtopics_in_section:
            violations.append(Violation(
                category=Category.SUBTOPICS,
                severity=Severity.WARNING,
                page=h.page_num,
                description="Long section lacks subtopic headings",
                detail=(
                    f"Section '{h.text[:50]}' has ~{words} words / {lines} lines "
                    f"but no L2/L3 subtopic headings to separate content"
                ),
                location=h.text[:60],
                bbox=(h.line.x0, h.line.top, h.line.x1, h.line.bottom),
            ))

    return violations


def check_subtopic_numbering(doc: ParsedDocument) -> list[Violation]:
    """L2 headings should share the chapter prefix of their parent L1 heading."""
    violations = []
    headings = extract_headings(doc)
    current_l1_chapter = None

    l1_pattern = re.compile(r"^(\d+)\.\d+")
    l2_pattern = re.compile(r"^(\d+)\.\d+\.\d+")

    for h in headings:
        if h.level == 1:
            m = l1_pattern.match(h.text.strip())
            current_l1_chapter = int(m.group(1)) if m else None

        elif h.level == 2 and current_l1_chapter is not None:
            m = l2_pattern.match(h.text.strip())
            if m:
                sub_ch = int(m.group(1))
                if sub_ch != current_l1_chapter:
                    violations.append(Violation(
                        category=Category.SUBTOPICS,
                        severity=Severity.WARNING,
                        page=h.page_num,
                        description="Subtopic chapter number does not match parent section",
                        detail=f"Subtopic '{h.text[:50]}' uses chapter {sub_ch}, expected {current_l1_chapter}",
                        location=h.text[:60],
                        bbox=(h.line.x0, h.line.top, h.line.x1, h.line.bottom),
                    ))

    return violations


def run_subtopic_checks(doc: ParsedDocument) -> list[Violation]:
    v = []
    v.extend(check_subtopic_separation(doc))
    v.extend(check_subtopic_numbering(doc))
    return v
