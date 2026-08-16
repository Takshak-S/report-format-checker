# PDF Format Checker — Agent Instructions

## Project Purpose

This is a **zero-cost / open-source PDF Format Checker** for academic reports
and research papers. It primarily validates *rendered PDFs* against the VIT
formatting requirements (margins, fonts, heading hierarchy, captions, line
spacing, alignment) and produces annotated PDFs, per-PDF HTML table reports, a
corpus index, machine-readable summaries, Excel dossiers, and a Streamlit
dashboard.

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
- **Prefer fixing root causes in reconstruction/classification** (regexes,
  paragraph splitting, alignment inference) over tolerance tuning.
- **Do not reduce violation counts by disabling validators or making
  tolerances unreasonably large.**

## Pipeline (source of truth)

`PDF → extraction → reconstruction → classification → DocumentModel →
build_profile → validators → ViolationCollector → noise filter → final
findings → scoring/document summary → UI + reports + annotated PDFs`.

See `architecture.md` for the full component map. `checker.py:run_checks()`
orchestrates the pipeline; `run_audit.py` runs the whole corpus and prints
per-file raw/final category+severity counts as JSON.

## Current State & Workflow

- **Authority:** `CURRENT_TASK.md` is the ground-truth for current development.
  Do not deviate from its stated plan.
- **Architecture:** The system uses a profile-driven validation architecture.
  It parses PDFs once to build a cached, immutable Document Object Model (DOM)
  in memory, which all validators query. See `architecture.md`.
- **Workflow:**
  1. Read `CURRENT_TASK.md`.
  2. Inspect relevant implementation in `checks/`, `ingestion/`, `nlp/`,
     `reporter/`, or `utils/` before modifying anything.
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
- **Ignore:** `corpus/`, `debug/`, `test_files/` (gitignored), cache
  directories (`.venv`, `__pycache__`, etc.), and repo-root debug artifacts
  (`audit_*.json`, `test_*.py`, `debug_*.py`, `investigate_*.py`,
  `find_overflows.py`) unless specifically investigating regressions.
- **Configuration:** `utils/constants.py` contains format specifications and
  caption patterns; `utils/profile.py` builds per-document profiles;
  `utils/config.py` reads the template config (`vit_template.json`).

## Validation Scope & Current Baseline

Current corpus baseline (12 PDFs, verified, noise-filtered):

| Category | Count |
|---|---|
| Headings | 0 |
| Alignment | 1 (H008 — genuine left-aligned paragraph) |
| Spacing | 0 |
| Captions | 8 (caption-numbering gaps) |
| Page Layout | 14 (9 body-text overflows + 5 LIST overflows) |
| Other | 0 |
| **Total** | **23** |

Overall Format Score: **100/100 (Excellent)** for all 12 corpus PDFs. The
score is a **document summary metric** (`utils/scoring.compute_score` +
`document_summary`), displayed in the Streamlit UI header — it is **NOT** a
Violation and must never be injected into the `ViolationCollector`.

## Validator Behavior (do-not-regress contract)

- **Margin (`checks/margin_validator.py`):** paragraph-median + per-line edge
  analysis. `checkable_types` = `BODY_TEXT`, `LIST`, `HEADING_1/2/3`,
  `CHAPTER_TITLE`, `REFERENCE`, `APPENDIX`. LIST blocks use the existing
  per-line logic: bullet/hanging indentation is exempt (left rule), while a
  genuinely overfull line (long unbreakable token past the right margin +
  `margin_tolerance`) is a MINOR per-line finding. The paragraph bbox is never
  validated directly. Columnar/table rows (word-gap > 30 pt) are excluded.
- **Heading (`checks/heading_validator.py`):** profile-driven; size check
  (`_HEADING_SIZE_TOLERANCE = 2.5` pt) applies to numbered headings only.
  Correctly formatted headings → **zero findings on the corpus**.
- **Alignment/Spacing (`checks/spacing_validator.py`):** paragraph-level,
  BODY_TEXT scope only; special sections (bibliography/references/appendix),
  headings, captions, lists, equations, tables, TOC are excluded. Findings
  require ≥ 2 consistently deviating lines (fraction 0.5), never a single
  stray line.
- **Bibliography/reference/appendix:** classified as their own BlockTypes
  (`BIBLIOGRAPHY`, `REFERENCE`, `APPENDIX`) via a state machine with
  medium/semibold/demibold/bold heading recognition; never treated as
  BODY_TEXT and never reported as heading violations.
- **Image (`checks/image_validator.py`):** **deliberate no-op** — returns an
  empty list. Do not re-enable DPI validation.
