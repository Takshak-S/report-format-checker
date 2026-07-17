from __future__ import annotations
import re
from typing import List, Tuple
from .dom import DocumentModel, Page, Paragraph, Line, Word, ImageNode, TableNode, BBox, BlockType

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
            lines = self._build_lines(p_chars, page_num)
            paragraphs = self._build_paragraphs(lines, page_num)
            
            for p in paragraphs:
                page_node.add_child(p)
                
            for img in p_imgs:
                img_node = ImageNode(
                    id=self._next_id("img"),
                    page_num=page_num,
                    bbox=BBox(img['x0'], img['y0'], img['x1'], img['y1']),
                    dpi_x=img['xres'],
                    dpi_y=img['yres'],
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

    def _build_lines(self, chars, page_num: int) -> List[Line]:
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
                lines.append(self._make_line(current_group, page_num))
                current_group = [ch]
        
        if current_group:
            lines.append(self._make_line(current_group, page_num))
            
        return lines
        
    def _make_line(self, chars, page_num: int) -> Line:
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
            
        line_node = Line(
            id=self._next_id("line"),
            page_num=page_num,
            bbox=line_bbox,
            text=" ".join(w.text for w in words),
            font=max(font_counts.items(), key=lambda x: x[1])[0] if font_counts else "",
            font_size=max(size_counts.items(), key=lambda x: x[1])[0] if size_counts else 0.0,
            bold=any(w.bold for w in words),
            italic=any(w.italic for w in words)
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
        
        paragraphs = []
        current_para_lines = [lines[0]]
        
        for i in range(1, len(lines)):
            prev_line = current_para_lines[-1]
            curr_line = lines[i]
            
            vertical_gap = curr_line.bbox.y0 - prev_line.bbox.y1
            horizontal_gap = curr_line.bbox.x0 - prev_line.bbox.x0
            
            is_new_para = False
            
            # Multi-column: if the next line is horizontally far away but vertically similar
            if abs(curr_line.bbox.y0 - prev_line.bbox.y0) < prev_line.font_size and abs(horizontal_gap) > 100:
                is_new_para = True
            # Standard vertical gap
            elif vertical_gap > (prev_line.font_size * 0.8):
                is_new_para = True
            # Font change
            elif curr_line.font != prev_line.font or abs(curr_line.font_size - prev_line.font_size) > 1.0:
                is_new_para = True
            # Indent detection (new paragraph starting)
            elif horizontal_gap > (prev_line.font_size * 1.5) and vertical_gap > 0:
                is_new_para = True
                
            if is_new_para:
                paragraphs.append(self._make_paragraph(current_para_lines, page_num))
                current_para_lines = [curr_line]
            else:
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
            
        return p
