# PDF Format Checker — Current Development State

This document is the ground-truth for current development. Read it before any
change and follow its stated plan.

IMPORTANT:
- Do not restart completed work.
- Do not redesign the architecture unless the existing implementation requires
  it.
- Inspect the current code before making changes.
- Preserve the existing profile-driven architecture and noise-filter decisions.
- Use the 12-PDF corpus to verify changes and watch for false positives.
- Distinguish genuine violations from extraction/classification noise.
- Investigate regressions rather than accepting them.

## CURRENT BASELINE

Verified against the complete 12-PDF corpus (`test_files/`, gitignored). Final
noise-filtered findings per PDF (from the regenerated `results/summary.json`,
timestamp 2026-08-16):

| PDF | Final Total | Category breakdown |
|---|---|---|
| 2026W10140U02H005_22BCE3217 | 0 | — |
| 2026W10140U02H007_22BCE0927 | 4 | Page Layout 4 |
| 2026W10140U03H004_22BCB0096 | 2 | Page Layout 1, Captions 1 |
| 2026W10140U03H008_22BCE0335 | 5 | Page Layout 4, Alignment 1 |
| 2026W10167P01H013_24MAI0005 | 1 | Captions 1 |
| 2026W10167P01H014_24MAI0027 | 1 | Captions 1 |
| 2026W10167U01H015_22BCE0508 | 2 | Page Layout 1, Captions 1 |
| 2026W10167U01H016_22BCE0309 | 2 | Page Layout 2 |
| 2026W10167U03H018_22BCE3372 | 3 | Page Layout 2, Captions 1 |
| 2026W10230U01H019_22BCE0420 | 0 | — |
| 2026W10243I01H026_21MID0051 | 2 | Captions 2 |
| 2026W10243P01H023_24MCS0036 | 1 | Captions 1 |
| **Total** | **23** | Headings 0 · Alignment 1 · Spacing 0 · Captions 8 · Page Layout 14 · Other 0 |

- **Overall Format Score:** 100/100 (Excellent) for all 12 PDFs. The score is a
  document summary metric (`utils/scoring.compute_score` + `document_summary`)
  shown in the Streamlit header — it is **NOT** a Violation and must never be
  injected into the `ViolationCollector`.
- **Tests:** `python3 -m pytest tests/` → **66 passed, 1 skipped** (the skip is
  `tests/test_regression.py::test_sample_report_regression`, which requires a
  local `report.pdf` not part of the corpus).
- **results/:** `summary.json`, `README.md`, `annotated/*_annotated.pdf`, and
  `tables/*` are regenerated from the actual pipeline, never hand-edited.
  Original corpus PDFs are unchanged (SHA-256 verified).

### The 5 Page-Layout LIST findings are intentional

All 5 are MINOR per-line "Right margin overflow in LIST." findings, verified as
genuine long unbreakable tokens past the right margin (nominal right boundary
523.276 pt = 595.276 − 72; effective threshold 523.276 + `margin_tolerance` 20.0
= 543.276 pt):

| PDF | Page | Token | Detected right edge (pt) |
|---|---|---|---|
| H007 | 36 | `kubernetes/deployment.yml` | 641.53 |
| H007 | 46 | `libgomp1` | 547.48 |
| H008 | 56 | `ReentrancyGuard.` | 552.12 |
| H016 | 29 | `Conv1d(kernel=7),` | 565.99 |
| H016 | 32 | `N)/0.6745` | 567.93 |

