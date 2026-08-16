"""tests/test_table_reports.py

Regression tests for the table-report generation layer
(reporter/table_report_generator), specifically the rotated / landscape
handling added for H005 pages 18-21.

pdfplumber extracts cell text by sorting characters on (top, x0), which is
wrong for 90°-rotated text, so rotated tables used to render reversed and
scrambled.  The report layer re-extracts rotated cell text from PyMuPDF lines
(which read rotated text correctly) and re-orders the grid into its natural
reading orientation via a pure grid transform.  These tests lock in:

  * the grid transform for portrait, landscape, 180°, and opposite rotations
  * reading-order line sorting inside rotated cells
  * direction detection from line directions
  * cell-bbox -> table matching
  * NO string reversal anywhere in the transform (only grid permutation)
  * portrait tables pass through unchanged
"""
from __future__ import annotations

import glob
from pathlib import Path

import pytest

from reporter.table_report_generator import (
    _detect_direction,
    _join_words,
    _line_sort_key,
    _match_table,
    _orient_cells,
    _orient_grid,
    _rotated_cell_text,
    _split_merged_rows,
    _words_in_bbox,
)

BASE_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = BASE_DIR / "test_files"
H005 = CORPUS_DIR / "2026W10140U02H005_22BCE3217.pdf"
H008 = CORPUS_DIR / "2026W10140U03H008_22BCE0335.pdf"
H018 = CORPUS_DIR / "2026W10167U03H018_22BCE3372.pdf"


# ── portrait word spacing ─────────────────────────────────────────────────
def test_join_words_restores_spaces_within_line():
    words = [
        {"x0": 319.2, "x1": 329.4, "top": 228.1, "bottom": 237.5, "text": "Specification"},
        {"x0": 302.0, "x1": 308.0, "top": 228.1, "bottom": 237.5, "text": "The"},
    ]
    assert _join_words(words) == "The Specification"


def test_join_words_preserves_multiline_cells():
    words = [
        {"x0": 200.0, "x1": 210.0, "top": 242.2, "bottom": 251.6, "text": "Mean"},
        {"x0": 214.0, "x1": 228.0, "top": 242.2, "bottom": 251.6, "text": "duration"},
        {"x0": 200.0, "x1": 215.0, "top": 256.7, "bottom": 266.1, "text": "between"},
        {"x0": 218.0, "x1": 232.0, "top": 256.7, "bottom": 266.1, "text": "lines"},
    ]
    assert _join_words(words) == "Mean duration\nbetween lines"


def test_words_in_bbox_excludes_words_below_band_edge():
    # A word whose top is 1.7pt below the band bottom must NOT leak in
    words = [
        {"x0": 200.0, "x1": 210.0, "top": 242.2, "bottom": 251.6, "text": "CPU"},
    ]
    assert _words_in_bbox(words, (195.9, 225.6, 268.1, 240.5)) == []
    words2 = [
        {"x0": 200.0, "x1": 210.0, "top": 233.0, "bottom": 242.4, "text": "Comp"},
    ]
    assert [w["text"] for w in _words_in_bbox(words2, (195.9, 225.6, 268.1, 240.5))] == ["Comp"]


def test_split_merged_rows_only_when_line_counts_match():
    assert _split_merged_rows([["A\nB", "1\n2"]]) == [["A", "1"], ["B", "2"]]
    # legitimate multiline cell: unequal line counts must not be split
    assert _split_merged_rows([["A\nB", "1"]]) == [["A\nB", "1"]]


# ── pure grid transform ───────────────────────────────────────────────────
def test_portrait_grid_unchanged():
    grid = [["A", "B", "C"], ["D", "E", "F"]]
    assert _orient_grid(grid, (1.0, 0.0)) == grid


