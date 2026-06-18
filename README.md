# PDF Format Checker

Automated format validation for project reports against the departmental
standardization template.

---

## Project Structure

```
pdf_format_checker/
├── ingestion/
│   └── pdf_loader.py          # PDF parsing — pdfplumber + PyMuPDF
├── checks/
│   ├── layout_checks.py       # Page size (A4), margins
│   ├── font_checks.py         # Font name (TNR) and size per element
│   ├── spacing_checks.py      # 1.5× line spacing, justified alignment
│   ├── heading_checks.py      # Hierarchy, numbering, case rules
│   ├── caption_checks.py      # Figure below / Table above, numbering, citations
│   ├── image_checks.py        # DPI ≥ 600, graph axis labels (OCR)
│   ├── equation_checks.py     # Chapter-wise numbering, right-alignment
│   ├── chapter_checks.py      # 8 mandatory chapters in order
│   ├── citation_checks.py     # APA format, in-text ↔ bibliography cross-check
│   └── grammar_checks.py      # LanguageTool + CS domain dictionary
├── reporter/
│   └── report_generator.py    # Excel report (Summary + Violations sheets)
├── utils/
│   ├── constants.py           # All format spec values and patterns
│   └── error_model.py         # Violation dataclass + ViolationCollector
├── checker.py                 # Orchestrator — runs all checks in sequence
├── app.py                     # Streamlit web UI
├── cli.py                     # Command-line interface
└── requirements.txt
```

---

## Setup

### 1. System dependencies

```bash
# Ubuntu / Debian
sudo apt-get install -y poppler-utils tesseract-ocr

# macOS
brew install poppler tesseract
```

### 2. Python dependencies

```bash
pip install -r requirements.txt
```

> LanguageTool downloads its server JAR (~200 MB) on first use.

---

## Usage

### Web UI (Streamlit)

```bash
streamlit run app.py
```

Open http://localhost:8501, upload a PDF, and click **Run Format Check**.

### CLI

```bash
# Full check with Excel report
python cli.py report.pdf

# Skip grammar check for speed
python cli.py report.pdf --skip-grammar

# Custom output path
python cli.py report.pdf --output /tmp/my_report.xlsx

# Print results only, no Excel
python cli.py report.pdf --no-report
```

Exit code: `0` = pass (no errors), `1` = fail (errors found).

---

## What is Checked

| Check | Spec |
|---|---|
| Page size | A4 (210×297 mm) |
| Margins | Left 1.5″, Right/Top/Bottom 1″ |
| Font | Times New Roman throughout |
| Body font size | 12 pt |
| Chapter title (L0) | 16 pt, UPPERCASE, new page |
| L1 heading | 14 pt, Bold, UPPERCASE, decimal prefix |
| L2 sub-heading | 12 pt, Title Case, two-decimal prefix |
| L3 sub-sub-heading | 12 pt, Bold + Italic |
| Caption font | 10 pt |
| Line spacing | 1.5× |
| Alignment | Fully justified |
| Image DPI | ≥ 600 DPI |
| Graph axes | X and Y labels present (OCR) |
| Figure caption | Below image, format `Figure X.Y: …` |
| Table title | Above table, format `Table X.Y: …` |
| Equations | Chapter-wise `(X.Y)`, right-aligned |
| Chapters | All 8 mandatory chapters, in order |
| Citations | APA 7th, in-text ↔ bibliography cross-check |
| Grammar | LanguageTool + CS term dictionary |

---

## Adding the CS Dictionary

Edit `checks/grammar_checks.py` → `CS_DICTIONARY` set to add domain terms that
should not be flagged as spelling errors.

---

## Extending with New Checks

1. Create `checks/my_new_check.py` with a `run_my_new_check(doc) -> list[Violation]` function.
2. Add it to the `CHECKS` list in `checker.py`.
3. Add a category constant to `utils/constants.py` → `Category` class if needed.
