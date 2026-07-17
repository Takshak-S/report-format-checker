import pdfplumber

with pdfplumber.open("sample_report.pdf") as pdf:
    page = pdf.pages[40] # Page 41
    chars = page.chars
    for c in chars:
        if 180 < c['top'] < 200:
            print(f"Char '{c['text']}' top={c['top']:.2f}")
