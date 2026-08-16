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

## Status

**COMPLETED.** The noise-reduction task is finished: headings, alignment,
spacing, and bibliography/reference/appendix false positives are reduced to
defensible levels on the 12-PDF corpus while genuine margin and caption
findings are preserved. All acceptance criteria are met and the documentation
(AGENTS.md, architecture.md) reflects the current implementation.

## Objective

Reduce validation noise on the rendered-PDF corpus without disabling
validators or gaming tolerances — by fixing root causes in reconstruction and
classification — while:

- **headings** on the corpus → **0** findings;
- **alignment/spacing** findings limited to genuine cases (paragraph-level,
  no single-stray-line findings);
- **bibliography / references / appendix** content never treated as BODY_TEXT
  or headings;
- the H019 heading regression eliminated;
- genuine margin overflows and caption numbering gaps **kept**;
- DPI validation stays disabled (no-op);
- graph-axis OCR stays active.

## Completed Changes

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
- Bibliography/References/Appendix receive structural boosts with guarded
  state transitions (their headings are structural, their content is never
  BODY_TEXT).

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
- Char-weighted dominant body font size/family from high-confidence
  BODY_TEXT; per-level char-weighted heading sizes
  (`heading_l0_size … heading_l3_size`); median margins with tolerance that
  grows with the document's own spread.

### HeadingValidator — `checks/heading_validator.py`
- Size check (`_HEADING_SIZE_TOLERANCE = 2.5` pt) applies only to numbered
  headings, compared against the profile per-level size. Correctly formatted
  headings → zero findings.
- Title-Case rule softened: flagged only when the **first significant word is
  lowercase** or there are **≥ 3 lowercase significant words** (accepts
  ML-style wording).
- Bibliography / reference / appendix headings excluded from heading
  violations.

### SpacingValidator — `checks/spacing_validator.py`
- Paragraph-level logic only (BODY_TEXT); single noisy lines never flag.
  `LINE_SPACING_TOLERANCE = 0.30`, `MIN_ALIGNMENT_LINES = 2`,
  `ALIGNMENT_VIOLATION_FRACTION = 0.5`, `MIN_SPACING_LINES = 2`,
  `SPACING_VIOLATION_FRACTION = 0.5`.

### Tests
- `tests/test_regression_v2.py` added — 22 unit tests covering
  bibliography/references/appendix transitions (incl. H019-style references),
  bullet/Greek glossary detection, list-marker splits (incl. code-font guard),
  alignment/spacing guards, text-area-center detection, boxed-quote vs
  left-aligned, TOC, heading case/size, and DPI-disabled behavior.
- `tests/test_corpus.py` gained `test_zero_heading_findings_on_corpus` and
  `test_no_alignment_spacing_noise_on_corpus`.
- Suite status: `python3 -m pytest tests/` → **29 passed, 1 skipped** (the
  skip is the legacy `test_sample_report_regression`, which needs a local
  `report.pdf`).

## Current Corpus Results

Post-noise-filter counts from the complete 12-PDF run (`python3 run_audit.py`),
run against the same PDFs as the baseline. Headings are 0 on every file;
alignment and spacing are limited to the one genuine case; all remaining
findings are pre-existing margin overflows (Page Layout) and caption numbering
gaps (Captions).

| PDF | Final Total | Headings | Alignment | Spacing | Other |
|---|---|---|---|---|---|
| H005 | 0 | 0 | 0 | 0 | — |
| H007 | 2 | 0 | 0 | 0 | Page Layout 2 |
| H004 | 2 | 0 | 0 | 0 | Page Layout 1, Captions 1 |
| H008 | 4 | 0 | 1 | 0 | Page Layout 3 |
| H013 | 1 | 0 | 0 | 0 | Captions 1 |
| H014 | 1 | 0 | 0 | 0 | Captions 1 |
| H015 | 2 | 0 | 0 | 0 | Page Layout 1, Captions 1 |
| H016 | 0 | 0 | 0 | 0 | — |
| H018 | 3 | 0 | 0 | 0 | Page Layout 2, Captions 1 |
| H019 | 0 | 0 | 0 | 0 | — |
| MID026 | 2 | 0 | 0 | 0 | Captions 2 |
| H023 | 1 | 0 | 0 | 0 | Captions 1 |

Before/after totals (baseline → round-1 → final): H005 188→152→0; H007
325→277→2; H004 183→139→2; H008 206→136→4; H013 90→68→1; H014 157→122→1;
H015 173→139→2; H016 132→85→0; H018 242→173→3; H019 93→111→0; MID026
105→70→2; H023 131→121→1.

## Known Legitimate Findings

- **H008 p52 — "Bidding logic acts almost predatorily…"**: genuinely
  left-aligned (lines x1 498.5 / 505.8 / 514.7 vs right margin 523.3). This is
  the only remaining alignment finding and is kept as defensible evidence, not
  noise.
- Remaining Page Layout findings (H007 p58/60, H004 p53, H008 p16/28/61,
  H015 p3, H018 p25/63) are **pre-existing margin overflows** from the
  baseline — out of the heading/alignment/spacing scope.
- Remaining Captions findings (H004, H013, H014, H015, H018, MID026 ×2, H023)
  are pre-existing caption numbering gaps — out of scope, preserved.

## Remaining Work

**No known implementation work remains for this noise-reduction task.** Future
changes (e.g. new validators, grammar/plagiarism integration, caption position
validation) should be treated as separate tasks with their own
before/after corpus measurements. Any change affecting classification,
reconstruction, or validation must still run the complete 12-PDF corpus and
verify category counts before/after.

## Warnings

- Do not reintroduce DPI validation — `checks/image_validator.py` is a
  deliberate no-op; keep `checks/image_checks.py` graph-axis OCR active.
- Do not disable validators or loosen tolerances to lower counts — fix root
  causes in reconstruction/classification instead.
- Do not treat bibliography/reference/appendix as BODY_TEXT for
  alignment/spacing checks.
- Do not report a single stray line as an alignment/spacing violation —
  findings require paragraph-level evidence.
- The final corpus JSON (e.g. `/tmp/opencode/audit_v5.json`) has a stray
  stdout line `warning: The fitz API is deprecated…` on the first line —
  strip it before `json.loads`.
- Root-level `test_*.py` files are legacy debug scripts; run pytest only on
  `tests/`.
- Deferred / out of scope: grammar (external LanguageTool), plagiarism
  (external), research-growth/subtopic/citation/chapter checks (complex,
  legacy ParsedDocument-bound).
