"""Generate per-PDF HTML table reports from the existing pipeline's TableNodes.

Read-only w.r.t. validation: uses checker.run_checks (the current pipeline) to
build the DOM, then renders every structural TableNode produced by pdfplumber
into a human-readable HTML report. Caption association replicates
services.table_service._find_caption_for_table exactly (pandas-free copy).
No validation logic is modified.

Rotated / landscape tables
--------------------------
pdfplumber extracts cell text by sorting characters on ``(top, x0)``, which is
wrong for 90°-rotated text: a rotated table's cells come back reversed and
scrambled (e.g. "ecnaveleR" instead of "Relevance").  Rather than touching the
extraction pipeline (which other validators depend on), the *report* layer
fixes this:

  1. Detect the dominant text direction of the lines inside the table bbox
     from PyMuPDF (``fitz``), which reads rotated text in the correct order.
  2. For tables whose text runs vertically (``|dy| > |dx|``), re-extract each
     cell's text from the ``fitz`` lines that intersect the pdfplumber cell
     bbox, sorted in the cell's natural reading order.
  3. Re-order the grid into its natural reading orientation (papers/rows,
     attributes/columns) via a pure grid transform derived from the direction
     vector.  Normal portrait tables are rendered exactly as pdfplumber built
     them.
  4. Wide / landscape tables are rendered inside a horizontally scrollable
     container with a sticky header instead of being squashed.

The transform never reverses whole strings; it only permutes grid positions
based on the detected reading direction.
"""
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pdfplumber

from checker import run_checks
from utils.constants import TABLE_CAPTION_PATTERN

ROOT = Path(__file__).resolve().parent.parent
TEST_FILES = ROOT / "test_files"
OUT = ROOT / "results"
TABLES_DIR = OUT / "tables"

_PAGE_CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
       margin: 2rem auto; max-width: 1200px; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 1.6rem; border-bottom: 2px solid #333; padding-bottom: 0.3rem; }
