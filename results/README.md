# PDF Format Checker — Results

Generation timestamp: 2026-08-16 20:55 UTC

Validation implementation: `checker.run_checks()` (final, noise-filtered collector) + `reporter/pdf_annotator.generate_annotated_pdf()`. Table extraction: `reporter/table_report_generator.py` (`ingestion/pdf_loader.py` → `TableNode`), caption association replicating `services/table_service.py:_find_caption_for_table`. Generated with `python3 -m reporter.table_report_generator`.

## Contents

- `annotated/` — annotated PDFs (final findings highlighted per severity)
- `tables/` — per-PDF extracted table reports + corpus-wide `index.html` + `_summary.json`
- `summary.json` — machine-readable final violations per PDF

## Corpus

All 12 corpus PDFs in `test_files/`:

- `2026W10140U02H005_22BCE3217.pdf`
- `2026W10140U02H007_22BCE0927.pdf`
- `2026W10140U03H004_22BCB0096.pdf`
- `2026W10140U03H008_22BCE0335.pdf`
- `2026W10167P01H013_24MAI0005.pdf`
- `2026W10167P01H014_24MAI0027.pdf`
- `2026W10167U01H015_22BCE0508.pdf`
- `2026W10167U01H016_22BCE0309.pdf`
- `2026W10167U03H018_22BCE3372.pdf`
- `2026W10230U01H019_22BCE0420.pdf`
- `2026W10243I01H026_21MID0051.pdf`
- `2026W10243P01H023_24MCS0036.pdf`

## Validation summary