The single Alignment finding (H008 p52, "Bidding logic acts almost
predatorily…", 3/4 judged lines left instead of justified) is also genuine.

## COMPLETED WORK

### Classification — `nlp/classifier.py`
- `_BULLET_RE` extended to `[\u2022\u2023\u00B7\u2013\*\-]` (bullet, triangle,
  **middle dot**, **en dash**, `*`, `-`) so middle-dot/en-dash bullets
  classify as `LIST`, not `BODY_TEXT`.
- New `_LIST_MARKER_RE` (`^(\d{1,2}\.\s|[\u2022\u2023\u00B7\u2013\*\-]\s+)`)
  shared with reconstruction for list-marker paragraph splits.
- `_GLOSSARY_ABBR_RE` extended with the Greek range `\u0370-\u03FF` so
  Greek-symbol glossary rows (e.g. `μ : 0.85`) stay out of BODY_TEXT.
- List scores boosted (multi-line list `+60`, single-line bullet `+70`,
  list-item prefix `+65`, glossary `+75`) with body penalties.
- Heading "Short uppercase line" guard skips **right-aligned math** lines
  (e.g. `U`, `V`, `W`) so symbol legends are not misread as headings.
- A single right-aligned math line is classified `EQUATION` (`+60`).
- **Bibliography / References / Appendix** state machine with
  medium/semibold/demibold/bold heading recognition
  (`_MEDIUM_FONT_RE = (medi|medium|demibold|semibold|bold)`); content is
  `BIBLIOGRAPHY` / `REFERENCE` / `APPENDIX` (never `BODY_TEXT`, never a heading
  violation), and the state resets when a new chapter (`Chapter N` or a
  full-match Roman numeral) appears.

### Reconstruction — `nlp/reconstruction.py`
- **Center detection** uses the text-area center
  `(left_margin + right_margin) / 2` instead of the physical page center
  (mirror-page/binding-offset PDFs no longer misclassified as centered).
- Paragraphs split at `_LIST_MARKER_RE` lines **unless** the line uses a code
  font (`is_code_font`), so code blocks are not split at leading `-`/`*`.
- **Boxed / block-quote alignment override**: when the median left indent and
  median right gap of interior lines (all but the last) are both `≤ 5` pt
  relative to the paragraph bbox, interior lines are treated as `justified`
  within the box — boxed quotations are no longer reported as left-aligned.

### Profile — `utils/profile.py`
- Char-weighted dominant body font size/family from high-confidence BODY_TEXT;
  per-level char-weighted heading sizes (`heading_l0_size … heading_l3_size`)
  excluding bibliography/reference/appendix; median margins with
  `margin_tolerance` (default 10 pt, grows via `3 * MAD`, capped at 20 pt);
  `body_left_indent` + `indent_tolerance` (default 8 pt).

### HeadingValidator — `checks/heading_validator.py`
- Size check (`_HEADING_SIZE_TOLERANCE = 2.5` pt) applies only to numbered
  headings, compared against the profile per-level size. Correctly formatted
  headings → zero findings on the corpus.
- Title-Case rule softened: flagged only when the **first significant word is
  lowercase** or there are **≥ 3 lowercase significant words** (accepts
  ML-style wording).
- Bibliography / reference / appendix headings excluded from heading
  violations.

### MarginValidator — `checks/margin_validator.py`
- `checkable_types` extended with `LIST` (also `BODY_TEXT`,
  `HEADING_1/2/3`, `CHAPTER_TITLE`, `REFERENCE`, `APPENDIX`). The paragraph
  bbox is never validated directly.
- LIST blocks reuse the per-line edge analysis: bullet/hanging indentation is
  exempt (left rule); a genuinely overfull line (long unbreakable token past
  the right margin + `margin_tolerance`) is a MINOR per-line finding.
- Columnar/table rows (word-gap > `_COLUMNAR_GAP_PT = 30.0`) excluded.

### SpacingValidator — `checks/spacing_validator.py`
- Paragraph-level logic only (BODY_TEXT, with bibliography/references/appendix,
  headings, captions, lists, equations, tables, TOC excluded); single noisy
  lines never flag. `LINE_SPACING_TOLERANCE = 0.30`,
  `MIN_ALIGNMENT_LINES = 2`, `ALIGNMENT_VIOLATION_FRACTION = 0.5`,
  `MIN_SPACING_LINES = 2`, `SPACING_VIOLATION_FRACTION = 0.5`.

### Images
- **DPI validation removed** — `checks/image_validator.py` is a deliberate
  no-op.
- **Graph-axis OCR** (`checks/image_checks.py`, pytesseract + pdftoppm) kept
  enabled.

### Captions — `checks/caption_validator.py`
- Continuity findings carry real evidence: page, bbox, location, previous /
  current caption context (detail), expected/detected numbers, and
  classification signals, with `confidence = 1.0`.

### Overall Score separation
- `utils/scoring.py::compute_score` + `document_summary` compute the overall
  format score as a **document summary metric** (only CRITICAL/WARNING
  penalties; `RESEARCH` / `OVERALL_SCORE` categories skipped). Removed the old
  `score_to_violation` wrapper — the score is never injected into the
  `ViolationCollector`.

### Tables & Reporting
- `reporter/table_report_generator.py` builds per-PDF HTML table reports,
  `results/tables/index.html`, and `results/tables/_summary.json`, handling
  landscape (rotated) tables, merged/rotated cells, multiline cells, and
  word-spacing reconstruction. Table extraction (`TableNode` via pdfplumber)
  is separate from the `TABLE` classifier block type.
- Annotated PDFs: each finding gets a highlight/square mark + FreeText note +
  a legend per page (`reporter/pdf_annotator.py`).
- `results/` regenerated from the actual pipeline (summary.json, README.md,
  12 annotated PDFs); original PDF integrity verified via SHA-256.

### Tests
- `tests/test_regression_v2.py` — 28 tests (bibliography/references/appendix
  transitions, list and glossary detection, alignment and spacing guards,
  heading case/size, LIST margin validation, DPI-disabled behavior).
- `tests/test_findings_model.py` — 10 tests locking the finding data model (no
  Overall-Score violations, caption evidence fields).
- `tests/test_table_reports.py` — 21 tests for the table report generator.
- `tests/test_corpus.py` — 7 slow acceptance tests (no font findings, no
  CRITICAL page-layout findings, per-file `MARGIN_BOUNDS` = H007 4 / H008 4 /
  H016 2, zero heading findings, alignment/spacing within bounds, summary/score
  integrity).
- Suite status: **66 passed, 1 skipped**.

## CURRENT OPEN TASK

### Table-caption association in table reports ("No caption detected")

**Observation:** a table report (`reporter/table_report_generator.py`) can show
`Caption: No caption detected` even though the PDF **visibly contains** a
caption above the table — e.g. `Table 7.1: Comprehensive Performance Evaluation
of Standalone vs. Hybrid Architectures`.

**Scope:** this is a **reporting/extraction** concern only
(`reporter/table_report_generator.py`, `_find_caption_for_table`,
`TABLE_CAPTION_PATTERN` in `utils/constants.py`). It is **independent** of
`checks/caption_validator.py` (validation) — do not confuse the two, and do not
"fix" it by weakening the validator.

**Current association logic:** for each `TableNode`, the closest paragraph above
it on the same page (`p.bbox.y1 <= tbl.bbox.y0 + 30`) sorted bottom-up is
matched against `TABLE_CAPTION_PATTERN`
(`^(Table|Tab\.?)\s+\d+\.\d+\s*[:–\-.]\s*`); the search stops when the gap to a
non-caption paragraph exceeds 100 pt. Anything not matched → "No caption
detected".

**Plan (investigate before changing anything):**
1. Reproduce: locate the failing PDF/page and confirm the visible caption text
   and its y-position relative to the table.
2. Read `reporter/table_report_generator.py` (`_find_caption_for_table`, how
   captions are stored in the report dict) and `services/table_service.py`
   (the pandas-free replica's source of truth).
3. Determine why the caption paragraph is missed: (a) paragraph not on the
   page's paragraph list, (b) bbox not strictly above the table within the
   30 pt tolerance / inside the 100 pt break, (c) text does not match
   `TABLE_CAPTION_PATTERN` (multi-line caption, separator variants), or
   (d) the `TableNode` bbox differs from the visual table.
4. Compare a working case vs the failing case; identify the discriminating
   feature.
5. Only then design a minimal fix that supports captions **above** tables
   (do not assume captions are below tables) and preserves all currently
   correct associations.
6. Add regression tests (`tests/test_table_reports.py`) covering the failing
   caption and the working captions.
7. Regenerate table reports (`python3 -m reporter.table_report_generator`).
8. Re-run the full test suite (`python3 -m pytest tests/`).
9. Verify no unrelated validation results changed (do not touch validators).
10. Update `results/tables/_summary.json` / `index.html` only by regenerating.
11. Update `AGENTS.md` / `architecture.md` / `CURRENT_TASK.md` only after the
    fix is verified.
12. Do **not** declare this fixed until the reproduction case passes with a
    regression test.

## KNOWN DESIGN QUESTIONS

- **Caption-numbering semantics (unresolved).** `checks/caption_validator.py`
  uses chapter-prefix advancement (each caption's integer part is the chapter
  prefix; a gap means consecutive captions skipped a chapter), while the
  template (`vit_template.json`, `chapter_wise`) and `checks/caption_checks.py`
  suggest per-chapter-sequence semantics. **Do not change this without an
  explicit specification decision.**
- **Table-caption association (open task above).** "No caption detected" for
  visible captions above tables — under investigation.
- **Legacy `checks/*_checks.py` modules** (`font_checks`, `caption_checks`,
  `heading_checks`, `spacing_checks`, `layout_checks`, `toc_checks`, etc.) are
  not part of the current validation pipeline (they are legacy
  ParsedDocument-bound). Do not extend them; the `*_validator.py` files are
  authoritative.
- **Repo-root debug artifacts** (`audit_*.json`, `test_*.py`, `debug_*.py`,
  `find_overflows.py`) are untracked and not part of the results task.

## Warnings

- Do not reintroduce DPI validation — `checks/image_validator.py` is a
  deliberate no-op; keep `checks/image_checks.py` graph-axis OCR active.
- Do not disable validators or loosen tolerances to lower counts — fix root
  causes in reconstruction/classification instead.
- Do not treat bibliography/reference/appendix as BODY_TEXT for
  alignment/spacing checks.
- Do not report a single stray line as an alignment/spacing violation —
  findings require paragraph-level evidence.
- Do not treat the Overall Format Score as a finding.
- Do not hand-edit `results/` — regenerate from the pipeline.
- Do not claim the table-caption association issue is fixed until it is
  actually fixed.
- `run_audit.py` stdout: the `fitz` deprecation warning line(s) precede the
  JSON — strip everything up to `[` before `json.loads`.
- Root-level `test_*.py` files are legacy debug scripts; run pytest only on
  `tests/`.
- Deferred / out of scope: grammar (external LanguageTool), plagiarism
  (external), research-growth/subtopic/citation/chapter checks (legacy,
  ParsedDocument-bound).
