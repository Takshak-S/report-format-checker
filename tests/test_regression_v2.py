"""
tests/test_regression_v2.py

Regression tests locking in the second noise-reduction pass over the corpus:

  * bibliography / references / appendix state machine (medium/semibold fonts,
    BIBLIOGRAPHY->APPENDIX transition, H019-style APA entries)
  * list detection for en-dash / middle-dot bullets and Greek symbol glossaries
  * text-area-center alignment and boxed/block-quote (justified within its box)
  * paragraph-level spacing/alignment guards (noise needs 2+ violating lines)
  * heading case + profile-size behaviour, and DPI validation disabled
  * LIST margin validation (per-line edge analysis, bullet-indent exemption)

These are unit-level (construct the DOM directly) so they run without
test_files/.  The corpus-level heading assertion lives in test_corpus.py.
"""
from __future__ import annotations

import types

from nlp.dom import (DocumentModel, Page, Paragraph, Line, Word, BBox,
                     BlockType)
from nlp.classifier import LayoutAnalyzer
from nlp.reconstruction import DocumentReconstructor
from checks.heading_validator import HeadingValidator, DetectedHeading
from checks.margin_validator import MarginValidator
from checks.spacing_validator import SpacingValidator
from checks.image_validator import ImageValidator
from utils.constants import Category, Severity

PAGE_W = 595.276
PAGE_H = 841.89
LEFT_M = 108.0
RIGHT_M = PAGE_W - 72.0  # 523.276


# ── DOM builders ──────────────────────────────────────────────────────────
def make_line(text, x0=LEFT_M, x1=RIGHT_M, y0=100.0, y1=None,
              font="nimbusromno9l-regu", font_size=12.0, alignment="",
              line_spacing=0.0, words=None, **kw):
    if y1 is None:
        y1 = y0 + 14.0
    ln = Line(id="l", page_num=1, bbox=BBox(x0, y0, x1, y1), text=text,
              font=font, font_size=font_size, alignment=alignment,
              line_spacing=line_spacing, **kw)
    for wt, wx0, wx1 in (words or []):
        ln.add_child(Word(id="w", page_num=1, bbox=BBox(wx0, y0, wx1, y1),
                          text=wt, font=font, font_size=font_size))
    return ln


def make_paragraph(text, block_type=None, font="nimbusromno9l-regu",
                   font_size=12.0, bold=False, lines=None):
    if lines is None:
        lines = [make_line(t) for t in text.split("\n")]
    para_bbox = BBox(
        x0=min(l.bbox.x0 for l in lines),
        y0=min(l.bbox.y0 for l in lines),
        x1=max(l.bbox.x1 for l in lines),
        y1=max(l.bbox.y1 for l in lines),
    )
    p = Paragraph(
        id="p", page_num=1, bbox=para_bbox,
        text="\n".join(l.text for l in lines),
        block_type=block_type or BlockType.UNKNOWN,
        dominant_font=font, dominant_font_size=font_size,
        dominant_bold=bold, dominant_italic=False,
    )
    for l in lines:
        p.add_child(l)
    return p


def make_body_paragraph(alignments, spacings, block_type=BlockType.BODY_TEXT,
                        n_lines=None, texts=None):
    n = n_lines or len(alignments)
    lines = []
    for i in range(n):
        al = alignments[i] if i < len(alignments) else "justified"
        sp = spacings[i] if i < len(spacings) else 0.0
        t = (texts[i] if texts else
             "Sample body text line number %d filled with alpha characters." % i)
        lines.append(make_line(t, y0=100.0 + i * 15.0, y1=114.0 + i * 15.0,
                               alignment=al, line_spacing=sp))
    return make_paragraph("\n".join(l.text for l in lines),
                          block_type=block_type, lines=lines)


def make_doc(paragraphs):
    doc = DocumentModel()
    page = Page(id="pg", page_num=1, bbox=BBox(0, 0, PAGE_W, PAGE_H),
                width=PAGE_W, height=PAGE_H)
    for p in paragraphs:
        page.add_child(p)
    doc.pages.append(page)
    return doc