Final noise-filtered findings per PDF. Totals include only real finding categories; the Overall Format Score is NOT a finding (see [Overall score](#overall-score)).

| PDF | Total | Headings | Alignment | Spacing | Captions | Page Layout | Other |
|---|---|---|---|---|---|---|---|
| 2026W10140U02H005_22BCE3217.pdf | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026W10140U02H007_22BCE0927.pdf | 4 | 0 | 0 | 0 | 0 | 4 | 0 |
| 2026W10140U03H004_22BCB0096.pdf | 2 | 0 | 0 | 0 | 1 | 1 | 0 |
| 2026W10140U03H008_22BCE0335.pdf | 5 | 0 | 1 | 0 | 0 | 4 | 0 |
| 2026W10167P01H013_24MAI0005.pdf | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| 2026W10167P01H014_24MAI0027.pdf | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| 2026W10167U01H015_22BCE0508.pdf | 2 | 0 | 0 | 0 | 1 | 1 | 0 |
| 2026W10167U01H016_22BCE0309.pdf | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| 2026W10167U03H018_22BCE3372.pdf | 3 | 0 | 0 | 0 | 1 | 2 | 0 |
| 2026W10230U01H019_22BCE0420.pdf | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026W10243I01H026_21MID0051.pdf | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| 2026W10243P01H023_24MCS0036.pdf | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| **Total** | **23** | **0** | **1** | **0** | **8** | **14** | **0** |

## Overall score

The overall format score is a document-level summary metric computed by `utils.scoring.compute_score()` from the same final collector. It is deliberately separate from the findings count.

| PDF | Score | Grade |
|---|---|---|
| 2026W10140U02H005_22BCE3217.pdf | 100 | Excellent |
| 2026W10140U02H007_22BCE0927.pdf | 100 | Excellent |
| 2026W10140U03H004_22BCB0096.pdf | 100 | Excellent |
| 2026W10140U03H008_22BCE0335.pdf | 100 | Excellent |
| 2026W10167P01H013_24MAI0005.pdf | 100 | Excellent |
| 2026W10167P01H014_24MAI0027.pdf | 100 | Excellent |
| 2026W10167U01H015_22BCE0508.pdf | 100 | Excellent |
| 2026W10167U01H016_22BCE0309.pdf | 100 | Excellent |
| 2026W10167U03H018_22BCE3372.pdf | 100 | Excellent |
| 2026W10230U01H019_22BCE0420.pdf | 100 | Excellent |
| 2026W10243I01H026_21MID0051.pdf | 100 | Excellent |
| 2026W10243P01H023_24MCS0036.pdf | 100 | Excellent |

Note: scores are unaffected by INFO/MINOR findings under the current scoring weights, hence 100/100 across the corpus despite 23 real findings.

## Annotated PDFs

- [annotated/2026W10140U02H005_22BCE3217_annotated.pdf](annotated/2026W10140U02H005_22BCE3217_annotated.pdf) — 0 finding(s)
- [annotated/2026W10140U02H007_22BCE0927_annotated.pdf](annotated/2026W10140U02H007_22BCE0927_annotated.pdf) — 4 finding(s)
- [annotated/2026W10140U03H004_22BCB0096_annotated.pdf](annotated/2026W10140U03H004_22BCB0096_annotated.pdf) — 2 finding(s)
- [annotated/2026W10140U03H008_22BCE0335_annotated.pdf](annotated/2026W10140U03H008_22BCE0335_annotated.pdf) — 5 finding(s)
- [annotated/2026W10167P01H013_24MAI0005_annotated.pdf](annotated/2026W10167P01H013_24MAI0005_annotated.pdf) — 1 finding(s)
- [annotated/2026W10167P01H014_24MAI0027_annotated.pdf](annotated/2026W10167P01H014_24MAI0027_annotated.pdf) — 1 finding(s)
- [annotated/2026W10167U01H015_22BCE0508_annotated.pdf](annotated/2026W10167U01H015_22BCE0508_annotated.pdf) — 2 finding(s)
- [annotated/2026W10167U01H016_22BCE0309_annotated.pdf](annotated/2026W10167U01H016_22BCE0309_annotated.pdf) — 2 finding(s)
- [annotated/2026W10167U03H018_22BCE3372_annotated.pdf](annotated/2026W10167U03H018_22BCE3372_annotated.pdf) — 3 finding(s)
- [annotated/2026W10230U01H019_22BCE0420_annotated.pdf](annotated/2026W10230U01H019_22BCE0420_annotated.pdf) — 0 finding(s)
- [annotated/2026W10243I01H026_21MID0051_annotated.pdf](annotated/2026W10243I01H026_21MID0051_annotated.pdf) — 2 finding(s)
- [annotated/2026W10243P01H023_24MCS0036_annotated.pdf](annotated/2026W10243P01H023_24MCS0036_annotated.pdf) — 1 finding(s)

## Extracted tables

- [tables/2026W10140U02H005_22BCE3217_tables.html](tables/2026W10140U02H005_22BCE3217_tables.html)
- [tables/2026W10140U02H007_22BCE0927_tables.html](tables/2026W10140U02H007_22BCE0927_tables.html)
- [tables/2026W10140U03H004_22BCB0096_tables.html](tables/2026W10140U03H004_22BCB0096_tables.html)
- [tables/2026W10140U03H008_22BCE0335_tables.html](tables/2026W10140U03H008_22BCE0335_tables.html)
- [tables/2026W10167P01H013_24MAI0005_tables.html](tables/2026W10167P01H013_24MAI0005_tables.html)
- [tables/2026W10167P01H014_24MAI0027_tables.html](tables/2026W10167P01H014_24MAI0027_tables.html)
- [tables/2026W10167U01H015_22BCE0508_tables.html](tables/2026W10167U01H015_22BCE0508_tables.html)
- [tables/2026W10167U01H016_22BCE0309_tables.html](tables/2026W10167U01H016_22BCE0309_tables.html)
- [tables/2026W10167U03H018_22BCE3372_tables.html](tables/2026W10167U03H018_22BCE3372_tables.html)
- [tables/2026W10230U01H019_22BCE0420_tables.html](tables/2026W10230U01H019_22BCE0420_tables.html)
- [tables/2026W10243I01H026_21MID0051_tables.html](tables/2026W10243I01H026_21MID0051_tables.html)
- [tables/2026W10243P01H023_24MCS0036_tables.html](tables/2026W10243P01H023_24MCS0036_tables.html)

## Corpus table index

- [results/tables/index.html](tables/index.html) — corpus-wide table index (PDF, table node, page, orientation, dimensions, caption, report link)

### Table extraction summary

| PDF | Structural TableNodes | TABLE-classified paragraphs | Captioned | Uncaptioned |
|---|---|---|---|---|
| 2026W10140U02H005_22BCE3217.pdf | 8 | 52 | 3 | 5 |
| 2026W10140U02H007_22BCE0927.pdf | 36 | 14 | 11 | 25 |
| 2026W10140U03H004_22BCB0096.pdf | 7 | 6 | 5 | 2 |
| 2026W10140U03H008_22BCE0335.pdf | 10 | 22 | 10 | 0 |
| 2026W10167P01H013_24MAI0005.pdf | 3 | 2 | 3 | 0 |
| 2026W10167P01H014_24MAI0027.pdf | 5 | 4 | 0 | 5 |
| 2026W10167U01H015_22BCE0508.pdf | 6 | 3 | 6 | 0 |
| 2026W10167U01H016_22BCE0309.pdf | 14 | 13 | 6 | 8 |
| 2026W10167U03H018_22BCE3372.pdf | 18 | 5 | 17 | 1 |
| 2026W10230U01H019_22BCE0420.pdf | 2 | 0 | 1 | 1 |
| 2026W10243I01H026_21MID0051.pdf | 1 | 3 | 1 | 0 |
| 2026W10243P01H023_24MCS0036.pdf | 1 | 1 | 1 | 0 |
| **Total** | 111 | 125 | 64 | 47 |

> Note: "Structural TableNodes" are tables extracted by pdfplumber (actual rows/cells). "TABLE-classified paragraphs" are text blocks the classifier marked as columnar/table layout — two distinct object types, not equivalent (e.g. H005 has 8 TableNodes vs 52 TABLE paragraphs).

## Notes

### Known legitimate findings

- **H008 (alignment):** one genuine left-aligned body paragraph is retained as a real Alignment finding (the accepted single finding in the corpus). All other alignment/spacing noise is suppressed by paragraph-level guards.
- **Captions:** 8 caption-numbering gap findings across the corpus (H004, H013, H014, H015, H018, H026×2, H023). Each finding now carries the real page, bounding box, caption snippet, previous/current caption context, expected/detected values, and classification signals.
- **Page Layout:** 14 MINOR right-margin-overflow findings (H007×4, H004, H008×4, H015, H016×2, H018×2). Since LIST blocks joined the per-line margin check, 5 of these are list items with a long unbreakable token pushed past the right margin: H007 p36 (`kubernetes/deployment.yml`), H007 p46 (`libgomp1`), H008 p56 (`ReentrancyGuard.` at 552.12pt), H016 p29 (`Conv1d(kernel=7),`), H016 p32 (`N)/0.6745`).

### Caption-numbering semantics ambiguity

The live validator (`checks/caption_validator.py`) treats each caption's leading integer as the chapter prefix and requires consecutive numbers to advance by exactly 1 (e.g. "expected 4, found 7" when tables jump from chapter 3 to chapter 7). The template config (`vit_template.json`, `numbering: "chapter_wise"`) and the sibling `checks/caption_checks.py` instead suggest per-chapter sequence validation ("Table 3.1 → Table 3.2 → Table 3.3"). These two semantics disagree; the live behavior is intentionally left unchanged to preserve corpus-locked output. Changing to per-chapter sequence would alter all 8 caption findings and would require continuation-caption handling (e.g. H008's legitimate "Table 2.1 – Continued from previous page" repeats on pages 25-28).

### Annotated PDFs

Annotated PDFs highlight only the final noise-filtered violations (never the raw pre-filter set, and never the Overall Score). Severity key: CRITICAL=red, MAJOR=orange, MINOR=yellow, WARNING=blue, SUGGESTION/INFO=gray. Each annotation carries a popup with category, description, expected/detected, confidence, reason, and suggested fix.

### Tables

- Page numbers in table reports are PDF page numbers (1-based); the implementation does not separately extract printed page numbers.
- Rotated/landscape tables (e.g. H005 pages 18-21) are detected by the dominant PyMuPDF text direction inside the table bbox; cells are re-extracted from PyMuPDF lines (which read rotated text correctly) and the grid re-ordered to its natural reading orientation. Reports render these in a horizontally scrollable container with a sticky header.
- Known preserved cases: H005 p33 Tables 3.2/3.3 (6×3 / 7×2, split from merged rows); H018 p37 multiline table stays 25×4 (legitimate, not over-split); H018 p43 false-positive table stays 8×6 and empty.
- Captions are associated via `TABLE_CAPTION_PATTERN` proximity above the table on the same page; uncaptioned tables (e.g. continuation tables with internal header rows) are marked "No caption detected".

## Machine-readable summary

`results/summary.json` holds the final collector state per PDF: `filename`, `total` (real findings only), and the full `violations` array (category, severity, page, description, expected, detected, confidence, reason, suggested_fix, location, bbox). Category counts, severity counts, overall score/grade, annotated-PDF path, and table-report path are derived views presented in this README.
