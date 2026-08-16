from typing import List
from nlp.dom import DocumentModel, BlockType
from utils.error_model import Violation
from utils.constants import Category, Severity
from utils.fonts import is_code_font, looks_like_code, normalize_font_name
from utils.profile import build_profile
from checks.validators import ValidationRule

import re


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


def _same_family(a: str, b: str) -> bool:
    """True if two font names share the same family root (weight/style variants)."""
    a, b = normalize_font_name(a), normalize_font_name(b)
    if not a or not b:
        return False
    if a == b:
        return True
    prefix = _common_prefix_len(a, b)
    return prefix / min(len(a), len(b)) >= 0.7


def _matches_allowed(normalized: str, allowed: set[str]) -> bool:
    """True if the font matches any allowed family (deterministic)."""
    return any(_same_family(normalized, fam) for fam in allowed)


# Paragraphs whose dominant size falls in these bands are almost certainly
# misclassified non-body elements (footnotes, table cells, headings) and are
# skipped instead of being reported as font errors.
_BODY_SIZE_BAND = (9.5, 15.0)
_SIZE_TOLERANCE = 1.0


class FontValidator(ValidationRule):
    def validate(self, doc: DocumentModel) -> List[Violation]:
        violations = []

        profile = self.profile if self.profile is not None else build_profile(doc, self.config)
        spec_body_size = self.config.typography.body_size

        # ── Document-level systemic deviation check (hybrid strategy) ────────
        # The document's own dominant body size is the baseline for per-paragraph
        # checks, but if it genuinely misses the spec we still flag it once.
        if abs(profile.body_font_size - spec_body_size) > _SIZE_TOLERANCE:
            violations.append(Violation(
                category=Category.FONT,
                severity=Severity.CRITICAL,
                page=-1,
                description="Document body font size deviates from the configured standard.",
                expected=f"{spec_body_size}pt",
                detected=f"{profile.body_font_size}pt",
                reason=("The dominant body text size across the document is "
                        f"{profile.body_font_size}pt, expected {spec_body_size}pt."),
                suggested_fix="Set the body text size to the required specification.",
            ))

        # ── Spec-compatible font families ────────────────────────────────────
        allowed_fonts = set()
        for f in self.config.typography.allowed_fonts:
            allowed_fonts.add(normalize_font_name(f))
        allowed_fonts.update([
            "times", "timesnewroman", "nimbusrom", "nimbusroman",
            "texgyretermes", "liberationserif", "urwnimbusroman",
        ])
        # The document's own dominant family is accepted as a consistent baseline.
        if profile.body_font_family:
            allowed_fonts.add(normalize_font_name(profile.body_font_family))

        paragraphs = doc.get_all_paragraphs()
        text_blocks = []
        for p in paragraphs:
            if not self._is_checkable(p):
                continue
            text_blocks.append(p)

        # Count how many checkable paragraphs share each family root, to scale
        # the severity of family violations (isolated vs systemic).
        family_counts: dict[str, int] = {}
        for p in text_blocks:
            nf = normalize_font_name(p.dominant_font)
            if not nf:
                continue
            family_counts[nf] = family_counts.get(nf, 0) + 1
        dominant_family = profile.body_font_family

        for p in text_blocks:
            nf = normalize_font_name(p.dominant_font)
            if not nf:
                continue

            # ── Font size check (body text only) ────────────────────────────
            if p.block_type == BlockType.BODY_TEXT and p.dominant_font_size:
                dev = round(p.dominant_font_size, 2) - round(profile.body_font_size, 2)
                if abs(dev) > _SIZE_TOLERANCE:
                    # Far from the body band → misclassified element, not a real error.
                    if _BODY_SIZE_BAND[0] <= p.dominant_font_size <= _BODY_SIZE_BAND[1]:
                        violations.append(Violation(
                            category=Category.FONT,
                            severity=Severity.WARNING,
                            page=p.page_num,
                            description=f"Font size differs from body text in {p.block_type.value}.",
                            expected=f"~{profile.body_font_size}pt",
                            detected=f"{round(p.dominant_font_size, 2)}pt",
                            confidence=p.classification_confidence,
                            signals=p.classification_reasons,
                            reason=f"Paragraph size differs from the document's dominant body size by {abs(dev):.2f}pt.",
                            suggested_fix="Match the surrounding body text size.",
                            location=p.text[:30] + "...",
                            bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                        ))

            # ── Font family check ───────────────────────────────────────────
            if _matches_allowed(nf, allowed_fonts):
                continue
            affected = family_counts.get(nf, 0)
            fraction = affected / len(text_blocks) if text_blocks else 0.0
            severity = (
                Severity.CRITICAL if fraction >= 0.5
                else Severity.WARNING if affected > 1
                else Severity.MINOR
            )
            violations.append(Violation(
                    category=Category.FONT,
                    severity=severity,
                    page=p.page_num,
                    description=f"Font family outside the template in {p.block_type.value}.",
                    expected=f"one of {sorted(allowed_fonts)[:6]}",
                    detected=f"'{p.dominant_font}'",
                    confidence=p.classification_confidence,
                    signals=p.classification_reasons,
                    reason=f"Font '{p.dominant_font}' is not a template alias and is not the "
                           f"document's dominant family ('{dominant_family}').",
                    suggested_fix="Use the template font family for this text.",
                    location=p.text[:30] + "...",
                    bbox=(p.bbox.x0, p.bbox.y0, p.bbox.x1, p.bbox.y1)
                ))

        return violations

    def _is_checkable(self, p) -> bool:
        """True if the paragraph is body-like text that should be font-checked."""
        if p.block_type not in (BlockType.BODY_TEXT, BlockType.CAPTION, BlockType.HEADING_1):
            return False

        text = p.text.strip()
        if not text or len(text) < 3:
            return False

        # Code / math / equation content is exempt.
        if is_code_font(p.dominant_font):
            return False
        if looks_like_code(text):
            return False
        if re.search(r"\(\d+\.\d+\)\s*$", text):
            return False

        # Tiny fragments and far-out-of-band sizes are misclassified elements.
        if p.dominant_font_size:
            if p.dominant_font_size < _BODY_SIZE_BAND[0]:
                return False
        return True