def classify(doc):
    LayoutAnalyzer().classify(doc)
    return [p.block_type for p in doc.get_all_paragraphs()]


def heading_profile():
    return types.SimpleNamespace(
        heading_l0_size=16.0, heading_l1_size=14.0,
        heading_l2_size=12.0, heading_l3_size=12.0)


# ── Bibliography / References / Appendix ──────────────────────────────────
class TestBibliographyAndAppendix:
    def test_medium_bibliography_heading_is_structural(self):
        doc = make_doc([
            make_paragraph("Bibliography", font="nimbusromno9l-medi"),
            make_paragraph("Doe, J. (2020). A work. Journal of X, 1(1), 1-10."),
        ])
        types_ = classify(doc)
        assert types_[0] == BlockType.BIBLIOGRAPHY
        assert types_[1] == BlockType.BIBLIOGRAPHY
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v.validate(doc) == []

    def test_semibold_references_detected(self):
        doc = make_doc([
            make_paragraph("References", font="latinmodernroman-demibold"),
            make_paragraph("Smith, J. (2020). Learning dynamics. Nature AI, 5(2), "
                           "30-40. https://doi.org/10.1038/s41586-020-0000-0"),
        ])
        types_ = classify(doc)
        assert types_[0] == BlockType.BIBLIOGRAPHY
        assert types_[1] == BlockType.BIBLIOGRAPHY
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v.validate(doc) == []

    def test_appendix_content_not_treated_as_heading(self):
        doc = make_doc([
            make_paragraph("Appendix", bold=True),
            make_paragraph("A.1 Raw data tables"),
            make_paragraph("Additional experimental results and figures."),
        ])
        types_ = classify(doc)
        assert types_[0] == BlockType.APPENDIX
        assert types_[1] not in (BlockType.HEADING_1, BlockType.HEADING_2,
                                 BlockType.HEADING_3, BlockType.BODY_TEXT)
        assert types_[2] not in (BlockType.HEADING_1, BlockType.HEADING_2,
                                 BlockType.HEADING_3, BlockType.BODY_TEXT)
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v.validate(doc) == []

    def test_bibliography_to_appendix_transition(self):
        doc = make_doc([
            make_paragraph("References", font="nimbusromno9l-medi"),
            make_paragraph("Author, B. (2021). Paper title. J. 2(3), 1-5."),
            make_paragraph("Appendix", bold=True),
            make_paragraph("This is appendix content, not a reference."),
        ])
        types_ = classify(doc)
        assert types_[1] == BlockType.BIBLIOGRAPHY
        assert types_[3] != BlockType.BIBLIOGRAPHY

    def test_h019_style_references_no_heading_false_positives(self):
        doc = make_doc([
            make_paragraph("References", font="nimbusromno9l-medi"),
            make_paragraph("Vaswani, A., Shazeer, N., Parmar, N., et al. (2017). "
                           "Attention is all you need. NeurIPS. "
                           "https://doi.org/10.48550/arXiv.1706.03762"),
            make_paragraph("He, K., Zhang, X., Ren, S., & Sun, J. (2016). "
                           "Deep residual learning for image recognition. "
                           "CVPR, 770-778."),
            make_paragraph("Kingma, D. P., & Ba, J. (2015). Adam: A method for "
                           "stochastic optimization. ICLR."),
        ])
        for t in classify(doc):
            assert t not in (BlockType.HEADING_1, BlockType.HEADING_2,
                             BlockType.HEADING_3, BlockType.BODY_TEXT)
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v.validate(doc) == []


