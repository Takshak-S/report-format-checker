# PDF Format Checker — Architecture

> This document describes the **current implementation**. It is the source of
> truth for how the codebase is organized today; do not document aspirational
> or previously-designed-but-removed features.

## Overview

The system is a **zero-cost, fully-local PDF format checker** for VIT academic
reports. It parses a rendered PDF once into an in-memory Document Object Model
(DOM), classifies every paragraph into a semantic block type, builds a
per-document profile (dynamic baselines), runs a set of profile-driven
validators, and post-processes the findings through a noise filter before
reporting.

Because **PDFs are the only student input** and extraction is inherently noisy
(kerning, hyphenation, multi-column layouts, floats, tables rendered as text),
the architecture deliberately separates *reconstruction* from *validation* so
that noise can be suppressed at its source (classification/reconstruction)
rather than by loosening validator tolerances.

```
PDF (rendered) 
   │
   ▼
┌──────────────────────────┐
│ ingestion/pdf_loader.py  │  pdfplumber + PyMuPDF (fitz)
│  load_pdf()              │  → raw words / lines / fonts / bboxes
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ nlp/reconstruction.py    │  DocumentReconstructor
│                          │  merges words into lines, lines into
│                          │  paragraphs (DOM), infers alignment,
│                          │  spacing and geometry
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ nlp/classifier.py        │  LayoutAnalyzer
│  classify()              │  scores each paragraph → BlockType,
│                          │  heading level, bib/ref/appendix state
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ utils/profile.py         │  build_profile() → DocumentProfile
│                          │  char-weighted dominant sizes, median
│                          │  margins, heading sizes, structure flags
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ checks/*_validator.py    │  Font, Margin, Heading, Caption,
│  validators (profile-    │  Image (no-op), Spacing
│  and config-driven)      │
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ utils/error_model.py     │  ViolationCollector (collects findings)
└──────────────────────────┘
   │
   ▼
┌──────────────────────────┐
│ utils/noise_filter.py    │  confidence gate, dedup, systemic
│  apply_noise_filter()    │  collapse (document-level)
└──────────────────────────┘
   │
   ▼
reporting:  annotated PDFs (reporter/), Excel dossiers (OpenPyXL),
            Streamlit dashboard (app.py / ui/), overall score
            (utils/scoring.py)
```

Orchestration happens in `checker.py:run_checks()`: `load_pdf` →
`LayoutAnalyzer().classify` → `build_profile` → six validators (each seeded
with the profile) → `apply_noise_filter` → `score_to_violation`.

## 1. Ingestion — `ingestion/pdf_loader.py`

- `load_pdf(path)` opens the file and extracts raw geometry using
  **pdfplumber** (text, words, lines, rects) and **PyMuPDF (fitz)** (fonts,
  page dimensions).
- Everything downstream consumes this raw data; nothing is re-parsed per
  validator.

## 2. Reconstruction — `nlp/reconstruction.py`

`DocumentReconstructor` builds the immutable DOM (`nlp/dom.py`):
`DocumentModel` → `Page` → `Paragraph` → `Line` → `Word` (with `BBox`).

**Line building** — words are grouped into lines when their vertical tops are
within `4.0` pt; a word joins a line when the horizontal gap to the previous
word is below `max(avg_char_width * 0.25, 1.5)` pt.

**Paragraph splitting** — a line starts a new paragraph when any of:
- multi-column layout detected (horizontal gap to the previous line `> 100` pt
  with comparable vertical positions);
- vertical gap exceeds the split threshold;
- vertical gap `> base_font * 1.3` (visual paragraph break);
- font change;
- indentation (horizontal gap `> font * 1.5` with a positive vertical gap);
- **list marker**: the line matches `_LIST_MARKER_RE`
  (`^(\d{1,2}\.\s|[\u2022\u2023\u00B7\u2013\*\-]\s+)`) — unless the line uses a
  code font (`is_code_font`), in which case it stays inside the code block.

**Alignment inference** — alignment is decided relative to the **text-area
center** `(left_margin + right_margin) / 2`, not the physical page center
(mirror-page / binding-offset PDFs otherwise misclassify). A line is:
- `justified` / `left` / `right` from its left/right indents versus the
  margins (tolerance `5` pt);
- `center` when centered about the text-area center (indent tolerance
  `max(font * 3, 24)` pt);
- `boxed` / block-quote paragraphs get a special override: when the median
  left indent **and** median right gap of the interior lines (all but the last
  line) are both `≤ 5` pt relative to the paragraph bbox, the interior lines
  are treated as `justified` within the box, so boxed quotations are not
  reported as left-aligned noise.

