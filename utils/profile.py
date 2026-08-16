"""
utils/profile.py

Builds a per-document "fingerprint" after layout classification.  The profile
is passed to every validator so they compare against the document's own
consistent values (dynamic adaptation) instead of blindly applying absolute
thresholds.  Spec mismatches are still detected later via the hybrid strategy:
the document's dominant value is the comparison baseline, but a systemic
deviation from the configured spec is still reported once at document level.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

from nlp.dom import DocumentModel, BlockType


@dataclass
class DocumentProfile:
    """Document-level, data-derived calibration values."""

    page_count: int = 0
    page_width: float = 595.28
    page_height: float = 841.89

    # Typography (char-weighted dominant values from high-confidence BODY_TEXT)
    body_font_size: float = 12.0
    body_font_family: str = ""
    body_size_tolerance: float = 1.0      # pt band around body size
    monospace_fonts: List[str] = field(default_factory=list)

    # Effective margins (median of paragraph edges) and consistency spread
    left_margin: float = 108.0
    right_margin: float = 72.0
    top_margin: float = 72.0
    bottom_margin: float = 72.0
    margin_tolerance: float = 10.0        # pt; grows with the doc's own spread

    # Structure flags (used to gate applicability of checks)
    has_images: bool = False
    has_tables: bool = False
    has_equations: bool = False
    has_toc: bool = False
    has_captions: bool = False
    chapter_count: int = 0

    # Dominant heading sizes per level (character-weighted, high-confidence)
    heading_l0_size: float = 16.0
    heading_l1_size: float = 14.0
    heading_l2_size: float = 12.0
    heading_l3_size: float = 12.0

    # Indentations used to distinguish quotations / declarations / list items
    body_left_indent: float = 108.0
    indent_tolerance: float = 8.0


def _char_weighted_mode(values: list[tuple[float, int]]) -> float:
    """Return the most common value weighted by character counts."""
    counter: Counter = Counter()
    for value, weight in values:
        if weight > 0:
            counter[round(value, 2)] += weight
    return counter.most_common(1)[0][0] if counter else 0.0


def _robust_spread(values: list[float]) -> float:
    """Median absolute deviation (MAD); falls back to stdev for tiny samples."""
    if len(values) < 2:
        return 0.0
    median = statistics.median(values)
    devs = [abs(v - median) for v in values]
    return statistics.median(devs)


def build_profile(doc: DocumentModel, config=None) -> DocumentProfile:
    """
    Compute the document fingerprint from the classified DOM.
    `config` is optional; when provided, spec values (margins, body size) are
    used as the baseline so the profile inherits user configuration.
    """
    prof = DocumentProfile()
    prof.page_count = len(doc.pages)

    if doc.pages:
        widths = [p.width for p in doc.pages if p.width]
        heights = [p.height for p in doc.pages if p.height]
        if widths:
            prof.page_width = statistics.median(widths)
        if heights:
            prof.page_height = statistics.median(heights)

    if config is not None:
        prof.left_margin = config.margins.left_inches * 72.0
        prof.right_margin = config.margins.right_inches * 72.0
        prof.top_margin = config.margins.top_inches * 72.0
        prof.bottom_margin = config.margins.bottom_inches * 72.0
        prof.body_font_size = config.typography.body_size
        # heading size fallbacks from template
        prof.heading_l0_size = config.headings.level_0.size
        prof.heading_l1_size = config.headings.level_1.size
        prof.heading_l2_size = config.headings.level_2.size
        prof.heading_l3_size = config.headings.level_3.size

    paragraphs = doc.get_all_paragraphs()

    # High-confidence body paragraphs form the calibration basis.
    body = [
        p for p in paragraphs
        if p.block_type == BlockType.BODY_TEXT
        and p.dominant_font_size
        and p.classification_confidence >= 0.5
    ]

    size_weights = [(p.dominant_font_size, len(p.text)) for p in body]
    if size_weights:
        prof.body_font_size = _char_weighted_mode(size_weights)

    family_weights: Counter = Counter()
    for p in body:
        fam = re.sub(r"^[A-Z]{6}\+", "", p.dominant_font or "").lower()
        if fam:
            family_weights[fam] += len(p.text)
    if family_weights:
        prof.body_font_family = family_weights.most_common(1)[0][0]

    mono_fonts = set()
    for p in paragraphs:
        fam = (p.dominant_font or "").lower()
        if any(sub in fam for sub in
               ("mono", "cmtt", "lmtt", "ectt", "txtt", "nimbusmon",
                "courier", "consolas", "inconsolata", "liberationmono")):
            mono_fonts.add(fam)
    prof.monospace_fonts = sorted(mono_fonts)

    # Effective margins from body paragraph edges
    lefts, rights, tops, bottoms = [], [], [], []
    for p in body:
        lefts.append(p.bbox.x0)
        rights.append(p.bbox.x1)
        tops.append(p.bbox.y0)
        bottoms.append(p.bbox.y1)

    if lefts:
        prof.left_margin = statistics.median(lefts)
        prof.body_left_indent = statistics.median(lefts)
        prof.right_margin = max(0.0, prof.page_width - statistics.median(rights))
        prof.top_margin = statistics.median(tops)
        prof.bottom_margin = max(0.0, prof.page_height - statistics.median(bottoms))
        prof.margin_tolerance = max(10.0, 3.0 * _robust_spread(rights + lefts))
        prof.margin_tolerance = min(prof.margin_tolerance, 20.0)
        prof.indent_tolerance = max(8.0, 2.0 * _robust_spread(lefts))

    # Structure flags
    for page in doc.pages:
        if page.get_images():
            prof.has_images = True
        if page.get_tables():
            prof.has_tables = True

    for p in paragraphs:
        if p.block_type == BlockType.EQUATION:
            prof.has_equations = True
        if p.block_type == BlockType.TOC:
            prof.has_toc = True
        if p.block_type == BlockType.CAPTION:
            prof.has_captions = True
        if p.block_type in (BlockType.CHAPTER_TITLE, BlockType.HEADING_1):
            prof.chapter_count += 1

    # ---- Dominant heading sizes (profile-driven) ----
    # Collect high-confidence headings per level, excluding special sections
    special_sections = {BlockType.BIBLIOGRAPHY, BlockType.REFERENCE, BlockType.APPENDIX}
    heading_levels = {
        BlockType.CHAPTER_TITLE: 'heading_l0_size',
        BlockType.HEADING_1: 'heading_l1_size',
        BlockType.HEADING_2: 'heading_l2_size',
        BlockType.HEADING_3: 'heading_l3_size',
    }
    for lvl_type, attr_name in heading_levels.items():
        samples = [
            (p.dominant_font_size, len(p.text))
            for p in paragraphs
            if p.block_type == lvl_type
            and p.dominant_font_size
            and p.classification_confidence >= 0.5
            and p.block_type not in special_sections
        ]
        if samples:
            setattr(prof, attr_name, _char_weighted_mode(samples))

    return prof