h2 { font-size: 1.25rem; margin-top: 2rem; color: #222; }
.table-container { overflow-x: auto; width: 100%; border: 1px solid #ddd;
                   border-radius: 4px; }
table { border-collapse: collapse; margin: 1rem 0; width: 100%;
        font-size: 0.9rem; min-width: 100%; }
th, td { border: 1px solid #bbb; padding: 6px 10px; text-align: left;
         vertical-align: top; word-break: break-word; min-width: 8rem; }
th { background: #eef1f6; font-weight: 600; position: sticky; top: 0; }
tr:nth-child(even) td { background: #fafbfc; }
.meta { color: #444; }
.caption { font-style: italic; margin: 0.5rem 0; }
.summary { border-collapse: collapse; }
.none { color: #888; font-style: italic; }
a { color: #0366d6; }
"""


def _find_caption_for_table(tbl_node, doc) -> tuple[str, str]:
    """Replicates services/table_service.py:_find_caption_for_table (pandas-free)."""
    page = next((p for p in doc.pages if p.page_num == tbl_node.page_num), None)
    if not page:
        return "", ""
    paragraphs = page.get_paragraphs()
    above_paras = [p for p in paragraphs if p.bbox.y1 <= tbl_node.bbox.y0 + 30]
    above_paras.sort(key=lambda p: p.bbox.y1, reverse=True)
    for p in above_paras:
        text = p.text.strip()
        if TABLE_CAPTION_PATTERN.match(text):
            m = re.search(r"(\d+\.\d+)", text)
            num = m.group(1) if m else ""
            return num, text
        if tbl_node.bbox.y0 - p.bbox.y1 > 100:
            break
    return "", ""


def _page_lines(fitz_doc, page_num):
    """Return (bbox, text, direction) for every line on a 1-based page."""
    page = fitz_doc[page_num - 1]
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            d = line.get("dir") or (1.0, 0.0)
            text = "".join(s.get("text", "") for s in line.get("spans", []))
            out.append((tuple(line["bbox"]), text, d))
    return out


def _detect_direction(lines, bbox, tol=2.0):
    """Dominant text direction ((dx, dy)) of lines overlapping ``bbox``.

    Returns (1.0, 0.0) when no usable text overlaps the region, so tables
    without text (e.g. graph-axis false positives) stay untouched.
    """
    bx0, by0, bx1, by1 = bbox
    counts: dict[tuple, int] = {}
    for line_bbox, _text, d in lines:
        x0, y0, x1, y1 = line_bbox
        if x0 > bx1 + tol or x1 < bx0 - tol or y0 > by1 + tol or y1 < by0 - tol:
            continue
        key = (round(d[0], 2), round(d[1], 2))
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return (1.0, 0.0)
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _orient_grid(rows, direction):
    """Reorder a pdfplumber text grid into its natural reading orientation.

    Pure grid transform derived from the text direction vector (fitz y-down
    coordinates).  ``rows`` are pdfplumber's rows (top-to-bottom bands), each
    a list of cell strings (left-to-right bands).

    * ``|dx| >= |dy|`` (horizontal text): rows/cols are already in reading
      order; a 180° text direction (dx < 0) flips both axes.
    * ``|dy| > |dx|`` (vertical text): the table is physically rotated.
      pdfplumber's y-bands become natural *columns* (they progress along the
      reading direction R) and its x-bands become natural *rows* (they
      progress along the perpendicular P).  The sign of dy decides which
      y-band is the first column (the header / label column).

    Never reverses strings — only permutes grid positions.
    """
    dx, dy = direction
    if abs(dx) >= abs(dy):
        if dx < 0:
            return [list(reversed(r)) for r in reversed(rows)]
        return rows
    nrows = len(rows)
    ncols = max((len(r) for r in rows), default=0)
    result = [[None] * nrows for _ in range(ncols)]
    for r, row in enumerate(rows):
        for c in range(ncols):
            val = row[c] if c < len(row) else None
            if dy < 0:
                result[c][nrows - 1 - r] = val
            else:
                result[c][r] = val
    return result


def _orient_cells(cells, direction):
    """Reorder a pdfplumber cell-bbox grid with ``_orient_grid`` semantics."""
    dx, dy = direction
    if abs(dx) >= abs(dy):
        if dx < 0:
            return [list(reversed(r)) for r in reversed(cells)]
        return cells
    nrows = len(cells)
    ncols = max((len(r) for r in cells), default=0)
    result = [[None] * nrows for _ in range(ncols)]
    for r, row in enumerate(cells):
        for c in range(ncols):
            val = row[c] if c < len(row) else None
            if dy < 0:
                result[c][nrows - 1 - r] = val
            else:
                result[c][r] = val
    return result


def _line_sort_key(bbox, direction):
    """Reading-order key for a text line inside a cell.

    Lines stack along the perpendicular P = (-dy, dx); within a line, text
    progresses along R = (dx, dy).  Sorting by (dot(center, P),
    dot(center, R)) yields the cell's natural reading order for any rotation.
    """
    dx, dy = direction
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    return (-dy * cx + dx * cy, dx * cx + dy * cy)


def _rotated_cell_text(lines, cell, direction, tol=4.0):
    """Reconstruct one rotated cell's text from intersecting fitz lines."""
    bx0, by0, bx1, by1 = cell
    hits = []
    for bbox, text, d in lines:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        if bx0 - tol <= cx <= bx1 + tol and by0 - tol <= cy <= by1 + tol:
            hits.append((bbox, text))
    if not hits:
        return ""
    hits.sort(key=lambda pair: _line_sort_key(pair[0], direction))
    return " ".join(t for _b, t in hits)


def _match_table(tables, bbox):
    """Pick the pdfplumber Table whose bbox overlaps ``bbox`` the most."""
    tx0, ty0, tx1, ty1 = bbox
    best, best_area = None, 0.0
    for table in tables:
        b = table.bbox
        ox0, oy0 = max(b[0], tx0), max(b[1], ty0)
        ox1, oy1 = min(b[2], tx1), min(b[3], ty1)
        area = max(0.0, ox1 - ox0) * max(0.0, oy1 - oy0)
        if area > best_area:
            best, best_area = table, area
    return best


def _extract_rotated_table(pdf_path, tbl, direction):
    """Rebuild a rotated table's rows via pdfplumber cell bboxes + fitz text.

    pdfplumber still supplies the authoritative grid geometry (the cell
    bboxes); PyMuPDF supplies the correctly-ordered text for each cell.
    """
    lines = _page_lines(fitz.open(str(pdf_path)), tbl.page_num)
    bbox = (tbl.bbox.x0, tbl.bbox.y0, tbl.bbox.x1, tbl.bbox.y1)
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[tbl.page_num - 1]
        table = _match_table(page.find_tables(), bbox)
    if table is None:
        return _orient_grid(tbl.rows, direction)
    rows = []
    for r in table.rows:
        row = []
        for c in range(len(r.cells)):
            cell = r.cells[c]
            if cell is None:
                row.append("")
            else:
                row.append(_rotated_cell_text(lines, cell, direction))
        rows.append(row)
    return _orient_grid(rows, direction)


def _cluster(values, tol=2.0):
    """Cluster sorted floats within ``tol``; return cluster means."""
    clusters = []
    for v in sorted(values):
        if clusters and abs(v - clusters[-1][-1]) <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def _vertical_endpoints(page, bbox, tol=2.0):
    """Vertical-segment endpoints inside ``bbox`` keyed by Y position.

    Each value is the set of distinct X positions that share an endpoint at
    that Y.  A Y shared by >= 2 vertical columns is strong evidence of a real
    row separator in tables drawn without interior horizontal rules.
    """
    bx0, by0, bx1, by1 = bbox
    by_y: dict[float, set] = {}
    for line in page.lines:
        x0, top, x1, bottom = line["x0"], line["top"], line["x1"], line["bottom"]
        if abs(x1 - x0) >= 0.5:
            continue
        if not (bx0 - tol <= x0 <= bx1 + tol):
            continue
        if bottom < by0 - tol or top > by1 + tol:
            continue
        for y in (top, bottom):
            by_y.setdefault(round(y, 1), set()).add(round(x0, 1))
    for r in page.rects:
        x0, top, x1, bottom = r["x0"], r["top"], r["x1"], r["bottom"]
        if x1 - x0 >= 0.5:
            continue
        if not (bx0 - tol <= x0 <= bx1 + tol):
            continue
        if bottom < by0 - tol or top > by1 + tol:
            continue
        for y in (top, bottom):
            by_y.setdefault(round(y, 1), set()).add(round(x0, 1))
    return by_y


def _col_boundaries(ptable):
    """Column boundary X positions from the pdfplumber table's cell edges."""
    xs = set()
    for row in ptable.rows:
        for cell in row.cells:
            if cell is None:
                continue
            xs.add(cell[0])
            xs.add(cell[2])
    return _cluster(sorted(xs), 2.0)


def _band_index(bounds, value, tol=3.0):
    """Return the band index containing ``value``, or None if out of range."""
    for i in range(len(bounds) - 1):
        if bounds[i] - tol <= value <= bounds[i + 1] + tol:
            return i
    return None


def _join_words(words):
    """Join words into lines with proper spaces; lines separated by newlines.

    pdfplumber's ``Table.extract()`` joins adjacent words without spaces when
    the PDF uses tight kerning (e.g. "TechnologyUsed" instead of
    "Technology Used").  Words are reconstructed here from their coordinates:
    same-line words get a single space, distinct text lines get a newline.
    """
    if not words:
        return ""
    ordered = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    cur = [ordered[0]]
    cur_bottom = ordered[0]["bottom"]
    for w in ordered[1:]:
        if w["top"] < cur_bottom - 1.0:
            cur.append(w)
            cur_bottom = max(cur_bottom, w["bottom"])
        else:
            lines.append(cur)
            cur = [w]
            cur_bottom = w["bottom"]
    lines.append(cur)
    return "\n".join(
        " ".join(w["text"] for w in sorted(ln, key=lambda w: w["x0"]))
        for ln in lines)


def _words_in_bbox(words, bbox, tol=2.0):
    bx0, by0, bx1, by1 = bbox
    out = []
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2.0
        cy = (w["top"] + w["bottom"]) / 2.0
        if (bx0 - tol <= cx <= bx1 + tol
                and by0 - tol <= cy <= by1 + tol):
            out.append(w)
    return out


def _grid_from_bounds(words, row_bounds, col_bounds):
    """Build a text grid by assigning words to (row-band, col-band) cells.

    Returns ``(grid, placed_count)`` where ``placed_count`` is the number of
    words that could be assigned to a cell (used for coverage validation).
    """
    nrows = len(row_bounds) - 1
    ncols = len(col_bounds) - 1
    grid = [[[] for _ in range(ncols)] for _ in range(nrows)]
    placed = 0
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2.0
        cy = (w["top"] + w["bottom"]) / 2.0
        r = _band_index(row_bounds, cy)
        c = _band_index(col_bounds, cx)
        if r is None or c is None:
            continue
        grid[r][c].append(w)
        placed += 1
    out = [[_join_words(grid[r][c]) for c in range(ncols)] for r in range(nrows)]
    return out, placed


def _split_merged_rows(rows):
    """Split rows whose cells were merged by pdfplumber (newline-separated).

    pdfplumber collapses several logical rows into one merged cell per column
    (each logical row separated by a newline).  A row is split only when ALL
    non-empty cells carry the SAME number of line segments K > 1 — a
    legitimate multiline cell inside an otherwise well-formed row leaves the
    counts unequal and stays unsplit.
    """
    out = []
    for row in rows:
        segs = [
            t.split("\n") if isinstance(t, str) else ["" if t is None else str(t)]
            for t in row
        ]
        counts = sorted({len(s) for s in segs if any(x.strip() for x in s)})
        if len(counts) == 1 and counts[0] > 1:
            k = counts[0]
            out.extend([
                [seg[i] if i < len(seg) else "" for seg in segs]
                for i in range(k)
            ])
        else:
            out.append(row)
    return out


def _accept_rebuilt(grid, original_rows, coverage, tol=0.7):
    """Accept a rebuilt grid only if it is structurally sane.

    ``coverage`` is the fraction of the table's words that ended up inside a
    cell (0.0-1.0); a rebuild that drops most of the words (e.g. wrong
    boundaries) is rejected.  Pass ``coverage=None`` to skip the check.
    """
    if not grid or not grid[0]:
        return False
    ncols = len(grid[0])
    if any(len(r) != ncols for r in grid):
        return False
    if any(c is None for r in grid for c in r):
        return False
    if len(grid) < len(original_rows):
        return False
    if coverage is not None and coverage < tol:
        return False
    return True


def _rebuild_portrait_table(pdf_path, tbl):
    """Reconstruct a portrait table's grid from page geometry.

    Fixes two pdfplumber ``Table.extract()`` defects without touching the
    validation pipeline:

      1. Merged rows — tables drawn without interior horizontal rules (row
         separators implied only by segmented vertical rules) collapse
         several logical rows into one cell.  pdfplumber's own row bands are
         kept as the primary structure; a row is split ONLY when its band
         contains vertical-segment endpoints shared by >= 2 column positions
         (real row separators).  Legitimate multiline cells leave no such
         endpoints and are never split.
      2. Lost word spacing — every cell is re-built from pdfplumber word
         objects (``extract_words``) instead of the lossy layout heuristic,
         joining same-line words with spaces.

    Falls back to the original ``tbl.rows`` when nothing better can be built.
    """
    bbox = (tbl.bbox.x0, tbl.bbox.y0, tbl.bbox.x1, tbl.bbox.y1)
    with pdfplumber.open(str(pdf_path)) as pdf:
        page = pdf.pages[tbl.page_num - 1]
        ptable = _match_table(page.find_tables(), bbox)
        if ptable is None:
            return tbl.rows
        page_words = page.extract_words(x_tolerance=1, y_tolerance=1)
        words = _words_in_bbox(page_words, bbox)
        endpoints = _vertical_endpoints(page, bbox)
        col_bounds = _col_boundaries(ptable)

        rows = []
        placed = 0
        for prow in ptable.rows:
            top, bottom = prow.bbox[1], prow.bbox[3]
            interior = sorted(
                y for y, xs in endpoints.items()
                if top + 2.0 < y < bottom - 2.0 and len(xs) >= 2)
            if interior:
                sub, placed_in_sub = _grid_from_bounds(
                    words, [top] + interior + [bottom], col_bounds)
                placed += placed_in_sub
                rows.extend(sub)
                continue
            row = []
            for cell in prow.cells:
                if cell is None:
                    row.append("")
                    continue
                cw = _words_in_bbox(page_words, cell)
                placed += len(cw)
                row.append(_join_words(cw))
            rows.append(row)

        coverage = (placed / len(words)) if words else None
        if _accept_rebuilt(rows, tbl.rows, coverage):
            return rows

        split = _split_merged_rows(rows)
        if _accept_rebuilt(split, tbl.rows, coverage):
            return split
        return tbl.rows


def _orientation_label(direction, page_width, page_height):
    dx, dy = direction
    if abs(dy) > abs(dx):
        return "landscape (rotated 90° text)", "landscape"
    if page_width > page_height:
        return "landscape page", "landscape"
    return "portrait", "portrait"


def _cell_html(cell) -> str:
    if cell is None:
        return '<span class="none">(empty)</span>'
    text = str(cell)
    text = html.escape(text)
    text = text.replace("\n", "<br>")
    return text


def _table_html(rows: list) -> str:
    if not rows:
        return '<p class="none">No rows extracted for this table.</p>'
    max_cols = max(len(r) for r in rows)
    use_header = len(rows) > 1 and all(c not in (None, "") for c in rows[0])
    thead = ""
    if use_header:
        thead = "<thead><tr>" + "".join(
            f"<th>{_cell_html(c)}</th>" for c in rows[0]) + "</tr></thead>"
        data_rows = rows[1:]
    else:
        data_rows = rows
    tbody = []
    for row in data_rows:
        cells = []
        for i in range(max_cols):
            c = row[i] if i < len(row) else None
            cells.append(f"<td>{_cell_html(c)}</td>")
        tbody.append("<tr>" + "".join(cells) + "</tr>")
    return (f"<div class='table-container'><table>\n{thead}<tbody>\n"
            + "\n".join(tbody) + "\n</tbody></table></div>")


def _report_html(pdf_name: str, tables: list[dict], table_para_count: int) -> str:
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
             f"<title>Tables — {html.escape(pdf_name)}</title>",
             f"<style>{_PAGE_CSS}</style></head><body>"]
    parts.append(f"<h1>Tables — {html.escape(pdf_name)}</h1>")
    parts.append(f"<p class='meta'>PDF: {html.escape(pdf_name)}</p>")
    parts.append(f"<p class='meta'>Total detected tables: {len(tables)}</p>")
    parts.append(
        f"<p class='meta'>Structural TableNodes (pdfplumber): {len(tables)} | "
        f"TABLE-classified paragraphs (classifier): {table_para_count}</p>"
    )
    parts.append("<p class='meta'>Page numbers are PDF page numbers "
                 "(1-based). Printed page numbers are not separately "
                 "extracted by the current implementation.</p>")

    parts.append("<h2>Summary</h2>")
    parts.append("<table class='summary'><tr><th>Table</th><th>PDF Page</th>"
                 "<th>Orientation</th><th>Rows × Cols</th><th>Caption</th></tr>")
    for i, t in enumerate(tables, 1):
        cap = html.escape(t["caption"]) if t["caption"] else '<span class="none">No caption detected</span>'
        parts.append(f"<tr><td>{i}</td><td>{t['page']}</td>"
                     f"<td>{html.escape(t['orientation'])}</td>"
                     f"<td>{len(t['rows'])} × {max((len(r) for r in t['rows']), default=0)}</td>"
                     f"<td>{cap}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Extracted Tables</h2>")
    for i, t in enumerate(tables, 1):
        parts.append(f"<h2>Table {i}</h2>")
        parts.append(f"<p class='meta'>Page: {t['page']} (PDF page number) | "
                     f"Orientation: {html.escape(t['orientation'])}</p>")
        if t["caption"]:
            num = f" (caption number: {t['table_number']})" if t["table_number"] else ""
            parts.append(f"<p class='caption'>Caption: {html.escape(t['caption'])}{num}</p>")
        else:
            parts.append('<p class="caption">Caption: No caption detected</p>')
        parts.append(_table_html(t["rows"]))

    parts.append("</body></html>")
    return "\n".join(parts)


def _build_tables(doc, pdf_path):
    """Collect TableNodes, applying rotation handling where detected."""
    tables = []
    with fitz.open(str(pdf_path)) as fitz_doc:
        for page in doc.pages:
            for tbl in page.get_tables():
                bbox = (tbl.bbox.x0, tbl.bbox.y0, tbl.bbox.x1, tbl.bbox.y1)
                lines = _page_lines(fitz_doc, tbl.page_num)
                direction = _detect_direction(lines, bbox)
                label, _kind = _orientation_label(
                    direction, fitz_doc[tbl.page_num - 1].rect.width,
                    fitz_doc[tbl.page_num - 1].rect.height)
                dx, dy = direction
                if abs(dy) > abs(dx):
                    rows = _extract_rotated_table(pdf_path, tbl, direction)
                else:
                    rows = _rebuild_portrait_table(pdf_path, tbl)
                num, cap = _find_caption_for_table(tbl, doc)
                tables.append({
                    "page": tbl.page_num,
                    "bbox": bbox,
                    "rows": rows,
                    "table_number": num,
                    "caption": cap,
                    "orientation": label,
                })
    return tables


def generate_table_reports(pdf_paths, out_dir: Path) -> dict:
    """Render per-PDF table reports plus index/summary; returns corpus dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus = []
    total_nodes = 0
    total_paras = 0
    total_caps = 0
    total_nocap = 0

    for pdf in pdf_paths:
        pdf = Path(pdf)
        print(f"[{pdf.name}] running pipeline ...", flush=True)
        doc, _collector = run_checks(pdf)

        tables = _build_tables(doc, pdf)

        table_para_count = sum(
            1 for p in doc.get_all_paragraphs() if p.block_type.value == "TABLE"
        )

        total_nodes += len(tables)
        total_paras += table_para_count
        caps = sum(1 for t in tables if t["caption"])
        nocaps = len(tables) - caps
        total_caps += caps
        total_nocap += nocaps

        out = out_dir / f"{pdf.stem}_tables.html"
        out.write_text(_report_html(pdf.name, tables, table_para_count))

        corpus.append({
            "pdf": pdf.name,
            "report": f"tables/{pdf.stem}_tables.html",
            "nodes": len(tables),
            "para": table_para_count,
            "captioned": caps,
            "uncaptioned": nocaps,
            "tables": tables,
        })
        print(f"  -> {len(tables)} TableNodes, {table_para_count} TABLE paras, "
              f"{caps} captioned / {nocaps} uncaptioned | {out.name}")

    _write_index(out_dir, corpus)
    _write_summary(out_dir, corpus, total_nodes, total_paras, total_caps,
                   total_nocap)
    return corpus


def _write_index(out_dir: Path, corpus: list[dict]) -> None:
    rows = []
    for c in corpus:
        for i, t in enumerate(c["tables"], 1):
            cap = html.escape(t["caption"]) if t["caption"] else '<span class="none">No caption</span>'
            rows.append(
                f"<tr><td>{html.escape(c['pdf'])}</td><td>{c['nodes']}</td>"
                f"<td>{i}</td><td>{t['page']}</td>"
                f"<td>{html.escape(t['orientation'])}</td><td>{cap}</td>"
                f"<td><a href='{html.escape(c['report'])}'>report</a></td></tr>"
            )
    index = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Corpus Table Index</title>",
        f"<style>{_PAGE_CSS}</style></head><body>",
        "<h1>Corpus-Wide Extracted Table Index</h1>",
        f"<p class='meta'>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>",
        "<p class='meta'>Page numbers are PDF page numbers (1-based).</p>",
        "<table><tr><th>PDF</th><th>Number of Tables</th><th>Table</th><th>Page</th>"
        "<th>Orientation</th><th>Caption</th><th>Report</th></tr>",
        *rows,
        "</table>",
        "</body></html>",
    ]
    (out_dir / "index.html").write_text("\n".join(index))


def _write_summary(out_dir: Path, corpus: list[dict], total_nodes: int,
                   total_paras: int, total_caps: int, total_nocap: int) -> None:
    (out_dir / "_summary.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdfs": [
            {"filename": c["pdf"], "table_nodes": c["nodes"],
             "table_paragraphs": c["para"],
             "captioned": c["captioned"], "uncaptioned": c["uncaptioned"],
             "landscape_tables": sum(
                 1 for t in c["tables"] if "landscape" in t["orientation"])}
            for c in corpus
        ],
        "totals": {
            "pdfs": len(corpus),
            "table_nodes": total_nodes,
            "table_paragraphs": total_paras,
            "captioned": total_caps,
            "uncaptioned": total_nocap,
        },
    }, indent=2), encoding="utf-8")


def main() -> None:
    pdfs = sorted(TEST_FILES.glob("*.pdf"))
    assert len(pdfs) == 12, f"expected 12 corpus PDFs, found {len(pdfs)}"
    corpus = generate_table_reports(pdfs, TABLES_DIR)

    print("\n=== TOTALS ===")
    print(f"PDFs: {len(corpus)}")
    print(f"Structural TableNodes: {sum(c['nodes'] for c in corpus)}")
    print(f"TABLE-classified paragraphs: {sum(c['para'] for c in corpus)}")
    print(f"Captioned tables: {sum(c['captioned'] for c in corpus)}")
    print(f"Uncaptioned tables: {sum(c['uncaptioned'] for c in corpus)}")
    landscape = sum(1 for c in corpus for t in c["tables"] if "landscape" in t["orientation"])
    print(f"Landscape-rendered tables: {landscape}")


if __name__ == "__main__":
    main()
