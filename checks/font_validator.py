from typing import List
from nlp.dom import DocumentModel, BlockType
from utils.error_model import Violation
from utils.constants import Category, Severity
from checks.validators import ValidationRule

import re

def normalize_font(font_name: str) -> str:
    if not font_name:
        return ""
    # Remove PDF subset prefix (e.g. ABCDEF+)
    font_name = re.sub(r"^[A-Z]{6}\+", "", font_name)
    # Lowercase
    font_name = font_name.lower()
    # Remove separators
    font_name = re.sub(r"[-_\s]", "", font_name)
    return font_name

class FontValidator(ValidationRule):
    def validate(self, doc: DocumentModel) -> List[Violation]:
        violations = []
        
        # User defined aliases mapping
        ALLOWED_BODY_ALIASES = [
            "times",
            "timesnewroman",
            "nimbusrom",
            "nimbusroman",
            "texgyretermes",
            "liberationserif",
            "urwnimbusroman"
        ]
        
        for p in doc.get_all_paragraphs():
            # Skip non-body and structural blocks for font validation
            if p.block_type in (
                BlockType.CODE_BLOCK, BlockType.EQUATION, BlockType.HEADER, BlockType.FOOTER,
                BlockType.PAGE_NUMBER, BlockType.REFERENCE, BlockType.TABLE, BlockType.FIGURE,
                BlockType.UNKNOWN, BlockType.LIST, BlockType.CAPTION, BlockType.APPENDIX
            ):
                continue
                
            text_lower = p.text.lower().strip()
            if re.match(r"^(algorithm\s+\d+|[0-9]+:\s)", text_lower):
                continue
            if re.search(r"\(\d+\.\d+\)$", text_lower):
                continue
                
            if p.dominant_font:
                nf = normalize_font(p.dominant_font)
                if nf.startswith("cm") or nf.startswith("lm") or "math" in nf or "symbol" in nf or "sym" in nf or nf in ["rsfs10", "msbm10", "msam10", "standardsyml"]:
                    continue
                    
            expected_size = None
            if p.block_type == BlockType.BODY_TEXT:
                expected_size = self.config.typography.body_size
            elif p.block_type == BlockType.CAPTION:
                expected_size = self.config.typography.caption_size
                
            if expected_size and p.dominant_font_size:
                normalized_size = round(p.dominant_font_size)
                if normalized_size != round(expected_size):
                    violations.append(Violation(
                        category=Category.FONT,
                        severity=Severity.CRITICAL,
                        page=p.page_num,
                        description=f"Invalid font size for {p.block_type.value}.",
                        expected=f"{expected_size}pt",
                        detected=f"{round(p.dominant_font_size, 2)}pt",
                        confidence=p.classification_confidence,
                        signals=p.classification_reasons,
                        reason=f"Paragraph predominant font size diverges from the configured standard.",
                        suggested_fix="Adjust the font size to the exact required specification.",
                        location=p.text[:30] + "...",
                        bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                    ))
                
            if p.dominant_font:
                norm_font = normalize_font(p.dominant_font)
                
                # Check against the allowed aliases
                allowed = any(alias in norm_font for alias in ALLOWED_BODY_ALIASES)
                
                if not allowed:
                    violations.append(Violation(
                        category=Category.FONT,
                        severity=Severity.CRITICAL,
                        page=p.page_num,
                        description=f"Invalid font detected in {p.block_type.value}.",
                        expected=f"one of {ALLOWED_BODY_ALIASES}",
                        detected=f"'{p.dominant_font}'",
                        confidence=p.classification_confidence,
                        signals=p.classification_reasons,
                        reason="The detected font family is not strictly in the allowed template list.",
                        suggested_fix="Change the font family for this section.",
                        location=p.text[:30] + "...",
                        bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                    ))
                    
        return violations
