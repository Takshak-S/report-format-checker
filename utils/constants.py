"""
Format specification constants derived from Standardization_Template_25_05_2206.docx
All measurements in PDF points (1 pt = 1/72 inch) unless noted.
"""

import re

# ── Page Layout ────────────────────────────────────────────────────────────────
PAGE_WIDTH_PT  = 595.28   # A4 width  (210 mm)
PAGE_HEIGHT_PT = 841.89   # A4 height (297 mm)
PAGE_SIZE_TOLERANCE_PT = 5.0   # ±5 pt tolerance for page size check

MARGIN_LEFT_PT   = 108.0  # 1.5 inch  (binding margin)
MARGIN_RIGHT_PT  = 72.0   # 1.0 inch
MARGIN_TOP_PT    = 72.0   # 1.0 inch
MARGIN_BOTTOM_PT = 72.0   # 1.0 inch
MARGIN_TOLERANCE_PT = 8.0  # ±8 pt tolerance (~2.8 mm) — updated from 6 pt

# ── Fonts ──────────────────────────────────────────────────────────────────────
REQUIRED_FONT_FAMILY = "TimesNewRoman"   # canonical name used for matching
FONT_ALIASES = [
    "timesnewroman", "times new roman", "times-new-roman",
    "timesnewromanpsmt", "timesnewromanps", "timesnewromanps-",
    "timesnewroman,", "times-roman", "times",
    "timesnewromanps-boldmt", "timesnewromanps-italicmt",
    "timesnewromanps-bolditalicmt",
    # Nimbus Roman No. 9L — open-source TNR equivalent (common in LaTeX PDFs)
    "nimbusromno9l", "nimbusromno9l-regu", "nimbusromno9l-medi",
    "nimbusromno9l-regual", "nimbusromno9l-mediital",
    "nimbusromno9l-bold", "nimbusromno9l-boldital",
    # Other common TNR equivalents
    "nimbus roman", "nimbus roman no9 l",
    "freeserif", "liberation serif", "liberationserif",
    "tinos",  # Google's TNR metric-compatible font
]

FONT_SIZE_BODY       = 12.0
FONT_SIZE_HEADING_L1 = 14.0
FONT_SIZE_HEADING_L0 = 16.0
FONT_SIZE_CAPTION    = 10.0
FONT_SIZE_TOLERANCE  = 3.5   # ±3.5 pt tolerance — handles real-world PDF rendering variance

# ── Spacing & Alignment ────────────────────────────────────────────────────────
LINE_SPACING_FACTOR  = 1.5   # 1.5× line spacing
LINE_SPACING_TOLERANCE = 0.5  # increased from 0.3 to reduce false positives
JUSTIFICATION_TOLERANCE_PT = 8.0  # max allowed right-edge variance — updated from 8.0

# ── Image Quality ──────────────────────────────────────────────────────────────
MIN_IMAGE_DPI = 600

# ── Header / Footer exclusion zones ───────────────────────────────────────────
HEADER_ZONE_PT = 72.0   # content within this distance from top is header/footer
FOOTER_ZONE_PT = 72.0   # content within this distance from bottom is header/footer

# ── Heading Patterns ──────────────────────────────────────────────────────────

# Level 0: UPPERCASE chapter title  e.g. "INTRODUCTION", "CHAPTER 1 INTRODUCTION", "CHAPTER1"
HEADING_L0_PATTERN = re.compile(r"^(?:CHAPTER\s*\d+[\s.:–-]*)?[A-Z][A-Z\s\-&/,\d]+$")

# Level 1: "1.1 SOME HEADING"  (decimal + uppercase words — allows colons, commas, parens)
HEADING_L1_PATTERN = re.compile(r"^\d+\.\d+\s+[A-Z][A-Z\s\-&/:,()]+$")

# Level 2: "1.1.1 Some Heading"  (two decimals + Title Case — allows mixed case)
HEADING_L2_PATTERN = re.compile(r"^\d+\.\d+\.\d+\s+[A-Z][A-Za-z\s\-&/:,()]+$")

# Caption patterns — support :, –, -, . separators
FIGURE_CAPTION_PATTERN = re.compile(
    r"^(?:Figure|Fig\.?)\s+\d+\.\d+\s*[:–\-.]\s*", re.IGNORECASE
)
TABLE_CAPTION_PATTERN = re.compile(
    r"^(?:Table|Tab\.?)\s+\d+\.\d+\s*[:–\-.]\s*", re.IGNORECASE
)

