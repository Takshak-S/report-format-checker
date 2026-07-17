import fitz

doc = fitz.open("sample_report.pdf")
page = doc[40] # Page 41 (0-indexed)
words = page.get_text("words")

for w in words:
    x0, y0, x1, y1, text = w[:5]
    if "second" in text or "phase" in text:
        print(f"'{text}' at ({x0:.2f}, {y0:.2f}, {x1:.2f}, {y1:.2f})")