def test_landscape_grid_transposed():
    grid = [
        ["Relevance", "r1", "r2"],   # pdfplumber row 0 = bottom-most natural col
        ["Venue", "v1", "v2"],
        ["Year", "2024", "2025"],    # pdfplumber row 2 = natural header column
    ]
    out = _orient_grid(grid, (0.0, -1.0))
    assert out[0] == ["Year", "Venue", "Relevance"]
    assert out[1] == ["2024", "v1", "r1"]
    assert out[2] == ["2025", "v2", "r2"]


def test_landscape_grid_matches_h005_shape():
    grid = [[f"r{r}c{c}" for c in range(11)] for r in range(6)]
    out = _orient_grid(grid, (0.0, -1.0))
    assert len(out) == 11
    assert all(len(r) == 6 for r in out)
    assert out[0] == [grid[5][0], grid[4][0], grid[3][0],
                      grid[2][0], grid[1][0], grid[0][0]]
    assert out[1] == [grid[5][1], grid[4][1], grid[3][1],
                      grid[2][1], grid[1][1], grid[0][1]]


def test_opposite_landscape_grid_transposed():
    grid = [
        ["Year", "2024", "2025"],
        ["Venue", "v1", "v2"],
        ["Relevance", "r1", "r2"],
    ]
    out = _orient_grid(grid, (0.0, 1.0))
    assert out[0] == ["Year", "Venue", "Relevance"]
    assert out[1] == ["2024", "v1", "r1"]
    assert out[2] == ["2025", "v2", "r2"]


def test_upside_down_grid_flipped():
    grid = [["A", "B"], ["C", "D"]]
    assert _orient_grid(grid, (-1.0, 0.0)) == [["D", "C"], ["B", "A"]]


