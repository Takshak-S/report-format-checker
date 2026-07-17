import pdfplumber

with pdfplumber.open("sample_report.pdf") as pdf:
    page = pdf.pages[40] # Page 41
    chars = page.chars
    for c in chars:
        if "second" in c['text'] or "phase" in c['text'] or "implementation" in c['text']:
            print(f"Char '{c['text']}' top={c['top']:.2f}")

