import fitz
import json

doc = fitz.open("sample_report.pdf")
page = doc[40] # Page 41 (0-indexed)
words = page.get_text("words")

with open("debug/margin_data.json") as f:
    margin_data = json.load(f)

m002 = next(m for m in margin_data if m["id"] == "para_13571")
left, right = min(m002["left_edges"]), max(m002["right_edges"])

print(f"pdfplumber right edge: {right}")

# Find words near this y-coordinate
for w in words:
    x0, y0, x1, y1, text = w[:5]
    # Check if in same paragraph y-range roughly
    if 180 < y0 < 200:
        print(f"PyMuPDF word: '{text}' x0={x0:.2f} x1={x1:.2f}")

