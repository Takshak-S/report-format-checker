# PDF Format Checker — Agent Instructions

## Project Purpose

This is a **zero-cost / open-source PDF Format Checker** for academic reports
and research papers. It primarily validates *rendered PDFs* against the VIT
formatting requirements (margins, fonts, heading hierarchy, captions, line
spacing, alignment) and produces annotated PDFs, Excel dossiers, and a
Streamlit dashboard.

## Core Principles

These rules are non-negotiable:

- **PDFs are the only student input.** Original `.tex` / `.docx` / `.doc`
  sources are never assumed to be available.
- **No paid/cloud document-AI or OCR services.** Everything runs locally on
  open-source tools (`poppler-utils`, `tesseract-ocr`, `PyMuPDF`, `pdfplumber`).
- **PDF extraction/reconstruction is inherently noisy.** Geometric extraction
  (kerning, hyphenation, columns, floats) frequently produces artifacts.
- **Do not treat extraction/classification noise as a formatting violation
  without sufficient evidence.** Alignment/spacing findings require multiple
  violating lines (paragraph-level), not a single stray line.
- **Preserve genuine validation while minimizing false positives.** The goal is
  a defensible signal, not an aggressively low count.
- **Do not reintroduce DPI validation.** `checks/image_validator.py` is a
  deliberate no-op.
- **Graph-axis OCR remains active** through `checks/image_checks.py`
  (pytesseract + pdftoppm); do not disable it.
- **Bibliography/reference/appendix content must not be treated as normal
  BODY_TEXT** for alignment/spacing validation.
- **Correctly formatted headings should produce zero heading violations.**
- **Do not reduce violation counts by disabling validators or making
  tolerances unreasonably large.**
- **Prefer fixing root causes in reconstruction/classification** (regexes,
  paragraph splitting, alignment inference) over tolerance tuning.

## Current State & Workflow

- **Authority:** `CURRENT_TASK.md` is the ground-truth for current development.
  Do not deviate from its stated plan.
- **Architecture:** The system uses a profile-driven validation architecture.
  It parses PDFs once to build a cached, immutable Document Object Model (DOM)
  in memory, which all validators query. See `architecture.md`.
- **Workflow:**
  1. Read `CURRENT_TASK.md`.
  2. Inspect relevant implementation in `checks/`, `ingestion/`, `nlp/`, or
     `utils/` before modifying anything.
  3. Make focused changes.
  4. Run unit/regression tests.
  5. Run the complete 12-PDF corpus.
  6. Compare before/after category counts.
  7. Investigate regressions rather than accepting them.
  8. Distinguish genuine violations from extraction/classification noise.
  9. Do not declare success merely because total violations decreased.

## Repository Boundaries

- **Core:** `checks/`, `ingestion/`, `nlp/`, `reporter/`, `services/`, `ui/`,
  and `utils/`.
- **Ignore:** `corpus/`, `debug/`, `test_files/` (gitignored), and cache
  directories (`.venv`, `__pycache__`, etc.) unless specifically investigating
  regressions.
- **Configuration:** `utils/constants.py` contains format specifications;
  `utils/profile.py` builds per-document profiles; `utils/config.py` reads the
  template config (`vit_template.json`).

## Testing & Verification

- **Test Command:** Use `python3 -m pytest tests/` (root-level `test_*.py`
  files are legacy debug scripts and are not part of the suite).
- **Current test status:** `29 passed, 1 skipped` (the skip is
  `tests/test_regression.py::test_sample_report_regression`, which requires a
  local `report.pdf` that is not part of the corpus).
- **Regression tests:** `tests/test_regression_v2.py` (22 unit tests covering
  bibliography/references/appendix, list and glossary detection, alignment and
  spacing guards, heading case/size, and DPI-disabled behavior).
- **Corpus acceptance tests:** `tests/test_corpus.py` — these are marked
  `@pytest.mark.slow` and require `test_files/` to be present locally
  (gitignored). They must continue passing. They assert:
  - no font findings,
  - no CRITICAL page-layout findings,
  - per-file margin bounds,
  - **zero heading findings on the corpus**,
  - **alignment/spacing noise within per-file bounds** (only H008 retains one
    genuine left-aligned paragraph),
  - summary/score integrity.
- **Any future change affecting classification, reconstruction, or validation
  must run the complete 12-PDF corpus** (e.g. `python3 run_audit.py`) and
  verify category counts before/after.

## Operational Gotchas

- **Parser:** Uses `PyMuPDF (fitz)` and `pdfplumber`.
- **Dependencies:** Requires system tools (`poppler-utils`, `tesseract-ocr`)
  and `pip install -r requirements.txt`.
- **Reporting:** Uses `OpenPyXL` for Excel dossiers; avoid hardcoding scoring
  logic—use `utils.scoring.compute_score`.
- **Corpus location:** `test_files/` is gitignored; copy the 12 PDFs locally to
  run slow tests.
- **Constraint:** Do not introduce architectural rewrites; the current
  DOM-based design is the required pattern.
