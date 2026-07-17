"""
checker.py

Orchestrator that runs the Document Reconstruction Engine, Layout Analyzer,
and all format validations in the correct order, returning a populated ViolationCollector.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer
from utils.error_model import ViolationCollector
from utils.scoring import score_to_violation

from checks.font_validator import FontValidator
from checks.margin_validator import MarginValidator
# Other validators would be imported here...

def run_checks(
    pdf_path: str | Path,
    progress_callback: Callable[[str, int, int], None] | None = None,
    skip_grammar: bool = False,
):
    """
    Load the PDF, reconstruct DOM, classify blocks, and run all format checks.
    """
    if progress_callback: progress_callback("Parsing PDF & Reconstructing DOM", 0, 5)
    
    # 1. Parse and Reconstruct
    doc = load_pdf(pdf_path)
    
    if progress_callback: progress_callback("Analyzing Layout", 1, 5)
    
    # 2. Layout Analysis
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    
    collector = ViolationCollector()
    
    if progress_callback: progress_callback("Validating Fonts", 2, 5)
    
    # 3. Validate
    font_validator = FontValidator()
    collector.add_all(font_validator.validate(doc))
    
    if progress_callback: progress_callback("Validating Margins", 3, 5)
    
    margin_validator = MarginValidator()
    collector.add_all(margin_validator.validate(doc))
    
    # Future: add other validators here (headings, equations, citations, grammar)
    
    # Overall score (computed after all checks)
    try:
        collector.add(score_to_violation(collector))
    except Exception:
        pass

    if progress_callback: progress_callback("Done", 5, 5)

    return doc, collector
