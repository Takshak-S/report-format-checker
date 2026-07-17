import pdfplumber
import fitz

with pdfplumber.open("sample_report.pdf") as pdf:
    p_text = pdf.pages[40].extract_text()
    
doc = fitz.open("sample_report.pdf")
f_text = doc[40].get_text("text")

print("PDFPLUMBER STARTS WITH:")
print(repr(p_text[:100]))
print("FITZ STARTS WITH:")
print(repr(f_text[:100]))
