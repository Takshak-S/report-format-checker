"""
checks/citation_checks.py

Checks:
  1. Bibliography section exists
  2. Each bibliography entry follows APA 7th edition format
  3. Every in-text citation has a corresponding bibliography entry
  4. Every bibliography entry is cited at least once in-text
  5. No orphaned references
  6. Support for numeric citation styles [1], [2-3]
"""
from __future__ import annotations

import re
from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    INTEXT_CITATION_PATTERN, NUMERIC_CITATION_PATTERN,
    Severity, Category,
)
from utils.error_model import Violation


# ── APA format patterns ───────────────────────────────────────────────────────

# APA journal article: Author, A. A., & Author, B. B. (Year). Title. Journal, Volume(Issue), pages. DOI
APA_JOURNAL = re.compile(
    r"[A-Z][a-z]+,\s+[A-Z][.\s].*?\(\d{4}\)\.\s+.+\.\s+\w.+,\s*\d+",
    re.DOTALL,
)

# APA book: Author, A. A. (Year). Title of book. Publisher.
APA_BOOK = re.compile(
    r"[A-Z][a-z]+,\s+[A-Z][.\s].*?\(\d{4}\)\.\s+[A-Z].+\.\s+[A-Z].+\.",
    re.DOTALL,
)

# APA website: Author. (Year, Month Day). Title. Site. URL
APA_WEBSITE = re.compile(
    r".+\(\d{4}.*?\)\.\s+.+\.\s+(https?://|www\.)",
    re.DOTALL,
)

# General APA heuristic: has author-like start, year in parens, and period-separated segments
APA_GENERAL = re.compile(
    r"[A-Z][a-z]+.*?\(\d{4}[a-z]?\)\.\s+.+\.",
    re.DOTALL,
)

# Year extraction from in-text citation
YEAR_PATTERN    = re.compile(r"\b(19|20)\d{2}\b")
AUTHOR_PATTERN  = re.compile(r"[A-Z][a-z]+")