- **Graph-axis OCR (`checks/image_checks.py`):** stays **enabled** (pytesseract
  + pdftoppm). Do not disable it.
- **Captions (`checks/caption_validator.py`):** `CAPTION` paragraphs are
  validated for format and numbering continuity. Continuity findings carry
  real evidence: page, bbox, location, previous/current caption context
  (detail), expected/detected numbers, and classification signals, with
  `confidence = 1.0`.

## Tables

- Table extraction is **separate from validation**. `pdfplumber` produces
  structural `TableNode`s; the classifier additionally labels text blocks as
  `TABLE`. These are two distinct object types.
- `reporter/table_report_generator.py` (`python3 -m reporter.table_report_generator`)
  builds per-PDF HTML reports, `index.html`, and `tables/_summary.json`,
  handling landscape tables, merged/rotated cells, multiline cells, and
  word-spacing reconstruction.
- **Known limitation (current open task):** caption association for table
  reports can report "No caption detected" even when a caption visibly exists
  above the table. See `CURRENT_TASK.md`. Do not claim this is fixed.
- Do not confuse table-report caption association with
  `CaptionValidator` (validation). They are independent.

## Results

- `results/` is **regenerated from the actual pipeline**, never hand-edited:
  `results/summary.json` (final noise-filtered findings), `results/README.md`
  (derived tables + notes), `results/annotated/*_annotated.pdf`, and
  `results/tables/*` (table reports).
- **Original corpus PDFs (`test_files/`) must never be modified.** Verify
  integrity (e.g. SHA-256) when reproducing results.
- Table reports are only regenerated when table extraction changes.

## Testing & Verification

- **Test Command:** `python3 -m pytest tests/` (root-level `test_*.py` files
  are legacy debug scripts and are not part of the suite).
- **Current test status:** `66 passed, 1 skipped` (the skip is
  `tests/test_regression.py::test_sample_report_regression`, which requires a
  local `report.pdf` that is not part of the corpus).
- **Regression tests:** `tests/test_regression_v2.py` (28 tests —
  bibliography/references/appendix transitions, list and glossary detection,
  alignment and spacing guards, heading case/size, LIST margin validation,
  DPI-disabled behavior). `tests/test_findings_model.py` (10 tests) locks the
  finding data model (no Overall-Score violations, caption evidence fields).
- **Corpus acceptance tests:** `tests/test_corpus.py` — marked
  `@pytest.mark.slow`, require `test_files/` present locally (gitignored).
  They assert: no font findings; no CRITICAL page-layout findings; per-file
  Page-Layout `MARGIN_BOUNDS` (H007=4, H008=4, H016=2, others unchanged);
  zero heading findings; alignment/spacing within per-file bounds (only H008
  retains one genuine left-aligned paragraph); summary/score integrity.
- **Any future change affecting classification, reconstruction, or validation
  must run the complete 12-PDF corpus** (e.g. `python3 run_audit.py`) and
  verify category counts before/after.

## Operational Gotchas

- **Parser:** Uses `PyMuPDF (fitz)` and `pdfplumber`.
- **run_audit.py stdout:** the `fitz` deprecation warning is printed to
  **stdout** before the JSON; strip the leading warning line(s) up to `[` before
  `json.loads`.
- **Dependencies:** Requires system tools (`poppler-utils`, `tesseract-ocr`)
  and `pip install -r requirements.txt`.
- **Reporting:** Uses `OpenPyXL` for Excel dossiers; avoid hardcoding scoring
  logic — use `utils.scoring.compute_score` / `document_summary`.
- **Corpus location:** `test_files/` is gitignored; copy the 12 PDFs locally to
  run slow tests.
- **Constraint:** Do not introduce architectural rewrites; the current
  DOM-based design is the required pattern.

## DO NOT (hard rules)

- Do **not** re-enable DPI validation — `checks/image_validator.py` stays a
  no-op.
- Do **not** treat the Overall Format Score as a finding — it is a document
  summary metric shown separately in the UI/report headers.
- Do **not** weaken validators or inflate tolerances merely to reduce finding
  counts.
- Do **not** modify original corpus PDFs.
- Do **not** use tolerance changes as a substitute for fixing a proven
  classification/reconstruction root cause.
- Do **not** change caption-numbering semantics (chapter-prefix advancement in
  `checks/caption_validator.py`) without an explicit specification decision —
  the per-chapter-sequence semantics suggested elsewhere remain unresolved.
- Do **not** hand-edit `results/` — regenerate from the pipeline.
- Do **not** claim the table-caption association issue is fixed until it is
  actually fixed.
