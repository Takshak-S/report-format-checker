import json

with open("debug/violations.json") as f:
    viols = json.load(f)

for v in viols:
    if v["id"] == "M002":
        print("M002 bbox:", v["bbox"])
        print("M002 dom_id:", v["dom_id"])

doc = __import__('ingestion.pdf_loader', fromlist=['load_pdf']).load_pdf("sample_report.pdf")
for p in doc.get_all_paragraphs():
    if p.id == "para_13571":
        print(f"pdfplumber para_13571: text='{p.text}' bbox={p.bbox}")
