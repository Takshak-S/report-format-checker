import json
import statistics
import numpy as np
from pathlib import Path
from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer
from nlp.dom import BlockType

def investigate():
    pdf_path = "sample_report.pdf"
    doc = load_pdf(pdf_path)
    
    analyzer = LayoutAnalyzer()
    analyzer.classify(doc)
    
    expected_right_pt = 72.0 # 1 inch
    
    for p in doc.get_all_paragraphs():
        if p.page_num in [2, 3]:
            text_preview = p.text.replace('\n', ' ')[:60]
            if "I hereby declare" in p.text or "EARLY STOPPING" in p.text or "MACHIN" in p.text:
                page = doc.pages[p.page_num - 1]
                max_x1 = page.width - expected_right_pt
                
                print(f"\n--- Page {p.page_num} ---")
                print(f"Text: {text_preview}")
                print(f"Classification: {p.block_type.value}")
                print(f"Confidence: {p.classification_confidence}")
                print(f"Reasons: {p.classification_reasons}")
                
if __name__ == "__main__":
    investigate()