**Line spacing** — normalized as
`(line_height + vertical_gap) / (base_font * 1.2)`.

## 3. Classification — `nlp/classifier.py`

`LayoutAnalyzer.classify(doc)` assigns a `BlockType` to every paragraph using
feature scoring (size, font, regexes, position, confidence) with a softmax
confidence; a paragraph whose top score is too low (`max_score < 10` or best
probability `< 0.75`) becomes `UNKNOWN`.

### Block types (`nlp/dom.py`)

`BODY_TEXT`, `CHAPTER_TITLE`, `HEADING_1`, `HEADING_2`, `HEADING_3`,
`CAPTION`, `TABLE`, `FIGURE`, `EQUATION`, `HEADER`, `FOOTER`,
`PAGE_NUMBER`, `TOC`, `REFERENCE`, `CODE_BLOCK`, `LIST`, `APPENDIX`,
`BIBLIOGRAPHY`, `UNKNOWN`.

### Heading classification

- Numbered headings match `_NUM_L1` / `_NUM_L2` / `_NUM_L3`
  (`^(\d+)\.\s`, `^(\d+\.\d+)\.\s`, `^(\d+\.\d+\.\d+)\.\s`) — **no trailing
  dot** in the match, so "3.1. Objectives." is classified as body text, not a
  heading.
- Unnumbered headings rely on size (`_HEADING_SIZE_BAND = 2.0` pt vs. body
  size), bold weight, and content heuristics. "Short uppercase line" headings
  are skipped when the line is **right-aligned math** (e.g. `U`, `V`, `W`
  alone) to avoid flagging symbol legends as headings.
- **Bibliography / References / Appendix** receive structural boosts; their
  headings are `CHAPTER_TITLE` / structural headings and their content is
  `BIBLIOGRAPHY` / `REFERENCE` / `APPENDIX` (never `BODY_TEXT`), guarded by
  state transitions so "3.4.2 Bibliography" etc. cannot become heading
  violations.

### Lists, glossaries, equations

- `_BULLET_RE = ^[\u2022\u2023\u00B7\u2013\*\-]\s+\S` (bullet `•`, triangle
  `‣`, **middle dot `·`**, **en dash `–`**, `*`, `-`). Bulleted lines score
  `LIST` (single-line bullet `+70`, multi-line list `+60`, list-item prefix
  `+65`).
- `_GLOSSARY_ABBR_RE` (all-caps abbreviation followed by `:` with a wide gap
  `> 10` pt) detects glossaries, including **Greek symbols** via the
  `\u0370-\u03FF` range; glossary rows score `+75`.
- A single right-aligned math line (`=`, `<`, `>`, `∑`, `≥`, etc.) scores
  `EQUATION` (`+60`).

## 4. Document Profile — `utils/profile.py`

`build_profile(doc)` computes a per-document "fingerprint" used by every
validator so checks compare against the document's *own* consistent values
instead of absolute thresholds:

- `page_count`, `page_width`, `page_height`;
- **typography**: `body_font_size`, `body_font_family`, `body_size_tolerance`
  (`1.0` pt band), `monospace_fonts` — char-weighted dominant values taken
  from high-confidence `BODY_TEXT`;
