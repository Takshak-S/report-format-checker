import re
import math
from typing import Dict, List, Tuple
from nlp.dom import DocumentModel, Paragraph, BlockType

EQUATION_FONTS = ["cmmi", "cmsy", "cmex", "math", "stix", "cambria math", "latin modern math"]

class LayoutAnalyzer:
    def __init__(self):
        # State tracking across pages (e.g., currently inside references or appendix)
        self.in_references = False
        self.in_appendix = False
        self.in_toc = False

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
                    
            # --- Headings ---
            if len(lines) <= 3:
                if re.match(r"^(chapter\s+\d+|[ivx]+)", text_lower) and is_large:
                    add_score(BlockType.CHAPTER_TITLE, 80, "Matches chapter title pattern and is large text")
                elif re.match(r"^\d+\.\s+[a-z]", text_lower):
                    add_score(BlockType.HEADING_1, 60, "Matches Level 1 heading pattern")
                elif re.match(r"^\d+\.\d+\.\s+[a-z]", text_lower):
                    add_score(BlockType.HEADING_2, 60, "Matches Level 2 heading pattern")
                elif re.match(r"^\d+\.\d+\.\d+\.\s+[a-z]", text_lower):
                    add_score(BlockType.HEADING_3, 60, "Matches Level 3 heading pattern")
                else:
                    if is_large:
                        add_score(BlockType.HEADING_1, 30, "Large text but no numbering")
                        
                if is_bold:
                    add_score(BlockType.HEADING_1, 20, "Bold text in short lines")
                        
            # --- State toggles based on headings ---
            if "reference" in text_lower or "bibliography" in text_lower:
                if len(text) < 50 and is_bold:
                    self.in_references = True
                    add_score(BlockType.HEADING_1, 40, "Reference section header identified")
            
            if "appendix" in text_lower:
                if len(text) < 50 and is_bold:
                    self.in_appendix = True
                    add_score(BlockType.HEADING_1, 40, "Appendix section header identified")
                    
            if "table of contents" in text_lower:
                if len(text) < 50 and is_bold:
                    self.in_toc = True
                    add_score(BlockType.HEADING_1, 40, "TOC header identified")
            
            # --- References & Appendix ---
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
            if re.match(r"^fig(ure)?\.?\s*\d+", text_lower):
                add_score(BlockType.CAPTION, 60, "Matches figure caption prefix")
                if is_small:
                    add_score(BlockType.CAPTION, 20, "Uses smaller caption font size")
            
            if re.match(r"^table\s*\d+", text_lower):
                add_score(BlockType.CAPTION, 60, "Matches table caption prefix")
                if is_small:
                    add_score(BlockType.CAPTION, 20, "Uses smaller caption font size")
                    
            # --- Equations ---
            if re.match(r"^\(.*\)$", text.strip()) or re.search(r"\(\d+\.\d+\)$", text.strip()):
                add_score(BlockType.EQUATION, 50, "Matches right-aligned equation numbering pattern")
            
            font_lower = p.dominant_font.lower()
            if any(ef in font_lower for ef in EQUATION_FONTS):
                add_score(BlockType.EQUATION, 80, f"Uses known equation/math font ({p.dominant_font})")
                
            # --- Lists ---
            if re.match(r"^[\u2022\-\*]\s+", text) or re.match(r"^\d+\.\s+", text):
                add_score(BlockType.LIST, 40, "Starts with bullet point or numbered list prefix")
                
            # --- Code Blocks & Algorithms ---
            if "cmtt" in font_lower or "cmt" in font_lower or "courier" in font_lower or "mono" in font_lower:
                add_score(BlockType.CODE_BLOCK, 80, f"Uses monospaced/typewriter font ({p.dominant_font})")
            
            if re.match(r"^(algorithm\s+\d+|[0-9]+:\s*)", text_lower) or any(re.match(r"^\s*(while|for|if|else|return|input:|output:)\b", line.strip(), re.IGNORECASE) for line in lines):
                add_score(BlockType.CODE_BLOCK, 80, "Matches algorithm environment pattern")
            
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
                if self.in_references:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append("Penalized: Inside references section (-40)")
                if self.in_appendix:
                    scores[BlockType.BODY_TEXT] -= 40
                    reasons[BlockType.BODY_TEXT].append("Penalized: Inside appendix section (-40)")
                
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
