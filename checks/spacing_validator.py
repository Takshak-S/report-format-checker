from typing import List
from collections import Counter
from nlp.dom import DocumentModel, BlockType
from utils.error_model import Violation
from utils.constants import Category, Severity
from checks.validators import ValidationRule


class SpacingValidator(ValidationRule):
    def validate(self, doc: DocumentModel) -> List[Violation]:
        violations = []

        profile = self.profile if self.profile is not None else self.config
        expected_alignment = self.config.paragraph.alignment  # "justified"
        expected_line_spacing = self.config.paragraph.line_spacing  # 1.5

        # Tolerance for line spacing check
        LINE_SPACING_TOLERANCE = 0.30
        # A paragraph must have at least this many lines whose alignment can be
        # established (i.e. excluding the ragged last line) before alignment is
        # judged; a single line or a lone ragged line cannot prove a deviation.
        MIN_ALIGNMENT_LINES = 2
        # Proportion of violating lines required before flagging alignment.
        ALIGNMENT_VIOLATION_FRACTION = 0.5
        # A paragraph-level spacing violation requires BOTH the median to deviate
        # beyond tolerance AND a significant proportion of lines to deviate.
        MIN_SPACING_LINES = 2
        SPACING_VIOLATION_FRACTION = 0.5

        paragraphs = doc.get_all_paragraphs()
        for p in paragraphs:
            if p.block_type != BlockType.BODY_TEXT:
                continue
            if not p.text.strip():
                continue

            lines = p.get_lines()
            if not lines:
                continue

            # ── Alignment (paragraph-level, robust) ────────────────────────
            # The last line of a justified paragraph is naturally ragged and is
            # excluded; a single stray line must not trigger a finding.
            judged_lines = lines[:-1] if len(lines) > 1 else lines
            alignments = [l.alignment for l in judged_lines if l.alignment]
            if len(alignments) >= MIN_ALIGNMENT_LINES:
                alignment_counts = Counter(alignments)
                dominant_alignment = alignment_counts.most_common(1)[0][0]

                if dominant_alignment != expected_alignment:
                    violating = sum(1 for a in alignments if a != expected_alignment)
                    fraction = violating / len(alignments)
                    if violating >= MIN_ALIGNMENT_LINES and fraction >= ALIGNMENT_VIOLATION_FRACTION:
                        severity = Severity.WARNING if fraction > 0.75 else Severity.MINOR
                        violations.append(Violation(
                            category=Category.ALIGNMENT,
                            severity=severity,
                            page=p.page_num,
                            description=f"Paragraph alignment '{dominant_alignment}' differs from required '{expected_alignment}'.",
                            expected=expected_alignment,
                            detected=dominant_alignment,
                            confidence=p.classification_confidence,
                            signals=p.classification_reasons,
                            reason=f"{violating}/{len(alignments)} judged lines in paragraph use '{dominant_alignment}' alignment instead of '{expected_alignment}'.",
                            suggested_fix=f"Set paragraph alignment to '{expected_alignment}'.",
                            location=p.text[:50] + "..." if len(p.text) > 50 else p.text,
                            bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                        ))

            # ── Line spacing (paragraph-level, robust) ─────────────────────
            # Only lines that have a following line within the paragraph carry a
            # measured line_spacing (reconstruction leaves the last line at 0).
            spacings = [l.line_spacing for l in lines if l.line_spacing and l.line_spacing > 0]
            if len(spacings) >= MIN_SPACING_LINES:
                ordered = sorted(spacings)
                median = ordered[len(ordered) // 2]
                if abs(median - expected_line_spacing) > LINE_SPACING_TOLERANCE:
                    deviating = sum(1 for s in spacings if abs(s - expected_line_spacing) > LINE_SPACING_TOLERANCE)
                    fraction = deviating / len(spacings)
                    if fraction >= SPACING_VIOLATION_FRACTION:
                        severity = Severity.WARNING if abs(median - expected_line_spacing) > 0.5 else Severity.MINOR
                        violations.append(Violation(
                            category=Category.SPACING,
                            severity=severity,
                            page=p.page_num,
                            description=f"Paragraph line spacing {median:.2f} differs from required {expected_line_spacing:.2f}.",
                            expected=f"{expected_line_spacing:.2f}",
                            detected=f"{median:.2f}",
                            confidence=p.classification_confidence,
                            signals=p.classification_reasons,
                            reason=f"{deviating}/{len(spacings)} lines in paragraph deviate from {expected_line_spacing:.2f} (median {median:.2f}).",
                            suggested_fix=f"Adjust paragraph line spacing to {expected_line_spacing:.2f}.",
                            location=p.text[:50] + "..." if len(p.text) > 50 else p.text,
                            bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                        ))

        return violations
