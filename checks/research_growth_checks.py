"""
checks/research_growth_checks.py

Analyzes and reports research growth indicators:
  1. Reference count and year distribution
  2. Citations per chapter
  3. Figures/tables per chapter
  4. Word count growth across chapters
"""
from __future__ import annotations

import re
from collections import defaultdict

from checks.heading_checks import extract_headings
from checks.citation_checks import _extract_bibliography_text, _parse_bib_entries
from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    INTEXT_CITATION_PATTERN, NUMERIC_CITATION_PATTERN,
    FIGURE_CAPTION_PATTERN, TABLE_CAPTION_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def _chapter_ranges(doc: ParsedDocument) -> list[tuple[int, str, int, int]]:
    """Return list of (chapter_num, title, start_page, end_page) for content chapters."""
    headings = extract_headings(doc)
    l0 = [h for h in headings if h.level == 0]

    content_chapters = []
    for h in l0:
        text = h.text.strip().upper()
        if text.startswith("CHAPTER") or any(
            ch.upper() in text for ch in [
                "INTRODUCTION", "PROJECT DESCRIPTION", "TECHNICAL SPECIFICATION",
                "SYSTEM DESIGN", "METHODOLOGY", "PROJECT IMPLEMENTATION",
                "RESULTS AND DISCUSSION", "CONCLUSION",
            ]
        ):
            content_chapters.append(h)

    if not content_chapters:
        return [(1, "Document", 1, doc.page_count)]

    ranges = []
    for idx, h in enumerate(content_chapters):
        start = h.page_num
        end = (
            content_chapters[idx + 1].page_num - 1
            if idx + 1 < len(content_chapters)
            else doc.page_count
        )
        ranges.append((idx + 1, h.text[:50], start, max(start, end)))
    return ranges


def _count_citations_in_range(doc: ParsedDocument, start: int, end: int) -> int:
    count = 0
    for page_idx in range(start - 1, min(end, doc.page_count)):
        text = doc.raw_text_by_page[page_idx]
        count += len(INTEXT_CITATION_PATTERN.findall(text))
        count += len(NUMERIC_CITATION_PATTERN.findall(text))
    return count


def _count_figures_tables_in_range(doc: ParsedDocument, start: int, end: int) -> tuple[int, int]:
    figures = tables = 0
    for page_idx in range(start - 1, min(end, doc.page_count)):
        text = doc.raw_text_by_page[page_idx]
        figures += len(FIGURE_CAPTION_PATTERN.findall(text))
        tables += len(TABLE_CAPTION_PATTERN.findall(text))
    return figures, tables


def _word_count_in_range(doc: ParsedDocument, start: int, end: int) -> int:
    words = 0
    for page_idx in range(start - 1, min(end, doc.page_count)):
        words += len(doc.raw_text_by_page[page_idx].split())
    return words


def run_research_growth_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []

    bib_text, bib_page = _extract_bibliography_text(doc)
    bib_entries = _parse_bib_entries(bib_text) if bib_text else []
    ref_count = len(bib_entries)

    year_counts: dict[str, int] = defaultdict(int)
    for entry in bib_entries:
        for year_m in YEAR_PATTERN.finditer(entry):
            year_counts[year_m.group()] += 1

    violations.append(Violation(
        category=Category.RESEARCH,
        severity=Severity.INFO,
        page=-1,
        description="Total bibliography references",
        detail=f"{ref_count} reference(s) found" + (f" starting p.{bib_page}" if bib_page > 0 else ""),
    ))

    if year_counts:
        sorted_years = sorted(year_counts.items())
        year_summary = ", ".join(f"{y}: {c}" for y, c in sorted_years[-8:])
        recent = sum(c for y, c in year_counts.items() if int(y) >= 2020)
        older = ref_count - recent
        growth_note = (
            f"Recent (2020+): {recent}, Older: {older}"
            if ref_count else ""
        )
        violations.append(Violation(
            category=Category.RESEARCH,
            severity=Severity.INFO,
            page=-1,
            description="Reference year distribution",
            detail=f"{year_summary}. {growth_note}".strip(),
        ))

        if len(sorted_years) >= 2:
            first_half = sum(c for y, c in sorted_years[: len(sorted_years) // 2])
            second_half = sum(c for y, c in sorted_years[len(sorted_years) // 2 :])
            trend = "increasing" if second_half > first_half else (
                "stable" if second_half == first_half else "decreasing"
            )
            violations.append(Violation(
                category=Category.RESEARCH,
                severity=Severity.INFO,
                page=-1,
                description=f"Research growth trend: {trend}",
                detail=f"Earlier years: {first_half} refs, Later years: {second_half} refs",
            ))

    chapter_ranges = _chapter_ranges(doc)
    prev_words = 0
    for ch_num, title, start, end in chapter_ranges:
        citations = _count_citations_in_range(doc, start, end)
        figures, tables = _count_figures_tables_in_range(doc, start, end)
        words = _word_count_in_range(doc, start, end)

        violations.append(Violation(
            category=Category.RESEARCH,
            severity=Severity.INFO,
            page=start,
            description=f"Chapter {ch_num} research metrics",
            detail=(
                f"'{title}': {words} words, {citations} citations, "
                f"{figures} figure(s), {tables} table(s)"
            ),
            location=title,
        ))

        if prev_words > 0 and words > prev_words * 1.5 and words > 200:
            violations.append(Violation(
                category=Category.RESEARCH,
                severity=Severity.INFO,
                page=start,
                description="Notable content growth between chapters",
                detail=f"Chapter {ch_num} word count ({words}) is >50% higher than previous ({prev_words})",
            ))
        prev_words = words

    total_citations = sum(_count_citations_in_range(doc, s, e) for _, _, s, e in chapter_ranges)
    if ref_count and total_citations:
        ratio = total_citations / ref_count
        violations.append(Violation(
            category=Category.RESEARCH,
            severity=Severity.INFO,
            page=-1,
            description="Citation-to-reference ratio",
            detail=f"{total_citations} in-text citations / {ref_count} bibliography entries = {ratio:.1f}×",
        ))

    return violations
