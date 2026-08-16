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
from utils.noise_filter import apply_noise_filter
from utils.profile import build_profile

from checks.font_validator import FontValidator
from checks.margin_validator import MarginValidator
from checks.heading_validator import HeadingValidator
from checks.caption_validator import CaptionValidator
from checks.image_validator import ImageValidator
from checks.spacing_validator import SpacingValidator


def run_checks(
    pdf_path: str | Path,
    progress_callback: Callable[[str, int, int], None] | None = None,
    skip_grammar: bool = False,
):
    """
    Load the PDF, reconstruct DOM, classify blocks, and run all format checks.
    """
    if progress_callback: progress_callback("Parsing PDF & Reconstructing DOM", 0, 6)
    
    # 1. Parse and Reconstruct
    doc = load_pdf(pdf_path)
    
    if progress_callback: progress_callback("Analyzing Layout", 1, 6)
    
    # 2. Layout Analysis
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    
    # 2b. Calibrate per-document profile (dynamic baselines for validators)
    profile = build_profile(doc)
    
    # 3. Validate
    font_validator = FontValidator()
    font_validator.set_profile(profile)
    margin_validator = MarginValidator()
    margin_validator.set_profile(profile)
    heading_validator = HeadingValidator()
    heading_validator.set_profile(profile)
    caption_validator = CaptionValidator()
    caption_validator.set_profile(profile)
    image_validator = ImageValidator()
    image_validator.set_profile(profile)
    spacing_validator = SpacingValidator()
    spacing_validator.set_profile(profile)
    
    collector = ViolationCollector()
    
    if progress_callback: progress_callback("Validating Fonts", 2, 6)
    collector.add_all(font_validator.validate(doc))
    
    if progress_callback: progress_callback("Validating Margins", 3, 6)
    collector.add_all(margin_validator.validate(doc))
    
    collector.add_all(heading_validator.validate(doc))
    
    collector.add_all(caption_validator.validate(doc))
    
    if progress_callback: progress_callback("Validating Images", 4, 6)
    collector.add_all(image_validator.validate(doc))
    
    if progress_callback: progress_callback("Validating Spacing", 5, 6)
    collector.add_all(spacing_validator.validate(doc))
    
    # 3b. Post-processing: suppress noise / collapse systemic findings
    collector = apply_noise_filter(collector, doc)
    
    # The overall score is a document summary metric (utils.scoring.compute_score),
    # not a format finding; it must not be injected into the collector.
    
    if progress_callback: progress_callback("Done", 6, 6)
    
    return doc, collector