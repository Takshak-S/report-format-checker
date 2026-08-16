import re
import statistics
from typing import List, Tuple
from nlp.dom import DocumentModel, BlockType, Paragraph
from utils.error_model import Violation
from utils.constants import Category, Severity
from utils.profile import build_profile
from checks.validators import ValidationRule

URL_PATTERN = re.compile(r"(http[s]?://|www\.)[^\s]+")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Consecutive-word gap above which a line is treated as columnar/table content.
# Measured on the corpus: genuine prose overflows show gaps of 2-9pt while
# table rows (dataset comparisons) show 54-109pt, so 30pt is a safe divider.
_COLUMNAR_GAP_PT = 30.0


def _is_columnar_line(words) -> bool:
    """True if the line's words are laid out in wide columns (table row)."""
    ordered = sorted(words, key=lambda w: w.bbox.x0)
    if len(ordered) < 3:
        return False
    gaps = [ordered[i + 1].bbox.x0 - ordered[i].bbox.x1
            for i in range(len(ordered) - 1)]
    return max(gaps) > _COLUMNAR_GAP_PT

class MarginValidator(ValidationRule):
    def validate(self, doc: DocumentModel) -> List[Violation]:
        violations = []

        profile = self.profile if self.profile is not None else build_profile(doc, self.config)
        expected_left_pt = self.config.margins.left_inches * 72.0
        expected_right_pt = self.config.margins.right_inches * 72.0
        tolerance = profile.margin_tolerance

        # We only check margins for body text, headings, and list blocks.
        # List items are validated with the same per-line edge analysis: bullet /
        # hanging indentation is exempt via the is_indented rule, while genuinely
        # overfull lines (e.g. a long unbreakable token pushed past the right
        # margin) are flagged per-line.
        checkable_types = {
            BlockType.BODY_TEXT,
            BlockType.LIST,
            BlockType.HEADING_1,
            BlockType.HEADING_2,
            BlockType.HEADING_3,
            BlockType.CHAPTER_TITLE,
            BlockType.REFERENCE,
            BlockType.APPENDIX
        }
        
        for p in doc.get_all_paragraphs():
            if p.block_type not in checkable_types:
                continue
                
            page = doc.pages[p.page_num - 1]
            max_x1 = page.width - expected_right_pt
            
            lines = p.get_lines()
            if not lines:
                continue
                
            # Paragraph-Level Median Analysis
            left_edges = []
            right_edges = []
            valid_lines = []
            
            for line in lines:
                text = line.text.strip()
                if not text:
                    continue
                words = line.get_words()
                if not words:
                    continue
                # Table cells / columnar rows (e.g. dataset comparison tables
                # rendered as text) have large gaps between cell values and are
                # excluded from margin checks — their edges are not text margins.
                if _is_columnar_line(words):
                    continue
                    
                left_edges.append(words[0].bbox.x0)
                right_edges.append(words[-1].bbox.x1)
                valid_lines.append(line)
                
            if not valid_lines:
                continue
                
            median_left = statistics.median(left_edges)
            median_right = statistics.median(right_edges)
            
            # Indented paragraphs (quotations, declarations, list items) start
            # further right than the body baseline and are exempt from the left
            # margin rule; they may also legitimately overflow the right edge.
            is_indented = (len(valid_lines) == 1
                           and median_left > profile.body_left_indent + profile.indent_tolerance)
            
            if not is_indented and median_left < (expected_left_pt - tolerance):
                if len(valid_lines) == 1:
                    # Single line left overflow is ignored or could be a minor warning, but we only strictly handled right overflow.
                    pass
                else:
                    self._report_left_violation(p, valid_lines, expected_left_pt, median_left, violations)
                
            if median_right > (max_x1 + tolerance):
                if len(valid_lines) == 1:
                    self._check_single_line_edge_case(p, valid_lines[0], max_x1, violations)
                else:
                    self._report_right_violation(p, valid_lines, max_x1, median_right, violations)
            elif max(right_edges) > (max_x1 + tolerance):
                # An overfull \hbox within a multi-line paragraph!
                overflowing_lines = [l for i, l in enumerate(valid_lines) if right_edges[i] > (max_x1 + tolerance)]
                for ol in overflowing_lines:
                    self._check_single_line_edge_case(p, ol, max_x1, violations)
                
        return violations
        
    def _check_single_line_edge_case(self, p: Paragraph, line, expected_max: float, violations: List[Violation]):
        text = line.text.strip()
        actual_x1 = line.get_words()[-1].bbox.x1
        
        has_url = bool(URL_PATTERN.search(text))
        has_doi = bool(DOI_PATTERN.search(text))
        has_email = bool(EMAIL_PATTERN.search(text))
        
        severity = Severity.WARNING if (has_url or has_doi or has_email) else Severity.MINOR
        reason = "Single line overflow due to unbreakable string (URL/DOI)." if (has_url or has_doi or has_email) else "Single line overflow."
        
        violations.append(Violation(
            category=Category.PAGE_LAYOUT,
            severity=severity,
            page=p.page_num,
            description=f"Right margin overflow in {p.block_type.value}.",
            expected=f"<= {expected_max}pt",
            detected=f"{round(actual_x1, 2)}pt",
            confidence=p.classification_confidence,
            signals=p.classification_reasons,
            reason=reason,
            suggested_fix="Enable URL wrapping, insert soft breaks, or adjust kerning.",
            location=text[:40] + "...",
            bbox=(line.bbox.x0, line.bbox.y0, line.bbox.x1, line.bbox.y1)
        ))

    def _report_left_violation(self, p: Paragraph, lines, expected: float, actual: float, violations: List[Violation]):
        bbox = (actual, lines[0].bbox.y0, max(l.bbox.x1 for l in lines), lines[-1].bbox.y1)
        
        violations.append(Violation(
            category=Category.PAGE_LAYOUT,
            severity=Severity.CRITICAL,
            page=p.page_num,
            description=f"Left margin violation in {p.block_type.value}.",
            expected=f">= {expected}pt",
            detected=f"{round(actual, 2)}pt",
            confidence=p.classification_confidence,
            signals=p.classification_reasons,
            reason=f"Paragraph consistently violates the left margin.",
            suggested_fix="Adjust the page layout margins to 1.5 inches on the left.",
            location=lines[0].text[:40] + "...",
            bbox=bbox
        ))

    def _report_right_violation(self, p: Paragraph, lines, expected: float, actual: float, violations: List[Violation]):
        bbox = (min(l.bbox.x0 for l in lines), lines[0].bbox.y0, actual, lines[-1].bbox.y1)
        
        violations.append(Violation(
            category=Category.PAGE_LAYOUT,
            severity=Severity.CRITICAL,
            page=p.page_num,
            description=f"Right margin violation in {p.block_type.value}.",
            expected=f"<= {expected}pt",
            detected=f"{round(actual, 2)}pt",
            confidence=p.classification_confidence,
            signals=p.classification_reasons,
            reason=f"Paragraph consistently violates the right margin.",
            suggested_fix="Ensure paragraph formatting does not exceed 1.0 inch on the right edge.",
            location=lines[0].text[:40] + "...",
            bbox=bbox
        ))
