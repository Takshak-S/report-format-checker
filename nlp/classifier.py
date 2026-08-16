import re
import math
from typing import Dict, List, Tuple
from nlp.dom import DocumentModel, Paragraph, BlockType
from utils.fonts import is_code_font, looks_like_code
from utils.config import get_config

EQUATION_FONTS = ["cmmi", "cmsy", "cmex", "math", "stix", "cambria math", "latin modern math"]

# Font-weight detection shared with HeadingValidator
_MEDIUM_FONT_RE = re.compile(r"(medi|medium|demibold|semibold|bold)", re.IGNORECASE)

# Level-0/1/2/3 numbering patterns.  Real headings are "1.1 TITLE" / "1.1.1 Title"
# (NO trailing dot after the last number) — earlier patterns wrongly required
# "1.1. TITLE".  Order matters: longest (deepest) level is tried first.
_NUM_L1_RE = re.compile(r"^\d+\.\d+\s+\S")
_NUM_L2_RE = re.compile(r"^\d+\.\d+\.\d+\s+\S")
_NUM_L3_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+\s+\S")

# TOC: header is "TABLE OF CONTENTS" / "CONTENTS" (may not be bold); entries use
# spaced dot leaders ". . . . ." plus an optional trailing page number.
_TOC_HEADER_RE = re.compile(r"^(table\s+of\s+contents|contents)\s*$", re.IGNORECASE)
_DOT_LEADER_RE = re.compile(r"(?:\.\s+){2,}\.")
_TOC_PAGE_NUM_RE = re.compile(r"\s{2,}\d{1,3}\s*$")

# A numbered line that reads like a sentence (period followed by lowercase) is
# prose, not a heading.
_SENTENCE_LIKE_RE = re.compile(r"\.[ \t]*[a-z]")

# Bullet markers include the en dash and middle dot — LaTeX often renders
# itemize/labeled lists with these, and without them such lists fall through
# to BODY_TEXT and get flagged for alignment/spacing.
_BULLET_RE = re.compile(r"^[\u2022\u2023\u00B7\u2013\*\-]\s+\S")

_LIST_MARKER_RE = re.compile(r"^(\d{1,2}\.\s|[\u2022\u2023\u00B7\u2013\*\-]\s+)")

# Roman-numeral chapter titles ("IV", "V", "X").  Must be a FULL match — a
# prefix match turns innocent words like "in"/"intro" into chapter titles.
_ROMAN_RE = re.compile(r"^[ivxlcdm]{2,}$")

# Width band (pt) around each configured heading size used to confirm a heading.
_HEADING_SIZE_BAND = 2.0

# Consecutive-word gap above which a line is treated as columnar/table content.
# Same divider as margin_validator (measured on the corpus: prose gaps are
# 2-9pt, table rows 54-109pt).
_COLUMNAR_GAP_PT = 30.0

# A glossary/abbreviation line: short all-caps/digit token followed by a wide
# gap and an expansion, e.g. "AI Artificial Intelligence", "1D-CNN One-Dim...".
_GLOSSARY_ABBR_RE = re.compile(r"^[A-Z0-9\u0370-\u03FF][A-Z0-9./+\-\u0370-\u03FF]*\s+\S")