# Equation pattern: "(2.1)" at end of line or preceded by whitespace
EQUATION_PATTERN = re.compile(r"\(\d+\.\d+\)\s*$")

# Broader equation detection (also matches mid-line numbered equations)
EQUATION_BROAD_PATTERN = re.compile(r"\s\(\d+\.\d+\)")

# In-text citation patterns
# APA author-year: [Author, Year] or (Author, Year) or (Author et al., Year)
INTEXT_CITATION_PATTERN = re.compile(
    r"(?:[A-Z][a-zA-Z\s\-]+(?:(?:,\s*|\s+and\s+|\s+&\s+)[A-Z][a-zA-Z\s\-]+|\s+et\s+al\.?)?,?\s*[\[(]\d{4}[a-z]?[\])]"
    r"|[\[(][A-Z][a-zA-Z\s\-]+(?:(?:,\s*|\s+and\s+|\s+&\s+)[A-Z][a-zA-Z\s\-]+|\s+et\s+al\.?)?,?\s*\d{4}[a-z]?[\])])"
)

# Numeric citation: [1], [2], [1-3], [1,2,3], [1, 2]
NUMERIC_CITATION_PATTERN = re.compile(
    r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]"
)

# ── Mandatory Chapters ─────────────────────────────────────────────────────────
MANDATORY_CHAPTERS = [
    "Introduction",
    "Project Description and Goals",
    "Technical Specification",
    "System Design",
    "Methodology and Testing",
    "Project Implementation",
    "Results and Discussion",
    "Conclusion and Future Enhancements",
]

# ── Severity Levels ────────────────────────────────────────────────────────────
class Severity:
    ERROR   = "ERROR"    # Must fix — structural/critical
    WARNING = "WARNING"  # Should fix — style/formatting
    INFO    = "INFO"     # FYI — minor suggestion

# ── Check Category Labels ──────────────────────────────────────────────────────
class Category:
    PAGE_LAYOUT    = "Page Layout"
    FONT           = "Font"
    SPACING        = "Spacing"
    ALIGNMENT      = "Alignment"
    HEADINGS       = "Headings"
    CAPTIONS       = "Captions"
    IMAGES         = "Images"
    EQUATIONS      = "Equations"
    CHAPTERS       = "Chapter Structure"
    CITATIONS      = "Citations & Bibliography"
    GRAMMAR        = "Grammar & Spelling"
    GRAPHS         = "Graphs"
    TOC            = "Table of Contents"
    SUBTOPICS      = "Subtopic Structure"
    IMAGE_DIMS     = "Image Dimensions"
    RESEARCH       = "Research Growth"
    PLAGIARISM     = "Plagiarism"
    OVERALL_SCORE  = "Overall Score"

# ── Table of Contents ──────────────────────────────────────────────────────────
TOC_HEADER_PATTERN = re.compile(
    r"^(table\s+of\s+contents|contents)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
TOC_ENTRY_PATTERN = re.compile(
    r"^(.+?)\s+(?:\.{2,}\s*|\s+)(?:\d+|[ivxlcdmIVXLCDM]+)\s*$"
)

# ── Subtopic structure ─────────────────────────────────────────────────────────
MIN_LINES_FOR_SUBTOPICS = 40          # body lines between L1 headings before subtopics expected
MIN_WORDS_FOR_SUBTOPICS = 500

# ── Image dimensions ───────────────────────────────────────────────────────────
MIN_IMAGE_RENDERED_PT = 72.0          # min 1 inch rendered width/height for significant images
MAX_IMAGE_PAGE_RATIO  = 0.85          # image should not exceed 85% of page width/height
MIN_IMAGE_PIXELS      = 200           # min pixel dimension for non-decorative images

# ── Plagiarism ─────────────────────────────────────────────────────────────────
PLAGIARISM_SIMILARITY_THRESHOLD = 0.72   # SequenceMatcher ratio for sentence match
PLAGIARISM_MIN_SENTENCE_LEN     = 40       # ignore very short sentences
PLAGIARISM_NGRAM_SIZE           = 8        # character n-gram size for fingerprinting