- **margins**: `left_margin`, `right_margin`, `top_margin`, `bottom_margin`
  (median of paragraph edges), `margin_tolerance` (default `10.0` pt, grows
  with the document's own spread);
- **structure flags**: `has_images`, `has_tables`, `has_equations`, `has_toc`,
  `has_captions`, `chapter_count`;
- **heading sizes**: `heading_l0_size … heading_l3_size` (char-weighted
  dominant sizes per level);
- **indentation**: `body_left_indent`, `indent_tolerance`.

Validators call `set_profile(profile)`; when a profile is absent they fall
back to `build_profile(doc, config)` internally.

## 5. Validators — `checks/`

All validators extend `checks/validators.py::ValidationRule` and return
`Violation` objects (category, severity, page, expected/detected, confidence,
reasons, suggested fix, location, bbox).

### FontValidator — `checks/font_validator.py`

- Body font must be within `_BODY_SIZE_BAND` (`9.5–15.0` pt) with
  `_SIZE_TOLERANCE = 1.0` pt against the profile body size.
- Font **family** must match the template family by prefix (≥ 0.7 similarity).
- Hybrid strategy: document-dominant value is the baseline; a *systemic*
  deviation from the configured spec is reported once at document level.
- On the corpus this validator produces **zero findings**.

### MarginValidator — `checks/margin_validator.py`

- Paragraph-level **median** edge analysis (left/right), checked against
  `expected_left = left_inches * 72` and `right = page_width - right_inches * 72`
  with `profile.margin_tolerance`.
- `checkable_types`: `BODY_TEXT`, `HEADING_1/2/3`, `CHAPTER_TITLE`,
  `REFERENCE`, `APPENDIX`.
- **Columnar/table rows are excluded**: a line whose consecutive-word gaps
  exceed `_COLUMNAR_GAP_PT = 30.0` pt is treated as a table cell row, not
  prose (genuine overflows show 2–9 pt gaps; table rows 54–109 pt).
- Indented paragraphs (quotations/declarations/list items) are exempt from the
  left rule.
- Single-line right overflows are demoted: `WARNING` if they contain a URL /
  DOI / email (unbreakable string), else `MINOR` ("Single line overflow").
  Multi-line overflows and left overflows are `CRITICAL`.

### HeadingValidator — `checks/heading_validator.py`

- **Size check** (`_HEADING_SIZE_TOLERANCE = 2.5` pt) applies only to
  *numbered* headings, compared against the profile's per-level size
  (`heading_l1_size` …). Correctly sized headings → zero findings.
- **Numbering**: consecutive headings must not repeat.
- **Case check**: config-driven per level — level 0/1 must be uppercase,
  level 2 must be Title Case. Title-Case is checked with a softened rule that
  flags a heading only when the **first significant word is lowercase** or
  there are **≥ 3 lowercase significant words** (accepts ML-style wording).
- **Special-section exclusion**: headings inside `BIBLIOGRAPHY` / `REFERENCE`
  / `APPENDIX` sections are excluded from heading violations.

### CaptionValidator — `checks/caption_validator.py`

- Collects `CAPTION` paragraphs; format check requires `Figure N:` /
  `Table N:`; numbering continuity is checked with INFO severity (gap or
  repeat).
- Position validation is currently a no-op stub (spatial figure/bbox
  reconstruction is not available).

### ImageValidator — `checks/image_validator.py`

- **Deliberate no-op** — returns an empty list. DPI validation was removed on
  purpose (rendered PDFs vary in rasterization DPI and it produced false
  positives). Do not reintroduce it.

### SpacingValidator — `checks/spacing_validator.py`

Operates only on `BODY_TEXT` paragraphs (bibliography/references/appendix,
headings, captions, lists, equations, tables, TOC are excluded), at
**paragraph level** — a single noisy line is never a finding:

- `LINE_SPACING_TOLERANCE = 0.30` (normalized spacing vs. profile body);
- `MIN_SPACING_LINES = 2`, `SPACING_VIOLATION_FRACTION = 0.5` — spacing is
  flagged only when ≥ half of a multi-line paragraph deviates.
- **Alignment** is flagged when `MIN_ALIGNMENT_LINES = 2` lines are
  consistently (fraction `ALIGNMENT_VIOLATION_FRACTION = 0.5`) aligned
  contrary to the inferred paragraph alignment.

## 6. Noise Filter — `utils/noise_filter.py`

`apply_noise_filter(collector, doc)` returns a new, noise-reduced collector:

1. **Confidence gate** — drop findings below `0.40`; demote one severity level
   below `0.60`.
2. **Deduplication** — identical findings (same rule, same page) collapse into
   one with a count.
3. **Consistency reclassification** — a rule firing on ≥ `0.5` of content
   pages (`_SYSTEMIC_PAGE_FRACTION`, `_MIN_PAGES_FOR_SYSTEMIC = 2`) is a
   systemic issue: collapsed into a single document-level finding.

## 7. Scoring & Reporting

- `utils/scoring.py::compute_score` computes the overall score from collected
  violations; `score_to_violation` wraps it in an `OVERALL_SCORE` INFO
  violation. Never hardcode scoring logic in reporters.
- Reporting produces annotated PDFs (`reporter/`), Excel dossiers
  (`OpenPyXL`), and a Streamlit dashboard (`app.py`, `ui/`).

## Technology Stack

- PDF parsing: **pdfplumber**, **PyMuPDF (fitz)**
- OCR (graph-axis labels only): **pytesseract** + **pdftoppm**
  (poppler-utils), `checks/image_checks.py`
- Excel: **OpenPyXL**; UI: **Streamlit**
- Tests: `pytest` (see `AGENTS.md` for the test suite and corpus acceptance
  criteria)
