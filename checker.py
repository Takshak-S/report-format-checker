"""
checker.py

Orchestrator that runs all format checks in the correct order
and returns a populated ViolationCollector.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ingestion.pdf_loader import load_pdf, ParsedDocument
from checks.layout_checks   import run_layout_checks
from checks.font_checks     import run_font_checks
from checks.spacing_checks  import run_spacing_checks
from checks.heading_checks  import run_heading_checks
from checks.caption_checks  import run_caption_checks
from checks.image_checks    import run_image_checks
from checks.equation_checks import run_equation_checks
from checks.chapter_checks  import run_chapter_checks
from checks.citation_checks import run_citation_checks
from checks.grammar_checks  import run_grammar_checks
from checks.toc_checks        import run_toc_checks
from checks.subtopic_checks   import run_subtopic_checks
from checks.image_dimension_checks import run_image_dimension_checks
from checks.research_growth_checks import run_research_growth_checks
from checks.plagiarism_checks import run_plagiarism_checks
from utils.error_model import ViolationCollector
from utils.scoring import score_to_violation


# ── Check pipeline ────────────────────────────────────────────────────────────

CHECKS: list[tuple[str, Callable]] = [
    ("Page Layout",            run_layout_checks),
    ("Font",                   run_font_checks),
    ("Spacing & Alignment",    run_spacing_checks),
    ("Headings",               run_heading_checks),
    ("Captions",               run_caption_checks),
    ("Images & Graphs",        run_image_checks),
    ("Equations",              run_equation_checks),
    ("Chapter Structure",      run_chapter_checks),
    ("Citations & References", run_citation_checks),
    ("Grammar & Spelling",     run_grammar_checks),
    ("Table of Contents",      run_toc_checks),
    ("Subtopic Structure",     run_subtopic_checks),
    ("Image Dimensions",       run_image_dimension_checks),
    ("Research Growth",        run_research_growth_checks),
    ("Plagiarism",             run_plagiarism_checks),
]


def run_checks(
    pdf_path: str | Path,
    progress_callback: Callable[[str, int, int], None] | None = None,
    skip_grammar: bool = False,
) -> tuple[ParsedDocument, ViolationCollector]:
    """
    Load the PDF and run all format checks.

    Args:
        pdf_path: Path to the PDF file.
        progress_callback: Optional callable(label, current, total) for UI progress.
        skip_grammar: If True, skip the slow LanguageTool grammar check.

    Returns:
        (ParsedDocument, ViolationCollector)
    """
    doc = load_pdf(pdf_path)
    collector = ViolationCollector()

    active_checks = [
        (label, fn) for label, fn in CHECKS
        if not (skip_grammar and "Grammar" in label)
    ]
    total = len(active_checks)

    for idx, (label, fn) in enumerate(active_checks):
        if progress_callback:
            progress_callback(label, idx, total)
        try:
            violations = fn(doc)
            collector.add_all(violations)
        except Exception as e:
            from utils.constants import Severity, Category
            from utils.error_model import Violation
            collector.add(Violation(
                category=label,
                severity=Severity.INFO,
                page=-1,
                description=f"Check '{label}' encountered an internal error",
                detail=str(e),
            ))

    # Overall score (computed after all checks)
    try:
        collector.add(score_to_violation(collector))
    except Exception:
        pass

    if progress_callback:
        progress_callback("Done", total, total)

    return doc, collector