# ── List / glossary detection ─────────────────────────────────────────────
class TestListDetection:
    def test_en_dash_and_middle_dot_bullets_classified_as_list(self):
        doc = make_doc([
            make_paragraph("\u2013 Frontend Technologies: React, Vue and Tailwind CSS."),
            make_paragraph("\u00B7 In most systems, it is not considered to involve overhead."),
            make_paragraph("\u2013 Image Build: Gets the code, builds the Docker image\n"
                           "with all dependencies bundled."),
        ])
        assert classify(doc) == [BlockType.LIST, BlockType.LIST, BlockType.LIST]

    def test_greek_symbol_glossary_list_classified(self):
        lines = []
        for i, (sym, exp) in enumerate([
            ("\u03B1", "Learning rate"), ("\u03B2", "Beta / Bias parameter"),
            ("\u0394", "Chaos / Variance")]):
            lines.append(make_line(
                f"{sym} {exp}",
                words=[(sym, 130.0, 136.5), (exp, 149.4, 250.0)],
                y0=100.0 + i * 15.0, y1=114.0 + i * 15.0))
        doc = make_doc([make_paragraph("\n".join(l.text for l in lines), lines=lines)])
        assert classify(doc) == [BlockType.LIST]

    def test_list_marker_line_starts_new_paragraph(self):
        recon = DocumentReconstructor()
        lines = [
            make_line("Let's maintain total transparency regarding what breaks."),
            make_line("1. The Mainnet Bloodbath: Attempting to run things.",
                      x0=108.0, y0=122.0, y1=140.0),
            make_line("This line continues the list item above.",
                      x0=108.0, y0=144.0, y1=162.0),
        ]
        paras = recon._build_paragraphs(lines, 1)
        assert len(paras) == 2
        assert paras[0].text.startswith("Let's")
        assert paras[1].text.startswith("1. The Mainnet")

    def test_code_font_marker_line_does_not_split_code_block(self):
        recon = DocumentReconstructor()
        y0s = [100.0, 116.0, 132.0, 148.0, 164.0]
        lines = [
            make_line('"""', font="courier", y0=y0s[0]),
            make_line('Returns dict with:', font="courier", y0=y0s[1]),
            make_line('- label : "FAKE" or "REAL"', font="courier", y0=y0s[2]),
            make_line('- confidence : float 0-1', font="courier", y0=y0s[3]),
            make_line('"""', font="courier", y0=y0s[4]),
        ]
        paras = recon._build_paragraphs(lines, 1)
        assert len(paras) == 1, "docstring marker lines must stay in the code block"


# ── Alignment / spacing ───────────────────────────────────────────────────
class TestAlignmentSpacingGuards:
    def test_single_noisy_spacing_line_not_flagged(self):
        p = make_body_paragraph(["justified"] * 4, [2.2, 1.5, 1.5])
        doc = make_doc([p])
        viols = SpacingValidator().validate(doc)
        assert not [v for v in viols if v.category == Category.SPACING]

    def test_consistently_wrong_spacing_flagged(self):
        p = make_body_paragraph(["justified"] * 5, [1.0] * 4)
        doc = make_doc([p])
        viols = SpacingValidator().validate(doc)
        assert any(v.category == Category.SPACING for v in viols)

    def test_single_unaligned_line_not_flagged(self):
        p = make_body_paragraph(["justified", "left", "justified"], [1.5, 1.5])
        doc = make_doc([p])
        viols = SpacingValidator().validate(doc)
        assert not [v for v in viols if v.category == Category.ALIGNMENT]

    def test_consistently_left_aligned_flagged(self):
        p = make_body_paragraph(["left"] * 4, [1.5] * 3)
        doc = make_doc([p])
        viols = SpacingValidator().validate(doc)
        assert any(v.category == Category.ALIGNMENT for v in viols)