def test_transform_never_reverses_cell_strings():
    cells = ["abcdef", "ghijkl", "mnopqr", "stuvwx"]
    grid = [cells[0:2], cells[2:]]
    for direction in ((1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
        for row in _orient_grid(grid, direction):
            for cell in row:
                assert cell in cells  # identity preserved, only positions move


def test_orient_cells_matches_orient_grid():
    cells = [[(i, j, i + 1, j + 1) for j in range(3)] for i in range(2)]
    out = _orient_cells(cells, (0.0, -1.0))
    assert len(out) == 3 and len(out[0]) == 2


# ── reading order inside rotated cells ────────────────────────────────────
def test_rotated_cell_text_reading_order():
    direction = (0.0, -1.0)  # reads bottom-to-top; successive lines go right
    lines = [
        ((38.7, 244.5, 51.9, 499.7), "line one", direction),
        ((52.3, 469.4, 65.4, 499.7), "line two", direction),
        ((52.3, 426.0, 65.4, 465.4), "line three", direction),
    ]
    cell = (36.3, 238.4, 108.5, 505.9)
    assert _rotated_cell_text(lines, cell, direction) == "line one line two line three"


def test_line_sort_key_respects_direction():
    k = _line_sort_key((38.7, 244.5, 51.9, 499.7), (0.0, -1.0))
    assert k[1] < 0  # dot(center, R=(0,-1)) is negative for y-down coords


# ── direction detection ───────────────────────────────────────────────────
def test_detect_direction_vertical_wins():
    bbox = (18.0, 15.0, 582.0, 770.0)
    lines = [
        ((20.3, 741.7, 34.5, 763.5), "", (0.0, -1.0)),
        ((20.3, 701.2, 34.5, 722.8), "", (0.0, -1.0)),
        ((312.0, 788.0, 330.0, 800.0), "", (1.0, 0.0)),  # page number, outside bbox
    ]
    assert _detect_direction(lines, bbox) == (0.0, -1.0)


def test_detect_direction_defaults_to_portrait_without_text():
    assert _detect_direction([], (0, 0, 100, 100)) == (1.0, 0.0)


# ── table matching ────────────────────────────────────────────────────────
def test_match_table_picks_largest_overlap():
    class T:
        def __init__(self, bbox):
            self.bbox = bbox

    tables = [T((0, 0, 50, 50)), T((40, 40, 200, 200)), T((300, 300, 400, 400))]
    assert _match_table(tables, (45, 45, 100, 100)).bbox == (40, 40, 200, 200)


# ── corpus-level: real rotated tables render readable ─────────────────────
@pytest.mark.slow
@pytest.mark.skipif(not H005.exists(), reason="test_files/ corpus not present")
def test_h005_rotated_tables_readable():
    from checker import run_checks
    from reporter.table_report_generator import _build_tables

    doc, _ = run_checks(H005)
    tables = _build_tables(doc, H005)
    rotated = [t for t in tables if "landscape" in t["orientation"]]
    assert len(rotated) == 4  # pages 18-21
    for t in rotated:
        header = t["rows"][0]
        assert header == ["Year", "Title", "Authors", "Abstract", "Venue", "Relevance"]
        assert all(isinstance(c, str) and c for c in t["rows"][1])
    joined = " ".join(c for t in rotated for r in t["rows"] for c in r)
    assert "LLM-based" in joined
    assert "ecnaveleR" not in joined  # no reversed cell text anywhere


# ── corpus-level: merged rows + lost word spacing on portrait tables ──────
@pytest.mark.slow
@pytest.mark.skipif(not H005.exists(), reason="test_files/ corpus not present")
def test_h005_page33_merged_rows_split():
    """Tables 3.2/3.3 on page 33 were 2-row merged monsters; now 6x3 and 7x2."""
    from checker import run_checks
    from reporter.table_report_generator import _build_tables

    doc, _ = run_checks(H005)
    tables = [t for t in _build_tables(doc, H005) if t["page"] == 33]
    assert len(tables) == 2

    t62 = tables[0]
    assert len(t62["rows"]) == 6
    assert all(len(r) == 3 for r in t62["rows"])
    assert t62["rows"][0] == ["Component", "Technology Used", "Purpose"]
    assert t62["rows"][1][0] == "Frontend"

    t72 = tables[1]
    assert len(t72["rows"]) == 7
    assert t72["rows"][0] == ["Step", "Description"]
    assert t72["rows"][3] == ["Validation", "Backend verifies correctness of code"]

    joined = " ".join(c for t in tables for r in t["rows"] for c in r)
    assert "Technology Used" in joined
    assert "TechnologyUsed" not in joined  # concatenated-word artifact gone


@pytest.mark.slow
@pytest.mark.skipif(not H018.exists(), reason="test_files/ corpus not present")
def test_h018_legitimate_multiline_tables_not_oversplit():
    """Tables whose rows wrap text (no interior row rules) must stay intact."""
    from checker import run_checks
    from reporter.table_report_generator import _build_tables

    doc, _ = run_checks(H018)
    tables = [t for t in _build_tables(doc, H018) if t["page"] == 37]
    t5 = tables[0]
    assert len(t5["rows"]) == 25
    assert all(len(r) == 4 for r in t5["rows"])
    assert any("\n" in c for r in t5["rows"] for c in r)  # multiline cells preserved


@pytest.mark.slow
@pytest.mark.skipif(not H018.exists(), reason="test_files/ corpus not present")
def test_h018_empty_false_positive_table_stays_empty():
    """p43 table is a graph-axis false positive; rebuild must not invent rows."""
    from checker import run_checks
    from reporter.table_report_generator import _build_tables

    doc, _ = run_checks(H018)
    tables = [t for t in _build_tables(doc, H018) if t["page"] == 43]
    assert tables
    for t in tables:
        assert sum(len(c) for r in t["rows"] for c in r) == 0


@pytest.mark.slow
@pytest.mark.skipif(not H008.exists(), reason="test_files/ corpus not present")
def test_h008_p46_wide_merged_table_split_into_rows():
    from checker import run_checks
    from reporter.table_report_generator import _build_tables

    doc, _ = run_checks(H008)
    tables = [t for t in _build_tables(doc, H008) if t["page"] == 46]
    assert len(tables) == 1
    assert len(tables[0]["rows"]) == 18
    assert tables[0]["rows"][0] == ["Category", "Tests", "Description"]
    assert tables[0]["rows"][1][0] == "Contract Deployment"
