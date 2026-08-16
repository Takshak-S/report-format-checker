"""
checks/heading_validator.py

HeadingValidator validates the heading hierarchy against the configured
template (vit_template.json → config.headings.*):

  1. Numbering continuity  — L1/L2/L3 numbers must advance by one within their
                             parent context (no gaps, no repeats).
  2. Case rules            — driven by config.headings.*.case
                             ("uppercase" / "title" / "sentence").
  3. New page (level 0)    — chapter titles must open a fresh page when
                             config.headings.level_0.new_page is set.
  4. Bold / italic         — headings must match the configured weight/style.
                             Nimbus Roman No9L renders LaTeX \\bfseries as the
                             Medium weight ("medi"), which counts as bold.
  5. Size                  — headings must match config.headings.*.size within
                             a tight band (numbered headings only).

Like the other validators it is profile+config driven and its findings feed
the noise filter (systemic heading deviations collapse to one finding).
"""
from __future__ import annotations

import re
from typing import List

from nlp.dom import DocumentModel, BlockType, Paragraph
from utils.error_model import Violation
from utils.constants import Category, Severity
from utils.profile import build_profile
from checks.validators import ValidationRule

_NUM_L1_RE = re.compile(r"^(\d+)\.(\d+)(\s|$)")
_NUM_L2_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(\s|$)")
_NUM_L3_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)(\s|$)")

# Nimbus Roman No9L (the LaTeX default in these reports) renders \\bfseries
# as the Medium weight.  Treat medium/demibold/semibold as bold for template
# compliance, otherwise every LaTeX heading would be reported as "not bold".
_MEDIUM_FONT_RE = re.compile(r"(medi|medium|demibold|semibold|bold)", re.IGNORECASE)

# Headings must match their configured size tightly (headings are a fixed
# spec, unlike body text which has rendering variance).
_HEADING_SIZE_TOLERANCE = 2.5

_TITLE_CASE_SKIP_WORDS = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "in", "on",
    "at", "to", "of", "by", "as", "is", "it", "vs", "via", "per",
    "with", "from", "into", "over", "under", "than", "that",
}


class DetectedHeading:
    def __init__(self, level: int, text: str, page_num: int, paragraph: Paragraph):
        self.level = level
        self.text = text
        self.page_num = page_num
        self.paragraph = paragraph


