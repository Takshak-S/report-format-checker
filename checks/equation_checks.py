"""
checks/equation_checks.py

Checks:
  1. Equations are numbered in chapter-wise format (2.1), (2.2) ...
  2. Numbers are sequential within each chapter
  3. Equation number is right-aligned on the line
"""
from __future__ import annotations

import re
from ingestion.pdf_loader import ParsedDocument, LineInfo
from utils.constants import EQUATION_PATTERN, Severity, Category
from utils.error_model import Violation


def _extract_eq_number(text: str) -> tuple[int, int] | None:
    m = re.search(r"\((\d+)\.(\d+)\)\s*$", text.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _is_right_aligned(line: LineInfo, page_width: float, margin_right: float, tol: float = 15.0) -> bool:
    """Heuristic: equation number label should be near the right margin."""
    expected_right = page_width - margin_right
    return abs(line.x1 - expected_right) <= tol


def run_equation_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []
    equation_lines = [
        (line, doc.page_sizes[line.page_num - 1][0])
        for line in doc.lines
        if EQUATION_PATTERN.search(line.text.strip())
    ]

    counters: dict[int, int] = {}  # chapter → last equation number

    for line, page_width in equation_lines:
        nums = _extract_eq_number(line.text)
        if not nums:
            continue
        ch, eq_num = nums

        # Sequential check
        expected = counters.get(ch, 0) + 1
        if eq_num != expected:
            violations.append(Violation(
                category=Category.EQUATIONS,
                severity=Severity.WARNING,
                page=line.page_num,
                description="Equation numbering is not sequential",
                detail=f"Expected ({ch}.{expected}), found ({ch}.{eq_num})",
                location=line.text[:60],
            ))
        counters[ch] = eq_num

        # Right-alignment check
        from utils.constants import MARGIN_RIGHT_PT
        if not _is_right_aligned(line, page_width, MARGIN_RIGHT_PT):
            violations.append(Violation(
                category=Category.EQUATIONS,
                severity=Severity.INFO,
                page=line.page_num,
                description="Equation number may not be right-aligned",
                detail=f"Line right edge at {line.x1:.1f} pt, expected near {page_width - MARGIN_RIGHT_PT:.1f} pt",
                location=line.text[:60],
            ))

    return violations
