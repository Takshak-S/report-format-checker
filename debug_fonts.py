from pathlib import Path
from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer

pdf_path = "sample_report.pdf"
doc = load_pdf(pdf_path)

analyzer = LayoutAnalyzer()
analyzer.classify(doc)

for p in doc.get_all_paragraphs():
    if p.block_type.value == "BODY_TEXT":
        if p.page_num in [1, 13, 41]:
            if p.dominant_font:
                print(f"Page {p.page_num} [{p.block_type.value}]: size={p.dominant_font_size} font='{p.dominant_font}' text='{p.text[:40]}...'")
