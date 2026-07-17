from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer

doc = load_pdf("sample_report.pdf")
analyzer = LayoutAnalyzer()
analyzer.classify(doc)

for p in doc.get_all_paragraphs():
    if p.page_num == 43 and p.block_type.name == "BODY_TEXT":
        if p.dominant_font_size != 12.0:
            print(f"Page 43 paragraph: {p.text}")
            print(f"Confidence: {p.classification_confidence}")
            print(f"Font size: {p.dominant_font_size}")
