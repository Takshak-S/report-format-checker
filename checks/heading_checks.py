"""
checks/heading_checks.py

Checks:
  1. Heading levels detected via font size + pattern
  2. Sequential decimal numbering (1.1, 1.2 ... not 1.1, 1.3)
  3. Case rules: L0 = UPPERCASE, L1 = UPPERCASE, L2 = Title Case
  4. Chapter titles start on a new page
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from ingestion.pdf_loader import ParsedDocument, LineInfo
from utils.constants import (
    FONT_SIZE_HEADING_L0, FONT_SIZE_HEADING_L1, FONT_SIZE_BODY,
    FONT_SIZE_TOLERANCE,
    HEADING_L0_PATTERN, HEADING_L1_PATTERN, HEADING_L2_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation


@dataclass
class DetectedHeading:
    level:    int       # 0, 1, 2, 3
    text:     str
    page_num: int
    line:     LineInfo


# ── Heading detection ─────────────────────────────────────────────────────────

def _detect_heading_level(line: LineInfo) -> int | None:
    """
    Return heading level (0–3) or None for body text.
    Detection priority: size → pattern → style.
    """
    text = line.text.strip()
    if not text or len(text) < 2:
        return None

    size = line.size or 0

    # Level 0: 16 pt, UPPERCASE, no decimal prefix
    if abs(size - FONT_SIZE_HEADING_L0) <= FONT_SIZE_TOLERANCE:
        if HEADING_L0_PATTERN.fullmatch(text):
            return 0

    # Level 1: 14 pt, bold, decimal prefix + UPPERCASE
    if abs(size - FONT_SIZE_HEADING_L1) <= FONT_SIZE_TOLERANCE:
        if HEADING_L1_PATTERN.match(text):
            return 1
        # Also catch 14 pt uppercase lines without numbering
        if text.isupper() and len(text) > 4:
            return 1

    # Level 2: 12 pt, Title Case, two-decimal prefix
    if abs(size - FONT_SIZE_BODY) <= FONT_SIZE_TOLERANCE:
        if HEADING_L2_PATTERN.match(text):
            return 2
        # Bold+italic at 12pt → Level 3
        if line.bold and line.italic:
            return 3

    return None


def extract_headings(doc: ParsedDocument) -> list[DetectedHeading]:
    headings = []
    for line in doc.lines:
        level = _detect_heading_level(line)
        if level is not None:
            headings.append(DetectedHeading(
                level=level,
                text=line.text.strip(),
                page_num=line.page_num,
                line=line,
            ))
    return headings


# ── Numbering continuity check ────────────────────────────────────────────────

def check_heading_numbering(headings: list[DetectedHeading]) -> list[Violation]:
    """Verify decimal numbering is sequential (no skips, no repeats)."""
    violations = []

    # Track last seen counters: {chapter: {section: last_subsection}}
    last_l1_per_chapter: dict[int, int] = {}   # chapter_num → last l1 number
    last_l2_per_section: dict[tuple, int] = {}  # (ch, sec) → last l2 number
    current_chapter = 0

    l1_pattern = re.compile(r"^(\d+)\.(\d+)")
    l2_pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

    for h in headings:
        text = h.text.strip()

        if h.level == 0:
            current_chapter += 1
            continue

        if h.level == 1:
            m = l1_pattern.match(text)
            if not m:
                continue
            ch, sec = int(m.group(1)), int(m.group(2))
            prev_sec = last_l1_per_chapter.get(ch, 0)
            if sec != prev_sec + 1:
                violations.append(Violation(
                    category=Category.HEADINGS,
                    severity=Severity.WARNING,
                    page=h.page_num,
                    description=f"Heading numbering gap or repeat at level 1",
                    detail=f"Expected {ch}.{prev_sec + 1}, found '{text[:50]}'",
                ))
            last_l1_per_chapter[ch] = sec

        elif h.level == 2:
            m = l2_pattern.match(text)
            if not m:
                continue
            ch, sec, subsec = int(m.group(1)), int(m.group(2)), int(m.group(3))
            key = (ch, sec)
            prev_subsec = last_l2_per_section.get(key, 0)
            if subsec != prev_subsec + 1:
                violations.append(Violation(
                    category=Category.HEADINGS,
                    severity=Severity.WARNING,
                    page=h.page_num,
                    description=f"Heading numbering gap or repeat at level 2",
                    detail=f"Expected {ch}.{sec}.{prev_subsec + 1}, found '{text[:50]}'",
                ))
            last_l2_per_section[key] = subsec

    return violations


# ── Case rules check ──────────────────────────────────────────────────────────

def check_heading_case(headings: list[DetectedHeading]) -> list[Violation]:
    violations = []
    for h in headings:
        text = h.text.strip()

        if h.level == 0:
            # Strip heading number prefix if any, check rest is uppercase
            body = re.sub(r"^\d+[\.\s]*", "", text)
            if not body.isupper():
                violations.append(Violation(
                    category=Category.HEADINGS,
                    severity=Severity.WARNING,
                    page=h.page_num,
                    description="Chapter title (L0) must be UPPERCASE",
                    location=text[:60],
                ))

        elif h.level == 1:
            # e.g. "1.1 INTRODUCTION" — part after number must be uppercase
            m = re.match(r"^\d+\.\d+\s+(.*)", text)
            if m:
                heading_body = m.group(1)
                if not heading_body.isupper():
                    violations.append(Violation(
                        category=Category.HEADINGS,
                        severity=Severity.WARNING,
                        page=h.page_num,
                        description="Level-1 heading must be UPPERCASE after decimal",
                        location=text[:60],
                    ))

        elif h.level == 2:
            # Title Case check — each word should start with uppercase
            m = re.match(r"^\d+\.\d+\.\d+\s+(.*)", text)
            if m:
                heading_body = m.group(1)
                words = heading_body.split()
                non_title = [w for w in words if w and w[0].islower() and len(w) > 3]
                if non_title:
                    violations.append(Violation(
                        category=Category.HEADINGS,
                        severity=Severity.INFO,
                        page=h.page_num,
                        description="Level-2 heading should use Title Case",
                        detail=f"Lowercase words: {non_title[:5]}",
                        location=text[:60],
                    ))

    return violations


# ── New-page check for L0 chapters ───────────────────────────────────────────

def check_chapter_new_page(headings: list[DetectedHeading], doc: ParsedDocument) -> list[Violation]:
    """
    Level-0 chapter titles should be the first significant content on their page.
    Heuristic: check if any content exists on the same page above the heading.
    """
    violations = []
    l0_headings = [h for h in headings if h.level == 0]

    for h in l0_headings:
        page_lines = doc.lines_on_page(h.page_num)
        # Lines above this heading on the same page
        lines_above = [l for l in page_lines if l.top < h.line.top - 20]
        # Filter out page numbers (very short, near bottom of previous group)
        significant_above = [l for l in lines_above if len(l.text.strip()) > 5]
        if significant_above:
            violations.append(Violation(
                category=Category.HEADINGS,
                severity=Severity.WARNING,
                page=h.page_num,
                description="Chapter title (L0) should start on a new page",
                detail=f"Found {len(significant_above)} content lines above it on page {h.page_num}",
                location=h.text[:60],
            ))

    return violations


# ── Main entry point ──────────────────────────────────────────────────────────

def run_heading_checks(doc: ParsedDocument) -> list[Violation]:
    headings = extract_headings(doc)
    v = []
    v.extend(check_heading_numbering(headings))
    v.extend(check_heading_case(headings))
    v.extend(check_chapter_new_page(headings, doc))
    return v
