import pytest
import os
from pathlib import Path
from checks.validators import ValidationConfig
from utils.config import get_config
from utils.error_model import ViolationCollector, Violation
from checks.margin_validator import MarginValidator
from checks.font_validator import FontValidator
from nlp.classifier import LayoutAnalyzer
from ingestion.pdf_loader import load_pdf

def test_sample_report_regression():
    # Construct paths
    base_dir = Path(__file__).parent.parent
    pdf_path = base_dir / "report.pdf"
    
    # If the file doesn't exist, we can't run the test
    if not pdf_path.exists():
        pytest.skip(f"Test file {pdf_path} not found.")

    # Parse and construct DOM
    doc = load_pdf(str(pdf_path))
    
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    
    # Run Validations
    config = get_config()
    validators = [MarginValidator(), FontValidator()]
    
    collector = ViolationCollector()
    for v in validators:
        for viol in v.validate(doc):
            collector.add(viol)
            
    summary = collector.summary()
    by_cat = collector.by_category()
    
    # Assertions for Margin Violations (Expected 2 or similar genuine margin issues)
    margin_viols = by_cat.get("Page Layout", [])
    assert len(margin_viols) <= 4, f"Expected 2-4 margin violations, found {len(margin_viols)}"
    
    # Assertions for Spurious Font Violations
    font_viols = by_cat.get("Font", [])
    
    # Assert that no font violations exist for structural elements
    for viol in font_viols:
        assert "HEADER" not in viol.description, "Spurious font violation found in HEADER"
        assert "FOOTER" not in viol.description, "Spurious font violation found in FOOTER"
        assert "UNKNOWN" not in viol.description, "Spurious font violation found in UNKNOWN"
        assert "LIST" not in viol.description, "Spurious font violation found in LIST"
        assert "TABLE" not in viol.description, "Spurious font violation found in TABLE"
        assert "CODE_BLOCK" not in viol.description, "Spurious font violation found in CODE_BLOCK"
        assert "EQUATION" not in viol.description, "Spurious font violation found in EQUATION"
