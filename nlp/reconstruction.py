from __future__ import annotations
import re
from typing import List, Tuple
from .dom import DocumentModel, Page, Paragraph, Line, Word, ImageNode, TableNode, BBox, BlockType
from utils.fonts import is_code_font

# A line that opens a numbered or bulleted list item ("1. ...", "– ...",
# "· ...").  Such a line always begins a new paragraph so a prose intro is
# never merged with the first list item (which would smear alignment/spacing).
_LIST_MARKER_RE = re.compile(r"^(\d{1,2}\.\s|[\u2022\u2023\u00B7\u2013\*\-]\s+)")

def normalize_font(raw: str) -> tuple[str, bool, bool]:
    name = re.sub(r"^[A-Z]{6}\+", "", raw)
    lower = name.lower()
    bold = any(kw in lower for kw in ("bold", "-bd", ",bold"))
    italic = any(kw in lower for kw in ("italic", "oblique", "-it", ",italic"))
    clean = re.sub(r"[-,]?(bold|italic|oblique|bd|it)", "", lower).strip("-,")
    return clean, bold, italic

def most_frequent(lst):
    if not lst:
        return None
    return max(set(lst), key=lst.count)

class DocumentReconstructor:
    def __init__(self):
        self.doc = DocumentModel()
        self._current_id = 0
        
    def _next_id(self, prefix: str) -> str:
        self._current_id += 1
        return f"{prefix}_{self._current_id}"
        
    def build_from_raw(self, page_sizes, raw_chars, raw_images, raw_tables, has_text_layer) -> DocumentModel:
        self.doc.pages = []
        
        # Group by page
        page_count = len(page_sizes)
        for page_num in range(1, page_count + 1):
            width, height = page_sizes[page_num - 1]
            page_node = Page(
                id=self._next_id("page"),
                page_num=page_num,
                bbox=BBox(0, 0, width, height),
                width=width,
                height=height
            )
            
            p_chars = [c for c in raw_chars if c['page'] == page_num]
            p_imgs = [i for i in raw_images if i['page'] == page_num]
            p_tbls = [t for t in raw_tables if t['page'] == page_num]
            
            # Reconstruct Text
            lines = self._build_lines(p_chars, page_num, width, height)
            paragraphs = self._build_paragraphs(lines, page_num)
            
            for p in paragraphs:
                page_node.add_child(p)
                
            for img in p_imgs:
                rendered_w = max(img['x1'] - img['x0'], 0.01)
                rendered_h = max(img['y1'] - img['y0'], 0.01)
                computed_dpi = min(img['width_px'] / rendered_w * 72.0,
                                   img['height_px'] / rendered_h * 72.0)
                # PyMuPDF reports xres/yres as 96 even for high-resolution
                # embedded images; fall back to the geometry-computed DPI.
                dpi_x = img['xres'] if img['xres'] > 96 else computed_dpi
                dpi_y = img['yres'] if img['yres'] > 96 else computed_dpi
                img_node = ImageNode(
                    id=self._next_id("img"),
                    page_num=page_num,
                    bbox=BBox(img['x0'], img['y0'], img['x1'], img['y1']),
                    xref=img.get('xref', 0),
                    dpi_x=round(dpi_x, 1),
                    dpi_y=round(dpi_y, 1),
                    width_px=img['width_px'],
                    height_px=img['height_px'],
                    colorspace=img['colorspace']
                )
                page_node.add_child(img_node)
                
            for tbl in p_tbls:
                tbl_node = TableNode(
                    id=self._next_id("tbl"),
                    page_num=page_num,
                    bbox=BBox(tbl['x0'], tbl['y0'], tbl['x1'], tbl['y1']),
                    rows=tbl['rows']
                )
                page_node.add_child(tbl_node)
                
            self.doc.pages.append(page_node)
            
        return self.doc

    def _build_lines(self, chars, page_num: int, page_width: float, page_height: float) -> List[Line]:
        if not chars:
            return []
            
        # Sort by Y top, then X0
        chars.sort(key=lambda c: (round(c['top'], 1), c['x0']))
        
        lines = []
        current_group = [chars[0]]
        
        for ch in chars[1:]:
            if abs(ch['top'] - current_group[0]['top']) < 4.0:
                current_group.append(ch)
            else:
                lines.append(self._make_line(current_group, page_num, page_width, page_height))
                current_group = [ch]
        
        if current_group:
            lines.append(self._make_line(current_group, page_num, page_width, page_height))
            
        return lines
        
    def _make_line(self, chars, page_num: int, page_width: float, page_height: float) -> Line:
        chars.sort(key=lambda c: c['x0'])
        
        words = []
        current_word_chars = [chars[0]]
        
        avg_char_width = sum(c['x1'] - c['x0'] for c in chars) / len(chars) if chars else 5.0
        space_threshold = max(avg_char_width * 0.25, 1.5)
        
        for ch in chars[1:]:
            gap = ch['x0'] - current_word_chars[-1]['x1']
            if gap > space_threshold:
                words.append(self._make_word(current_word_chars, page_num))
                current_word_chars = [ch]
            else:
                current_word_chars.append(ch)
                
        if current_word_chars:
            words.append(self._make_word(current_word_chars, page_num))
            
        line_bbox = BBox(
            x0=min(w.bbox.x0 for w in words),
            y0=min(w.bbox.y0 for w in words),
            x1=max(w.bbox.x1 for w in words),
            y1=max(w.bbox.y1 for w in words)
        )
        
        font_counts = {}
        size_counts = {}
        for w in words:
            length = len(w.text.strip())
            if length == 0: length = 1
            font_counts[w.font] = font_counts.get(w.font, 0) + length
            size_counts[w.font_size] = size_counts.get(w.font_size, 0) + length

        line_font_size = max(size_counts.items(), key=lambda x: x[1])[0] if size_counts else 0.0

        # Compute alignment relative to page margins (left 1.5in=108pt, right 1in=72pt)
        left_margin = 108.0
        right_margin = page_width - 72.0
        line_center = (line_bbox.x0 + line_bbox.x1) / 2.0
        text_area_center = (left_margin + right_margin) / 2.0
        tolerance = 5.0  # points
        # A paragraph's first line is typically indented by ~2-3× the font size;
        # such a line still reaches the right margin, so treat it as justified
        # rather than right-aligned.
        indent_tolerance = max(line_font_size * 3.0, 24.0)

        at_left = abs(line_bbox.x0 - left_margin) <= tolerance
        at_right = abs(line_bbox.x1 - right_margin) <= tolerance

        if at_left and at_right:
            alignment = "justified"
        elif at_right and (left_margin <= line_bbox.x0 <= left_margin + indent_tolerance):
            alignment = "justified"
        elif at_left:
            alignment = "left"
        elif at_right:
            alignment = "right"
        elif abs(line_center - text_area_center) <= tolerance:
            alignment = "center"
        else:
            # fallback: decide by which side is closer
            if abs(line_bbox.x0 - left_margin) < abs(line_bbox.x1 - right_margin):
                alignment = "left"
            else:
                alignment = "right"
            
        line_node = Line(
            id=self._next_id("line"),
            page_num=page_num,
            bbox=line_bbox,
            text=" ".join(w.text for w in words),
            font=max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else "",
            font_size=max(size_counts.items(), key=lambda x: x[1])[0] if size_counts else 0.0,
            bold=any(w.bold for w in words),
            italic=any(w.italic for w in words),
            alignment=alignment,
            line_spacing=0.0  # will be set in paragraph building
        )
        
        for w in words:
            line_node.add_child(w)
            
        return line_node

    def _make_word(self, chars, page_num: int) -> Word:
        text = "".join(c['text'] for c in chars)
        fonts = [c['fontname'] for c in chars]
        sizes = [c['size'] for c in chars]
        
        clean_font, bold, italic = normalize_font(most_frequent(fonts) or "")
        
        return Word(
            id=self._next_id("word"),
            page_num=page_num,
            bbox=BBox(
                x0=min(c['x0'] for c in chars),
                y0=min(c['y0'] for c in chars),
                x1=max(c['x1'] for c in chars),
                y1=max(c['y1'] for c in chars)
            ),
            text=text,
            font=clean_font,
            font_size=round(most_frequent(sizes) or 0.0, 2),
            bold=bold,
            italic=italic
        )

    def _build_paragraphs(self, lines: List[Line], page_num: int) -> List[Paragraph]:
        if not lines:
            return []
            
        # Sort lines by top-to-bottom, then left-to-right (for multi-column support)
        lines.sort(key=lambda l: (round(l.bbox.y0 / 10.0), l.bbox.x0))
        
        # Estimate the typical intra-paragraph vertical gap from the document's
        # own line grid so paragraph breaks (which are ~2× the intra-paragraph
        # gap) can be separated reliably regardless of the line-spacing factor.
        gap_samples = []
        for i in range(1, len(lines)):
            prev_l = lines[i - 1]
            curr_l = lines[i]
            if prev_l.font_size > 0 and abs(curr_l.font_size - prev_l.font_size) <= 1.0:
                v_gap = curr_l.bbox.y0 - prev_l.bbox.y1
                h_gap = curr_l.bbox.x0 - prev_l.bbox.x0
                if abs(h_gap) < 100.0:  # same column
                    gap_samples.append(v_gap)
        typical_gap = None
        if gap_samples:
            gap_samples.sort()
            typical_gap = gap_samples[len(gap_samples) // 2]  # median
            # Quantile guard: choose the gap separating intra-paragraph from
            # paragraph-break gaps if a clear break point exists.
            lower_q = gap_samples[int(len(gap_samples) * 0.35)]
            if typical_gap * 1.4 < gap_samples[-1] and gap_samples[int(len(gap_samples) * 0.85)] > typical_gap * 1.6:
                break_gap = gap_samples[int(len(gap_samples) * 0.85)]
                split_threshold = (typical_gap + break_gap) / 2.0
            else:
                split_threshold = typical_gap * 1.5
            if split_threshold <= 0:
                split_threshold = typical_gap * 1.5
        else:
            split_threshold = None
        
        paragraphs = []
        current_para_lines = [lines[0]]
        
        for i in range(1, len(lines)):
            prev_line = current_para_lines[-1]
            curr_line = lines[i]
            
            vertical_gap = curr_line.bbox.y0 - prev_line.bbox.y1
            horizontal_gap = curr_line.bbox.x0 - prev_line.bbox.x0
            line_height = prev_line.bbox.y1 - prev_line.bbox.y0
            base_font = prev_line.font_size if prev_line.font_size > 0 else 12.0
            
            # Line spacing is only meaningful for lines within the same
            # paragraph; a paragraph break (large vertical gap) must not be
            # attributed to the last line of the paragraph.
            is_new_para = False
            
            # Multi-column: if the next line is horizontally far away but vertically similar
            if abs(curr_line.bbox.y0 - prev_line.bbox.y0) < prev_line.font_size and abs(horizontal_gap) > 100:
                is_new_para = True
            # Standard vertical gap: paragraph breaks are ~2× the intra-para gap
            elif split_threshold is not None and vertical_gap > split_threshold:
                is_new_para = True
            elif vertical_gap > (base_font * 1.3):
                is_new_para = True
            # Font change
            elif curr_line.font != prev_line.font or abs(curr_line.font_size - prev_line.font_size) > 1.0:
                is_new_para = True
            # Indent detection (new paragraph starting)
            elif horizontal_gap > (prev_line.font_size * 1.5) and vertical_gap > 0:
                is_new_para = True
            # List-item boundary: a line opening a bullet/numbered item starts a
            # new paragraph (unless it is monospaced code/docstring content).
            elif _LIST_MARKER_RE.match(curr_line.text.strip()) and not is_code_font(curr_line.font):
                is_new_para = True
                
            if is_new_para:
                paragraphs.append(self._make_paragraph(current_para_lines, page_num))
                current_para_lines = [curr_line]
            else:
                # Same-paragraph line: compute line spacing normalized by the
                # natural line box (1.2× font size), so a correctly 1.5-spaced
                # LaTeX line measures ~1.5 instead of ~1.8.
                if prev_line.font_size > 0:
                    prev_line.line_spacing = (line_height + max(vertical_gap, 0)) / (base_font * 1.2)
                # Hyphenation handling
                if prev_line.text.endswith("-"):
                    prev_line.text = prev_line.text[:-1]
                    # Don't add a space between hyphenated lines in paragraph reconstruction text (handled in _make_paragraph)
                current_para_lines.append(curr_line)
                
        if current_para_lines:
            paragraphs.append(self._make_paragraph(current_para_lines, page_num))
            
        return paragraphs
        
    def _make_paragraph(self, lines: List[Line], page_num: int) -> Paragraph:
        para_bbox = BBox(
            x0=min(l.bbox.x0 for l in lines),
            y0=min(l.bbox.y0 for l in lines),
            x1=max(l.bbox.x1 for l in lines),
            y1=max(l.bbox.y1 for l in lines)
        )
        
        font_counts = {}
        size_counts = {}
        for l in lines:
            for w in l.get_words():
                length = len(w.text.strip())
                if length == 0: length = 1
                font_counts[w.font] = font_counts.get(w.font, 0) + length
                size_counts[w.font_size] = size_counts.get(w.font_size, 0) + length
        
        p = Paragraph(
            id=self._next_id("para"),
            page_num=page_num,
            bbox=para_bbox,
            text="\n".join(l.text for l in lines),
            dominant_font=max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else "",
            dominant_font_size=max(size_counts.items(), key=lambda x: x[1])[0] if size_counts else 0.0,
            dominant_bold=any(l.bold for l in lines),
            dominant_italic=any(l.italic for l in lines)
        )
        
        for l in lines:
            p.add_child(l)

        # Paragraph-relative alignment: an indented/boxed block (block quote,
        # callout) is justified *within* its box even though it is inset from
        # the page margins.  If the interior lines (excluding the naturally
        # ragged last line) are flush to both the paragraph's own left and right
        # extremes, they are justified.  Genuinely ragged (left-aligned) or
        # right-pushed (equation) blocks keep large right-gaps / left-indents
        # and are unaffected.
        if len(lines) >= 2:
            interior = lines[:-1]
            tol = 5.0
            left_indents = sorted(l.bbox.x0 - para_bbox.x0 for l in interior)
            right_gaps = sorted(para_bbox.x1 - l.bbox.x1 for l in interior)
            med_left = left_indents[len(left_indents) // 2]
            med_right = right_gaps[len(right_gaps) // 2]
            if med_left <= tol and med_right <= tol:
                for l in interior:
                    l.alignment = "justified"

        return p