# ── Alignment detection (reconstruction) ──────────────────────────────────
class TestAlignmentDetection:
    def _line(self, x0, x1, y0=100.0, alignment="", text="Sample text for the line "
             "which fills enough width to look plausible in a paragraph."):
        return make_line(text, x0=x0, x1=x1, y0=y0, y1=y0 + 14.0,
                         alignment=alignment)

    def test_centered_line_detected_via_text_area_center(self):
        recon = DocumentReconstructor()
        chars = [
            {"x0": 200.0, "x1": 280.0, "top": 100.0, "y0": 100.0, "y1": 115.0,
             "text": "Center", "fontname": "NimbusRomNo9L-Regu", "size": 12.0},
            {"x0": 330.0, "x1": 431.3, "top": 100.0, "y0": 100.0, "y1": 115.0,
             "text": "Line", "fontname": "NimbusRomNo9L-Regu", "size": 12.0},
        ]
        line = recon._make_line(chars, 1, PAGE_W, PAGE_H)
        assert line.alignment == "center"

    def test_boxed_block_quote_justified_within_box(self):
        recon = DocumentReconstructor()
        lines = [self._line(137.3, 494.0, y0=100.0 + i * 20.0, alignment="center")
                 for i in range(4)]
        lines[3] = self._line(137.3, 334.2, y0=160.0, alignment="left")
        p = recon._make_paragraph(lines, 1)
        got = [l.alignment for l in p.get_lines()]
        assert got[:3] == ["justified"] * 3
        assert got[3] == "left"

    def test_genuinely_left_aligned_paragraph_keeps_left(self):
        recon = DocumentReconstructor()
        x1s = [521.9, 498.5, 505.8, 471.1]
        lines = [self._line(108.0, x1s[i], y0=100.0 + i * 20.0,
                            alignment="left", text=f"line {i}")
                 for i in range(4)]
        p = recon._make_paragraph(lines, 1)
        got = [l.alignment for l in p.get_lines()]
        assert all(a == "left" for a in got), got


# ── TOC ───────────────────────────────────────────────────────────────────
class TestToc:
    def test_toc_entries_not_heading(self):
        doc = make_doc([
            make_paragraph("TABLE OF CONTENTS", bold=True),
            make_paragraph("1.1 Introduction . . . . . . . . . . 5"),
            make_paragraph("1.2 Literature Review . . . . . . . . . . 12"),
        ])
        types_ = classify(doc)
        assert types_[1] == BlockType.TOC
        assert types_[2] == BlockType.TOC
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v.validate(doc) == []


# ── Heading case & size ───────────────────────────────────────────────────
class TestHeadingRules:
    def _heading(self, level, text, block_type, font_size=12.0):
        p = make_paragraph(text, block_type=block_type, font_size=font_size)
        return DetectedHeading(level, text, 1, p)

    def test_title_case_accepts_ml_wording(self):
        v = HeadingValidator()
        v.profile = heading_profile()
        for text in ("5.7.1 Training Dynamics and Early stopping",
                     "5.7.2 Inter fold variability",
                     "5.7.3 Comparision with Reference papers"):
            assert not v._check_case([self._heading(2, text, BlockType.HEADING_2)])

    def test_sentence_case_heading_flagged(self):
        v = HeadingValidator()
        v.profile = heading_profile()
        h = self._heading(2, "5.7.1 training dynamics and early stopping",
                          BlockType.HEADING_2)
        assert v._check_case([h])

    def test_level1_uppercase_rule(self):
        v = HeadingValidator()
        v.profile = heading_profile()
        assert v._check_case([self._heading(1, "1.1 Introduction",
                                            BlockType.HEADING_1)])
        assert not v._check_case([self._heading(1, "1.1 INTRODUCTION",
                                                BlockType.HEADING_1)])

    def test_heading_size_check_uses_profile(self):
        v = HeadingValidator()
        v.profile = heading_profile()
        ok = self._heading(1, "1.1 Introduction", BlockType.HEADING_1, 14.0)
        assert not v._check_size([ok], v.profile)
        bad = self._heading(1, "1.2 Methods", BlockType.HEADING_1, 18.0)
        size_viols = v._check_size([bad], v.profile)
        assert any(x.severity == Severity.MAJOR for x in size_viols)