class LayoutAnalyzer:
    def __init__(self, config=None):
        # State tracking across pages (e.g., currently inside references or appendix)
        self.in_references = False
        self.in_appendix = False
        self.in_bibliography = False
        self.in_toc = False
        self.config = config if config is not None else get_config()

    def classify(self, doc: DocumentModel):
        paragraphs = doc.get_all_paragraphs()
        total_pages = len(doc.pages)
        
        for p in paragraphs:
            scores = {bt: 0.0 for bt in BlockType}
            reasons = {bt: [] for bt in BlockType}
            
            def add_score(bt: BlockType, score: float, reason: str):
                scores[bt] += score
                reasons[bt].append(f"{reason} (+{score})")
            
            text = p.text.strip()
            if not text:
                continue
                
            text_lower = text.lower()
            lines = text.split("\n")
            
            # --- Location signals ---
            is_near_end = (p.page_num / total_pages) > 0.8 if total_pages > 0 else False
            is_near_start = p.page_num <= 3
            is_header_area = p.bbox.y0 < 72  # Top 1 inch
            is_footer_area = p.bbox.y1 > (doc.pages[p.page_num - 1].height - 72)
            
            # --- Typographic signals ---
            is_bold = p.dominant_bold
            is_uppercase = text.isupper() and len(text) > 3
            is_large = p.dominant_font_size >= 14.0
            is_small = p.dominant_font_size <= 10.0
            
            # --- Header / Footer / Page Number ---
            if is_header_area and len(lines) <= 2:
                add_score(BlockType.HEADER, 50, "Located in header zone (top 1 inch)")
                
            if is_footer_area and len(lines) <= 2:
                if re.match(r"^\d+$", text) or re.match(r"^[ivx]+$", text_lower):
                    add_score(BlockType.PAGE_NUMBER, 80, "Isolated numeric or roman numeral in footer zone")
                else:
                    add_score(BlockType.FOOTER, 50, "Located in footer zone (bottom 1 inch)")

            # --- Table of Contents (header + entries) --------------------------
            # The header may not be bold; recognize it by text alone and switch
            # into TOC mode.  Entries carry spaced dot leaders (LaTeX) and/or a
            # trailing page number and must never become headings.
            toc_header = False
            if _TOC_HEADER_RE.match(text):
                self.in_toc = True
                toc_header = True
                add_score(BlockType.HEADING_1, 40, "TOC header identified")
            is_toc_entry = bool(_DOT_LEADER_RE.search(text)) or bool(
                self.in_toc and _TOC_PAGE_NUM_RE.search(text))

            # --- Headings ---
            heading_match = None
            if not is_toc_entry and not self.in_references and not self.in_appendix and len(lines) <= 3:
                if (re.match(r"^chapter\s+\d+", text_lower) or _ROMAN_RE.match(text_lower)) and is_large:
                    add_score(BlockType.CHAPTER_TITLE, 80, "Matches chapter title pattern and is large text")
                elif _NUM_L3_RE.match(text) and len(lines) == 1 and not _SENTENCE_LIKE_RE.search(text):
                    add_score(BlockType.HEADING_3, 60, "Matches Level 3 heading pattern")
                    heading_match = BlockType.HEADING_3
                    self._boost_size_match(BlockType.HEADING_3, p.dominant_font_size, add_score)
                elif _NUM_L2_RE.match(text) and len(lines) == 1 and not _SENTENCE_LIKE_RE.search(text):
                    add_score(BlockType.HEADING_2, 60, "Matches Level 2 heading pattern")
                    heading_match = BlockType.HEADING_2
                    self._boost_size_match(BlockType.HEADING_2, p.dominant_font_size, add_score)
                elif _NUM_L1_RE.match(text) and (text.isupper() or is_bold or is_large):
                    add_score(BlockType.HEADING_1, 60, "Matches Level 1 heading pattern")
                    heading_match = BlockType.HEADING_1
                    self._boost_size_match(BlockType.HEADING_1, p.dominant_font_size, add_score)
                elif (text.isupper() and len(text) >= 8 and len(text.split()) <= 6
                      and not (re.search(r"[=+\^_/{}\\]", text)
                               and any(ln.alignment == "right" for ln in p.get_lines()))):
                    add_score(BlockType.HEADING_1, 60, "Short uppercase line (unnumbered heading)")
                    heading_match = BlockType.HEADING_1
                else:
                    if is_large:
                        add_score(BlockType.HEADING_1, 30, "Large text but no numbering")
                        
                if is_bold:
                    add_score(BlockType.HEADING_1, 20, "Bold text in short lines")
                    
                # A strong heading pattern is mutually exclusive with body text.
                if heading_match is not None:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append(
                        f"Penalized: matches heading pattern ({heading_match.value}) (-40)")
                        
            # --- State toggles based on headings ---
            # Detect bibliography / references heading (accept bold/medium/semibold/demibold)
            is_heading_weight = is_bold or bool(_MEDIUM_FONT_RE.search(p.dominant_font or ""))
            if text_lower in {"bibliography", "references", "reference"} and len(text) < 50 and is_heading_weight:
                # Enter bibliography mode
                self.in_bibliography = True
                self.in_references = False
                self.in_appendix = False
                add_score(BlockType.BIBLIOGRAPHY, 80, "Bibliography/References section header identified")
            elif text_lower == "appendix" and len(text) < 50 and is_heading_weight:
                # Enter appendix mode
                self.in_appendix = True
                self.in_bibliography = False
                self.in_references = False
                add_score(BlockType.APPENDIX, 80, "Appendix section header identified")
            # Reset bibliography mode when a new chapter/heading appears
            elif (re.match(r"^chapter\s+\d+", text_lower) or _ROMAN_RE.match(text_lower) or _NUM_L1_RE.match(text)) and self.in_bibliography:
                self.in_bibliography = False
            # Reset appendix mode when a new chapter/heading appears
            elif (re.match(r"^chapter\s+\d+", text_lower) or _ROMAN_RE.match(text_lower) or _NUM_L1_RE.match(text)) and self.in_appendix:
                self.in_appendix = False

            # TOC context ends at the first chapter title after the contents page.
            if self.in_toc and not toc_header and (re.match(r"^chapter\s+\d+", text_lower)
                                                   or _ROMAN_RE.match(text_lower)):
                self.in_toc = False
            
            # --- Special section scoring ---
            if self.in_bibliography:
                add_score(BlockType.BIBLIOGRAPHY, 60, "Inside bibliography section")
            if self.in_references:
                add_score(BlockType.REFERENCE, 40, "Inside reference section context")
                if re.search(r"\(20\d\d\)", text):
                    add_score(BlockType.REFERENCE, 20, "Contains APA year format (20xx)")
                if "doi" in text_lower:
                    add_score(BlockType.REFERENCE, 15, "Contains DOI string")
                if "http" in text_lower:
                    add_score(BlockType.REFERENCE, 10, "Contains URL string")
                if is_near_end:
                    add_score(BlockType.REFERENCE, 10, "Located near end of document")
                    
            if self.in_appendix:
                add_score(BlockType.APPENDIX, 40, "Inside appendix section context")
                    
            # --- Captions ---
            caption_score = 0
            if len(lines) <= 2 and re.match(r"^(fig(ure)?|table)\s*\d+(\.\d+)?\s*:", text_lower):
                add_score(BlockType.CAPTION, 85, "Matches 'Figure/Table N.M:' caption pattern")
                caption_score = 85
            elif len(lines) <= 2 and re.match(r"^(fig(ure)?|table)\s*\d+", text_lower):
                add_score(BlockType.CAPTION, 50, "Matches figure/table caption prefix")
                caption_score = 50
                
            if caption_score:
                if is_small:
                    add_score(BlockType.CAPTION, 20, "Uses smaller caption font size")
                scores[BlockType.BODY_TEXT] -= 40
                reasons[BlockType.BODY_TEXT].append("Penalized: matches caption pattern (-40)")
                    
            # --- Equations ---
            if re.match(r"^\(.*\)$", text.strip()) or re.search(r"\(\d+\.\d+\)$", text.strip()):
                add_score(BlockType.EQUATION, 50, "Matches right-aligned equation numbering pattern")
            
            font_lower = p.dominant_font.lower()
            if any(ef in font_lower for ef in EQUATION_FONTS):
                add_score(BlockType.EQUATION, 80, f"Uses known equation/math font ({p.dominant_font})")
            
            # Displayed math: right-aligned lines carrying math symbols and/or an
            # equation number, e.g. "TP" / "Precision = (5.3)" / "TP+FP".
            math_lines = [ln for ln in lines if re.search(r"[=+\-^_/{}\\]", ln)]
            right_aligned_math = 0
            for ln in p.get_lines():
                if ln.alignment == "right" and re.search(r"[=+\-^_/{}\\]", ln.text):
                    right_aligned_math += 1
            if right_aligned_math >= 2 and len(lines) <= 6:
                add_score(BlockType.EQUATION, 75, f"Right-aligned math lines ({right_aligned_math} lines)")
                scores[BlockType.BODY_TEXT] -= 60
                reasons[BlockType.BODY_TEXT].append("Penalized: right-aligned equation lines (-60)")
            elif right_aligned_math >= 1 and len(lines) == 1 and re.search(r"[=+\^_/{}\\]", text):
                add_score(BlockType.EQUATION, 60, "Single right-aligned math line")
                scores[BlockType.BODY_TEXT] -= 50
                reasons[BlockType.BODY_TEXT].append("Penalized: single right-aligned equation line (-50)")
            elif len(math_lines) >= 2 and len(lines) <= 6:
                para_right = sum(1 for ln in p.get_lines() if ln.alignment == "right")
                if para_right >= len(lines) * 0.5:
                    add_score(BlockType.EQUATION, 60, "Multiple math-symbol lines with right alignment")
                
            # --- Table of Contents ---
            if is_toc_entry:
                add_score(BlockType.TOC, 75, "Dot-leader / page-numbered TOC entry")
                scores[BlockType.BODY_TEXT] -= 30
                reasons[BlockType.BODY_TEXT].append("Penalized: TOC entry (-30)")
            elif self.in_toc and re.search(r"\d{1,3}\s*$", text):
                add_score(BlockType.TOC, 60, "Inside TOC context with page number")

            # --- Lists ---
            list_lines = [
                ln for ln in lines
                if _LIST_MARKER_RE.match(ln.strip())
            ]
            if len(list_lines) >= 2 and list_lines[0] is lines[0]:
                add_score(BlockType.LIST, 60, "Multiple numbered/bulleted lines (list)")
                scores[BlockType.BODY_TEXT] -= 20
                reasons[BlockType.BODY_TEXT].append("Penalized: list-like lines (-20)")
            elif _BULLET_RE.match(text) and len(lines) == 1:
                # LaTeX itemize renders each bullet as its own single-line block.
                add_score(BlockType.LIST, 70, "Single-line bullet list item")
                scores[BlockType.BODY_TEXT] -= 30
                reasons[BlockType.BODY_TEXT].append("Penalized: bullet list item (-30)")
            elif _LIST_MARKER_RE.match(text.strip()):
                add_score(BlockType.LIST, 65, "Starts with bullet point or numbered list prefix")
                scores[BlockType.BODY_TEXT] -= 20
                reasons[BlockType.BODY_TEXT].append("Penalized: list-item prefix (-20)")
                
            # --- Code Blocks & Algorithms ---
            if is_code_font(p.dominant_font):
                add_score(BlockType.CODE_BLOCK, 90, f"Uses monospaced/typewriter font ({p.dominant_font})")
            elif looks_like_code(text):
                add_score(BlockType.CODE_BLOCK, 85, "Matches code/listing content pattern (line numbers, YAML, CI/CD keywords)")
            
            if re.match(r"^(algorithm\s+\d+|[0-9]+:\s*)", text_lower):
                add_score(BlockType.CODE_BLOCK, 80, "Matches algorithm environment pattern")
            else:
                # Strict algorithm/pseudocode heuristic: at least two lines must
                # start with a programming keyword AND carry code punctuation,
                # so prose lines beginning with "else/if/for" are never caught.
                algo_lines = [
                    ln for ln in lines
                    if re.match(r"^\s*(while|for|if|else|return|input:|output:)\b",
                                ln.strip(), re.IGNORECASE)
                    and re.search(r"[()=;{}]", ln)
                ]
                if len(algo_lines) >= 2:
                    add_score(BlockType.CODE_BLOCK, 80, "Matches algorithm/pseudocode pattern")
                    
            # --- Glossary / Abbreviation lists ---------------------------------
            # e.g. "AI Artificial Intelligence", "1D-CNN One-Dimensional CNN":
            # short all-caps token, wide word gap, then the expansion. Such
            # lines are definition entries, not justified prose.
            glossary_lines = 0
            for ln in p.get_lines():
                words = [w for w in ln.get_words() if w.text.strip()]
                if len(words) >= 2 and _GLOSSARY_ABBR_RE.match(ln.text.strip()):
                    gap = words[1].bbox.x0 - words[0].bbox.x1
                    if gap > 10.0 and len(words[0].text) <= 14:
                        glossary_lines += 1
            if glossary_lines >= 2 and glossary_lines >= len(lines) * 0.5:
                add_score(BlockType.LIST, 75, f"Glossary/abbreviation entries ({glossary_lines} lines)")
                scores[BlockType.BODY_TEXT] -= 50
                reasons[BlockType.BODY_TEXT].append("Penalized: glossary/abbreviation list (-50)")
            elif glossary_lines == 1:
                add_score(BlockType.LIST, 45, "Single glossary/abbreviation entry")
                
            # --- Columnar / table content ---------------------------------------
            # Rows whose words are laid out in wide columns (e.g. comparison
            # tables rendered as text) are structural, not justified prose.
            columnar_lines = 0
            for ln in p.get_lines():
                words = sorted(ln.get_words(), key=lambda w: w.bbox.x0)
                if len(words) < 3:
                    continue
                gaps = [words[i + 1].bbox.x0 - words[i].bbox.x1 for i in range(len(words) - 1)]
                if max(gaps) > _COLUMNAR_GAP_PT:
                    columnar_lines += 1
            if columnar_lines >= 2 and columnar_lines >= len(lines) * 0.5:
                add_score(BlockType.TABLE, 80, f"Columnar/table row layout ({columnar_lines} lines)")
                scores[BlockType.BODY_TEXT] -= 60
                reasons[BlockType.BODY_TEXT].append("Penalized: columnar table content (-60)")
            
            # --- Body Text (Fallback) ---
            if not is_bold and not is_header_area and not is_footer_area and not is_large:
                if len(lines) > 2:
                    add_score(BlockType.BODY_TEXT, 20, "Contains >2 lines of text")
                else:
                    add_score(BlockType.BODY_TEXT, 5, "Contains 1-2 lines of text")
                add_score(BlockType.BODY_TEXT, 20, "Regular weight font (not bold)")
                add_score(BlockType.BODY_TEXT, 10, "Located within main body margins")
                
                # Definitive text heuristic for short paragraphs
                if len(lines) <= 2 and not is_small:
                    math_chars = sum(1 for c in text if c in '=+_^{}\\')
                    alpha_chars = sum(1 for c in text if c.isalpha())
                    if alpha_chars > 20 and math_chars == 0:
                        add_score(BlockType.BODY_TEXT, 15, "Definitive text characteristics (high alpha, no math, standard size)")
                # Penalize tiny or garbled fragments (footnotes, mojibake, stray glyphs)
                total_chars = len(text.replace(" ", ""))
                alpha_chars = sum(1 for c in text if c.isalpha())
                alpha_ratio = (alpha_chars / total_chars) if total_chars else 0.0
                if (p.dominant_font_size and p.dominant_font_size < 9.0) or alpha_ratio < 0.4:
                    scores[BlockType.BODY_TEXT] -= 50
                    reasons[BlockType.BODY_TEXT].append(
                        f"Penalized: tiny/garbled fragment (size={p.dominant_font_size}, alpha_ratio={alpha_ratio:.2f}) (-50)")
                # Penalize paragraphs that overlap a detected table region (table cell text)
                if 0 < p.page_num <= len(doc.pages):
                    page_node = doc.pages[p.page_num - 1]
                    for tbl in page_node.get_tables():
                        if p.bbox.intersects(tbl.bbox):
                            scores[BlockType.BODY_TEXT] -= 50
                            reasons[BlockType.BODY_TEXT].append("Penalized: overlaps table region (-50)")
                            break
                if self.in_references:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append("Penalized: Inside references section (-40)")
                if self.in_appendix:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append("Penalized: Inside appendix section (-40)")
                if self.in_bibliography:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append("Penalized: Inside bibliography section (-40)")
                
            # --- Determine Winner & Softmax Confidence ---
            # Remove unknown from consideration unless everything is 0
            scores.pop(BlockType.UNKNOWN, None)
            
            max_score = max(scores.values()) if scores else 0
            
            if max_score < 10:
                p.block_type = BlockType.UNKNOWN
                p.classification_confidence = 0.0
                p.classification_reasons = ["No strong signals detected."]
                continue
                
            # Softmax to calculate true probabilities against a base doubt threshold (25)
            exp_scores = {bt: math.exp(s / 20.0) for bt, s in scores.items() if s > 0}
            exp_scores[BlockType.UNKNOWN] = math.exp(25.0 / 20.0)
            
            sum_exp = sum(exp_scores.values())
            probs = {bt: (exp_scores[bt] / sum_exp) for bt in exp_scores}
            
            best_type = max(probs, key=probs.get) if probs else BlockType.UNKNOWN
            best_prob = probs[best_type] if probs else 0.0
            
            p.block_type = best_type
            
            # The user requires UNCERTAIN if confidence < 0.75
            if best_prob < 0.75:
                p.block_type = BlockType.UNKNOWN
                p.classification_reasons.append(f"Dropped to UNCERTAIN due to low confidence ({best_prob:.2f} < 0.75)")
                
            p.classification_confidence = best_prob
            p.classification_reasons.extend(reasons[best_type])
            
            # Record top alternative candidates (> 5% probability)
            p.alternative_candidates = {
                bt: prob for bt, prob in probs.items() 
                if bt != best_type and prob > 0.05
            }

    def _boost_size_match(self, block_type: BlockType, size: float, add_score) -> None:
        """Confirm a heading when its size falls in the configured band for its level."""
        if not size:
            return
        level_map = {
            BlockType.HEADING_1: self.config.headings.level_1,
            BlockType.HEADING_2: self.config.headings.level_2,
            BlockType.HEADING_3: self.config.headings.level_3,
        }
        level_cfg = level_map.get(block_type)
        if level_cfg is None:
            return
        if abs(size - level_cfg.size) <= _HEADING_SIZE_BAND:
            add_score(block_type, 12, f"Size matches config band for level ({size}pt vs {level_cfg.size}pt)")
