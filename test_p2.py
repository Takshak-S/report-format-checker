from ingestion.pdf_loader import load_pdf
from nlp.classifier import LayoutAnalyzer

doc = load_pdf("sample_report.pdf")
analyzer = LayoutAnalyzer()
analyzer.classify(doc)

for p in doc.get_all_paragraphs():
    if p.page_num == 2 and "hereby declare" in p.text:
        print(f"Page 2 paragraph: {p.text}")
        print(f"Type: {p.block_type}")
        print(f"Confidence: {p.classification_confidence}")
        print(f"Reasons: {p.classification_reasons}")