# ── LIST margin validation ────────────────────────────────────────────────
class TestMarginListValidation:
    """LIST paragraphs are checked with the existing per-line edge analysis.

    Bullet / hanging indentation is exempt via the is_indented rule, while a
    genuinely overfull line (an unbreakable token pushed past the right margin)
    is flagged per-line as MINOR — using the same logic as BODY_TEXT.
    """

    def _margin_profile(self):
        return types.SimpleNamespace(
            margin_tolerance=20.0,
            body_left_indent=107.9924,
            indent_tolerance=8.0)

    def _run(self, doc):
        v = MarginValidator()
        v.set_profile(self._margin_profile())
        return v.validate(doc)

    def _lines(self, spec):
        """spec: list of (x0, x1, text) -> Line nodes with dense word edges.

        Words are auto-spaced so the first word starts at x0 and the last word
        ends exactly at x1, with 2pt gaps between words (well under the 30pt
        columnar-line exclusion) so per-line edge analysis is exercised.
        """
        out = []
        for i, (x0, x1, text) in enumerate(spec):
            parts = [w for w in text.split() if w]
            n = len(parts)
            gap_total = 2.0 * (n - 1)
            word_w = (x1 - x0 - gap_total) / n
            words = []
            cur = x0
            for j, p in enumerate(parts):
                end = x1 if j == n - 1 else cur + word_w
                words.append((p, cur, end))
                cur = end + 2.0
            out.append(make_line(
                text, x0=x0, x1=x1,
                y0=100.0 + i * 15.0, y1=114.0 + i * 15.0,
                words=words))
        return out

    def test_list_line_exceeding_right_margin_detected(self):
        """Real H008 p56 geometry: line 2 ends at 552.12pt on the ReentrancyGuard word."""
        lines = self._lines([
            (127.22, 523.30,
             "\u2022 Reentrancy (SWC-107): We flatly refused to trust any external state"),
            (137.26, 552.12,
             "single function coughing up ETH wraps tightly in an OpenZeppelin ReentrancyGuard."),
            (137.26, 493.29,
             "State morphs internally before a single drop of currency exits the building."),
        ])
        doc = make_doc([make_paragraph("Reentrancy list item",
                                       block_type=BlockType.LIST, lines=lines)])
        viols = self._run(doc)
        assert len(viols) == 1
        v = viols[0]
        assert v.category == Category.PAGE_LAYOUT
        assert v.severity == Severity.MINOR
        assert v.description == "Right margin overflow in LIST."
        assert v.expected == "<= 523.276pt"
        assert v.detected == "552.12pt"
        assert "single function coughing up ETH" in v.location

    def test_normal_wrapped_list_line_not_flagged(self):
        """Justified wrapped lines ending ~523pt must not produce a finding."""
        lines = self._lines([
            (127.22, 523.30,
             "\u2022 Normal list item label that wraps onto the next line."),
            (137.26, 523.29,
             "second wrapped line ending right at the margin boundary."),
            (137.26, 493.29,
             "final short line."),
        ])
        doc = make_doc([make_paragraph("wrapped list",
                                       block_type=BlockType.LIST, lines=lines)])
        assert self._run(doc) == []

    def test_bullet_indentation_no_left_violation(self):
        """Bullet/hanging indents start right of the body baseline; no left finding."""
        single = self._lines([
            (127.22, 400.0,
             "\u2022 Single bullet item indented from the body baseline."),
        ])
        assert self._run(make_doc([make_paragraph(
            "bullet", block_type=BlockType.LIST, lines=single)])) == []

        multi = self._lines([
            (127.22, 400.0,
             "\u2022 Multi-line bullet item starts indented."),
            (137.26, 493.29,
             "continuation line hanging further right."),
        ])
        assert self._run(make_doc([make_paragraph(
            "bullet multi", block_type=BlockType.LIST, lines=multi)])) == []

    def test_multiline_list_checked_per_line_not_paragraph_bbox(self):
        """Only the single overfull line is flagged; the paragraph bbox is not used.

        The paragraph median right edge is 523.30pt (within tolerance), so a
        paragraph-level median check would flag nothing; the per-line branch
        flags exactly the one line whose edge exceeds the threshold, anchoring
        the violation to that line's bbox rather than the paragraph bbox.
        """
        lines = self._lines([
            (127.22, 523.30,
             "\u2022 Reentrancy (SWC-107): We flatly refused to trust any external state"),
            (137.26, 552.12,
             "single function coughing up ETH wraps tightly in an OpenZeppelin ReentrancyGuard."),
            (137.26, 493.29,
             "State morphs internally before a single drop of currency exits the building."),
        ])
        doc = make_doc([make_paragraph("Reentrancy list item",
                                       block_type=BlockType.LIST, lines=lines)])
        viols = self._run(doc)
        assert len(viols) == 1
        v = viols[0]
        assert v.severity == Severity.MINOR, "per-line overfull must stay MINOR, not paragraph CRITICAL"
        assert v.detected == "552.12pt"
        assert v.bbox == (137.26, 115.0, 552.12, 129.0), \
            "violation must anchor to the overfull line's bbox, not the paragraph bbox"

    def test_body_text_margin_behavior_unchanged(self):
        overfull = self._lines([
            (125.55, 562.93,
             "A few decisions in this Dockerfile move the needle on build performance."),
        ])
        viols = self._run(make_doc([make_paragraph(
            "body overfull", block_type=BlockType.BODY_TEXT, lines=overfull)]))
        assert len(viols) == 1
        assert viols[0].severity == Severity.MINOR
        assert viols[0].description == "Right margin overflow in BODY_TEXT."
        assert viols[0].detected == "562.93pt"

        left = self._lines([
            (80.0, 523.29, "left violating body line one."),
            (80.0, 523.29, "left violating body line two."),
            (80.0, 523.29, "left violating body line three."),
        ])
        viols = self._run(make_doc([make_paragraph(
            "body left", block_type=BlockType.BODY_TEXT, lines=left)]))
        assert len(viols) == 1
        assert viols[0].severity == Severity.CRITICAL
        assert viols[0].description == "Left margin violation in BODY_TEXT."

        normal = self._lines([
            (108.0, 523.29, "Normal body line one."),
            (108.0, 523.29, "Normal body line two."),
        ])
        assert self._run(make_doc([make_paragraph(
            "body normal", block_type=BlockType.BODY_TEXT, lines=normal)])) == []

    def test_heading_chapter_reference_appendix_unchanged(self):
        for bt, txt in [
            (BlockType.HEADING_1, "1.1 Introduction"),
            (BlockType.CHAPTER_TITLE, "Chapter One"),
            (BlockType.REFERENCE, "Doe, J. (2020). A work. Journal of X, 1(1), 1-10."),
            (BlockType.APPENDIX, "A.1 Raw data tables"),
        ]:
            lines = self._lines([(108.0, 523.29, txt)])
            doc = make_doc([make_paragraph(txt, block_type=bt, lines=lines)])
            assert self._run(doc) == [], f"{bt} produced an unexpected finding"

        overfull = self._lines([
            (108.0, 552.12, "An overlong heading that spills into the margin."),
        ])
        viols = self._run(make_doc([make_paragraph(
            "heading overfull", block_type=BlockType.HEADING_1, lines=overfull)]))
        assert len(viols) == 1
        assert viols[0].description == "Right margin overflow in HEADING_1."
        assert viols[0].detected == "552.12pt"


# ── DPI validation disabled ───────────────────────────────────────────────
class TestImageDpiDisabled:
    def test_image_dpi_validation_disabled(self):
        doc = DocumentModel()
        page = Page(id="pg", page_num=1, bbox=BBox(0, 0, PAGE_W, PAGE_H),
                    width=PAGE_W, height=PAGE_H)
        page.add_child(type("Img", (object,), {
            "id": "i1", "page_num": 1,
            "bbox": BBox(100, 100, 200, 150),
            "dpi_x": 720, "dpi_y": 720,
            "width_px": 400, "height_px": 300,
            "colorspace": "rgb"})())
        doc.pages.append(page)
        assert ImageValidator().validate(doc) == []