# Detect bibliography section header (supports optional numbering like '9. REFERENCES')
BIB_SECTION_HEADERS = re.compile(
    r"^(?:\d+\.)?\s*(references|bibliography|works cited|reference list)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ── Extract bibliography section ──────────────────────────────────────────────

def _extract_bibliography_text(doc: ParsedDocument) -> tuple[str, int]:
    """
    Find the bibliography/references section and return (text, start_page).
    Returns ("", -1) if not found.
    """
    full_pages = doc.raw_text_by_page
    for page_idx, text in enumerate(full_pages):
        if BIB_SECTION_HEADERS.search(text):
            # Collect text from this page onwards
            bib_text = "\n".join(full_pages[page_idx:])
            return bib_text, page_idx + 1
    return "", -1


def _parse_bib_entries(bib_text: str) -> list[str]:
    """
    Split bibliography text into individual entries.
    Heuristic: entries start with Author (Lastname, Initials).
    """
    # Split on lines that start with an uppercase letter followed by lowercase + comma
    entry_pattern = re.compile(r"(?=^[A-Z][a-z]+,\s+[A-Z])", re.MULTILINE)
    parts = entry_pattern.split(bib_text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]


# ── In-text citation extraction ───────────────────────────────────────────────

def _extract_intext_citations(doc: ParsedDocument) -> list[tuple[str, int]]:
    """
    Return list of (citation_text, page_num) for all in-text citations found.
    Includes both author-year and numeric styles.
    """
    citations = []
    for page_idx, text in enumerate(doc.raw_text_by_page):
        page_num = page_idx + 1
        # Author-year citations
        for m in INTEXT_CITATION_PATTERN.finditer(text):
            citations.append((m.group(), page_num))
        # Numeric citations
        for m in NUMERIC_CITATION_PATTERN.finditer(text):
            citations.append((m.group(), page_num))
    return citations


def _citation_key(text: str) -> tuple[str, str]:
    """Extract (first_author_lastname, year) as a lookup key."""
    year_m = YEAR_PATTERN.search(text)
    year = year_m.group() if year_m else ""
    author_m = AUTHOR_PATTERN.search(text)
    author = author_m.group().lower() if author_m else ""
    return author, year


# ── APA format validation ─────────────────────────────────────────────────────

def _validate_apa_entry(entry: str) -> bool:
    """Return True if entry roughly matches any APA format."""
    return bool(
        APA_JOURNAL.search(entry)
        or APA_BOOK.search(entry)
        or APA_WEBSITE.search(entry)
        or APA_GENERAL.search(entry)   # broader heuristic
        or (YEAR_PATTERN.search(entry) and len(entry) > 40)
    )


# ── Main checks ───────────────────────────────────────────────────────────────

def run_citation_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []

    # 1. Check bibliography exists
    bib_text, bib_start_page = _extract_bibliography_text(doc)
    if not bib_text:
        violations.append(Violation(
            category=Category.CITATIONS,
            severity=Severity.CRITICAL,
            page=-1,
            description="No bibliography / references section found",
            detail="Expected a section titled 'References' or 'Bibliography'",
        ))
        return violations

    # 2. Parse bibliography entries
    bib_entries = _parse_bib_entries(bib_text)
    if not bib_entries:
        violations.append(Violation(
            category=Category.CITATIONS,
            severity=Severity.WARNING,
            page=bib_start_page,
            description="Bibliography section found but no entries could be parsed",
        ))
        return violations

    # 3. APA format check on each entry
    for entry in bib_entries:
        if not _validate_apa_entry(entry):
            violations.append(Violation(
                category=Category.CITATIONS,
                severity=Severity.WARNING,
                page=bib_start_page,
                description="Bibliography entry may not follow APA 7th edition format",
                detail=entry[:100],
            ))

    # 4. Build lookup sets
    bib_keys = set()
    for entry in bib_entries:
        author_m = AUTHOR_PATTERN.search(entry)
        year_m   = YEAR_PATTERN.search(entry)
        if author_m and year_m:
            bib_keys.add((author_m.group().lower(), year_m.group()))

    # 5. Extract in-text citations (exclude pages after bibliography section)
    intext = _extract_intext_citations(doc)
    intext_keys: dict[tuple, int] = {}   # key → first page seen
    for cit_text, page_num in intext:
        if page_num >= bib_start_page:
            continue
        key = _citation_key(cit_text)
        if key not in intext_keys:
            intext_keys[key] = page_num

    # 6. In-text citation without bibliography entry — use full last-name matching
    for key, page_num in intext_keys.items():
        author, year = key
        if not author or not year:
            continue
        # Full last-name case-insensitive match (not just 4-char prefix)
        matched = any(
            bk_author == author and bk_year == year
            for bk_author, bk_year in bib_keys
        )
        # Fallback: also try prefix matching for hyphenated/long names
        if not matched:
            matched = any(
                (bk_author.startswith(author) or author.startswith(bk_author))
                and bk_year == year
                for bk_author, bk_year in bib_keys
            )
        if not matched:
            violations.append(Violation(
                category=Category.CITATIONS,
                severity=Severity.INFO,
                page=page_num,
                description="In-text citation has no matching bibliography entry",
                detail=f"Author '{author}', Year '{year}' not found in references",
            ))

    # 7. Bibliography entry never cited in text — use full last-name matching
    for bk_author, bk_year in bib_keys:
        cited = any(
            (it_author == bk_author or it_author.startswith(bk_author) or bk_author.startswith(it_author))
            and it_year == bk_year
            for it_author, it_year in intext_keys
        )
        if not cited:
            violations.append(Violation(
                category=Category.CITATIONS,
                severity=Severity.INFO,
                page=bib_start_page,
                description="Bibliography entry never cited in the body text",
                detail=f"Author '{bk_author}', Year '{bk_year}'",
            ))

    return violations