class HeadingValidator(ValidationRule):
    # Block types that should be excluded from normal heading checks
    SPECIAL_SECTION_BLOCK_TYPES = {BlockType.BIBLIOGRAPHY, BlockType.REFERENCE, BlockType.APPENDIX}

    def validate(self, doc: DocumentModel) -> List[Violation]:
        profile = self.profile if self.profile is not None else build_profile(doc, self.config)
        headings = self._collect(doc)

        violations: List[Violation] = []
        violations.extend(self._check_numbering(headings))
        violations.extend(self._check_case(headings))
        violations.extend(self._check_new_page(headings, doc))
        violations.extend(self._check_bold_italic(headings))
        violations.extend(self._check_size(headings, profile))
        return violations

    # ── Collection ──────────────────────────────────────────────────────────
    def _collect(self, doc: DocumentModel) -> List[DetectedHeading]:
        headings: List[DetectedHeading] = []
        for p in doc.get_all_paragraphs():
            if p.block_type == BlockType.CHAPTER_TITLE:
                headings.append(DetectedHeading(0, p.text.strip(), p.page_num, p))
            elif p.block_type == BlockType.HEADING_1:
                headings.append(DetectedHeading(1, p.text.strip(), p.page_num, p))
            elif p.block_type == BlockType.HEADING_2:
                headings.append(DetectedHeading(2, p.text.strip(), p.page_num, p))
            elif p.block_type == BlockType.HEADING_3:
                headings.append(DetectedHeading(3, p.text.strip(), p.page_num, p))
        return headings

    # ── 1. Numbering continuity ─────────────────────────────────────────────
    def _check_numbering(self, headings: List[DetectedHeading]) -> List[Violation]:
        violations = []
        last_l1_per_chapter: dict[int, int] = {}
        last_l2_per_section: dict[tuple, int] = {}
        last_l3_per_subsection: dict[tuple, int] = {}
        patterns = {
            1: _NUM_L1_RE,
            2: _NUM_L2_RE,
            3: _NUM_L3_RE,
        }

        for h in headings:
            # Skip numbering checks inside special sections (bibliography, reference, appendix)
            if h.paragraph.block_type in self.SPECIAL_SECTION_BLOCK_TYPES:
                continue
            if h.level not in patterns:
                continue
            m = patterns[h.level].match(h.text)
            if not m:
                continue

            if h.level == 1:
                ch, sec = int(m.group(1)), int(m.group(2))
                prev = last_l1_per_chapter.get(ch, 0)
                expected = f"{ch}.{prev + 1}"
            elif h.level == 2:
                ch, sec, sub = int(m.group(1)), int(m.group(2)), int(m.group(3))
                key = (ch, sec)
                prev = last_l2_per_section.get(key, 0)
                expected = f"{ch}.{sec}.{prev + 1}"
                if sub != prev + 1:
                    violations.append(self._numbering_violation(h, 2, expected, f"{ch}.{sec}.{sub}"))
                last_l2_per_section[key] = sub
                continue
            else:
                ch, sec, sub, subsub = (int(m.group(i)) for i in range(1, 5))
                key = (ch, sec, sub)
                prev = last_l3_per_subsection.get(key, 0)
                expected = f"{ch}.{sec}.{sub}.{prev + 1}"
                if subsub != prev + 1:
                    violations.append(self._numbering_violation(h, 3, expected, f"{ch}.{sec}.{sub}.{subsub}"))
                last_l3_per_subsection[key] = subsub
                continue

            if sec != prev + 1:
                violations.append(self._numbering_violation(h, 1, expected, f"{ch}.{sec}"))
            last_l1_per_chapter[ch] = sec

        return violations

    def _numbering_violation(self, h: DetectedHeading, level: int,
                             expected: str, detected: str) -> Violation:
        return Violation(
            category=Category.HEADINGS,
            severity=Severity.WARNING,
            page=h.page_num,
            description=f"Heading numbering gap or repeat at Level {level}",
            expected=expected,
            detected=detected,
            confidence=h.paragraph.classification_confidence,
            signals=h.paragraph.classification_reasons,
            reason=f"Expected numbering sequence {expected}, found '{h.text[:40]}'.",
            suggested_fix=f"Change numbering to {expected}",
            location=h.text[:30],
            bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                  h.paragraph.bbox.x1, h.paragraph.bbox.y1),
        )

    # ── 2. Case rules (config.headings.*.case) ──────────────────────────────
    def _check_case(self, headings: List[DetectedHeading]) -> List[Violation]:
        violations = []
        for h in headings:
            case = self._case_rule(h.level)
            if not case:
                continue
            body = self._numbered_body(h.text, h.level)
            if not body:
                continue

            if case == "uppercase" and not body.isupper():
                violations.append(Violation(
                    category=Category.HEADINGS,
                    severity=Severity.WARNING,
                    page=h.page_num,
                    description=f"Level-{h.level} heading must be UPPERCASE",
                    expected="UPPERCASE TEXT",
                    detected=f"'{body[:30]}'",
                    confidence=h.paragraph.classification_confidence,
                    signals=h.paragraph.classification_reasons,
                    reason=f"Template requires UPPERCASE level-{h.level} headings.",
                    suggested_fix="Convert the heading text to UPPERCASE.",
                    location=h.text[:30],
                    bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                          h.paragraph.bbox.x1, h.paragraph.bbox.y1),
                ))
            elif case == "title":
                words = body.split()
                # Significant words exclude short articles/prepositions; a stray
                # lowercase term ("Early stopping", "Inter fold variability") is
                # normal ML wording and not an actionable defect.  Only report
                # sentence-case or predominantly-lowercase headings: a heading
                # whose FIRST significant word is lowercase, or that has 3+
                # lowercase significant words.
                significant = [
                    w for w in words
                    if w.lower() not in _TITLE_CASE_SKIP_WORDS and len(w) > 3
                ]
                non_title = [
                    w for w in significant
                    if w[0].islower()
                ]
                first_word_lower = bool(significant and significant[0][0].islower())
                if first_word_lower or len(non_title) >= 3:
                    violations.append(Violation(
                        category=Category.HEADINGS,
                        severity=Severity.INFO,
                        page=h.page_num,
                        description=f"Level-{h.level} heading should use Title Case",
                        expected="Title Case Text",
                        detected=f"Contains lowercase: {non_title[:3]}",
                        confidence=h.paragraph.classification_confidence,
                        signals=h.paragraph.classification_reasons,
                        reason="Template requires Title Case for this heading level.",
                        suggested_fix="Capitalize the first letter of each significant word.",
                        location=h.text[:30],
                        bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                              h.paragraph.bbox.x1, h.paragraph.bbox.y1),
                    ))
        return violations

    def _case_rule(self, level: int) -> str:
        cfg = {0: self.config.headings.level_0,
               1: self.config.headings.level_1,
               2: self.config.headings.level_2,
               3: self.config.headings.level_3}.get(level)
        return cfg.case if cfg else ""

    def _numbered_body(self, text: str, level: int) -> str:
        if level == 0:
            body = re.sub(r"^CHAPTER\s+\d+[\s.:\u2013\u2014\-]*", "", text, flags=re.IGNORECASE)
            return body.strip()
        pattern = {1: _NUM_L1_RE, 2: _NUM_L2_RE, 3: _NUM_L3_RE}.get(level)
        if not pattern:
            return ""
        return re.sub(r"^\d+(\.\d+){0,3}\s+", "", text)

    # ── 3. Chapter title starts a new page ──────────────────────────────────
    def _check_new_page(self, headings: List[DetectedHeading], doc: DocumentModel) -> List[Violation]:
        violations = []
        if not self.config.headings.level_0.new_page:
            return violations
        for h in headings:
            if h.level != 0 or h.page_num == 1:
                continue
            page_node = doc.pages[h.page_num - 1]
            significant_above = [
                p for p in page_node.get_paragraphs()
                if p is not h.paragraph
                and p.bbox.y1 < h.paragraph.bbox.y0 - 40
                and len(p.text.strip()) > 10
                and p.bbox.y0 >= 72
            ]
            if significant_above:
                violations.append(Violation(
                    category=Category.HEADINGS,
                    severity=Severity.WARNING,
                    page=h.page_num,
                    description="Chapter title (L0) should start on a new page",
                    expected="First content line on page",
                    detected=f"Found {len(significant_above)} element(s) above it",
                    confidence=h.paragraph.classification_confidence,
                    signals=h.paragraph.classification_reasons,
                    reason=f"Chapter title '{h.text[:30]}' is not the first content element on page {h.page_num}.",
                    suggested_fix="Insert a page break before the chapter title.",
                    location=h.text[:30],
                    bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                          h.paragraph.bbox.x1, h.paragraph.bbox.y1),
                ))
        return violations

    # ── 4. Bold / italic per config ─────────────────────────────────────────
    def _check_bold_italic(self, headings: List[DetectedHeading]) -> List[Violation]:
        violations = []
        for h in headings:
            cfg = {0: self.config.headings.level_0,
                   1: self.config.headings.level_1,
                   2: self.config.headings.level_2,
                   3: self.config.headings.level_3}.get(h.level)
            if cfg is None:
                continue
            if cfg.bold and not self._is_bold(h.paragraph):
                violations.append(self._style_violation(h, "bold", cfg))
            if cfg.italic and not self._is_italic(h.paragraph):
                violations.append(self._style_violation(h, "italic", cfg))
        return violations

    def _style_violation(self, h: DetectedHeading, style: str, cfg) -> Violation:
        return Violation(
            category=Category.HEADINGS,
            severity=Severity.MINOR,
            page=h.page_num,
            description=f"Level-{h.level} heading is not {style}",
            expected=f"{style} heading text",
            detected=f"font '{h.paragraph.dominant_font or '?'}'",
            confidence=h.paragraph.classification_confidence,
            signals=h.paragraph.classification_reasons,
            reason=f"Template requires {style} level-{h.level} headings "
                   f"(configured size {cfg.size}pt).",
            suggested_fix=f"Apply the {style} font style to this heading.",
            location=h.text[:30],
            bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                  h.paragraph.bbox.x1, h.paragraph.bbox.y1),
        )

    def _is_bold(self, p: Paragraph) -> bool:
        if p.dominant_bold:
            return True
        if _MEDIUM_FONT_RE.search(p.dominant_font or ""):
            return True
        for line in p.get_lines():
            for w in line.get_words():
                if _MEDIUM_FONT_RE.search(w.font):
                    return True
        return False

    def _has_number(self, h: DetectedHeading) -> bool:
        if h.level == 0:
            return bool(re.match(r"^chapter\s+\d+", h.text, re.IGNORECASE))
        pattern = {1: _NUM_L1_RE, 2: _NUM_L2_RE, 3: _NUM_L3_RE}.get(h.level)
        return bool(pattern and pattern.match(h.text))

    def _is_italic(self, p: Paragraph) -> bool:
        if p.dominant_italic:
            return True
        return any(w.italic for line in p.get_lines() for w in line.get_words())

    # ── 5. Size per profile (numbered headings only) ─────────────────────────
    def _check_size(self, headings: List[DetectedHeading], profile) -> List[Violation]:
        violations = []
        # map level to profile attribute
        level_to_attr = {
            0: 'heading_l0_size',
            1: 'heading_l1_size',
            2: 'heading_l2_size',
            3: 'heading_l3_size',
        }
        for h in headings:
            # Skip size checks inside special sections
            if h.paragraph.block_type in self.SPECIAL_SECTION_BLOCK_TYPES:
                continue
            if not self._has_number(h):
                continue
            expected_size = getattr(profile, level_to_attr.get(h.level, 'heading_l1_size'), None)
            if expected_size is None or not h.paragraph.dominant_font_size:
                continue
            if abs(h.paragraph.dominant_font_size - expected_size) <= _HEADING_SIZE_TOLERANCE:
                continue
            violations.append(Violation(
                category=Category.HEADINGS,
                severity=Severity.MAJOR,
                page=h.page_num,
                description=f"Level-{h.level} heading size deviates from the document's dominant heading size.",
                expected=f"{expected_size}pt",
                detected=f"{round(h.paragraph.dominant_font_size, 1)}pt",
                confidence=h.paragraph.classification_confidence,
                signals=h.paragraph.classification_reasons,
                reason=f"Level-{h.level} heading is {round(h.paragraph.dominant_font_size, 1)}pt, "
                       f"expected {expected_size}pt per the document profile.",
                suggested_fix="Set the heading font size to match the document's dominant heading size.",
                location=h.text[:30],
                bbox=(h.paragraph.bbox.x0, h.paragraph.bbox.y0,
                      h.paragraph.bbox.x1, h.paragraph.bbox.y1),
            ))
        return violations
