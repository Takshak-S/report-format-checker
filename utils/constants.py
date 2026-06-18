"""
Format specification constants derived from Standardization_Template_25_05_2206.docx
All measurements in PDF points (1 pt = 1/72 inch) unless noted.
"""

# ── Page Layout ────────────────────────────────────────────────────────────────
PAGE_WIDTH_PT  = 595.28   # A4 width  (210 mm)
PAGE_HEIGHT_PT = 841.89   # A4 height (297 mm)
PAGE_SIZE_TOLERANCE_PT = 5.0   # ±5 pt tolerance for page size check

MARGIN_LEFT_PT   = 108.0  # 1.5 inch  (binding margin)
MARGIN_RIGHT_PT  = 72.0   # 1.0 inch
MARGIN_TOP_PT    = 72.0   # 1.0 inch
MARGIN_BOTTOM_PT = 72.0   # 1.0 inch
MARGIN_TOLERANCE_PT = 6.0  # ±6 pt tolerance (~2 mm)

# ── Fonts ──────────────────────────────────────────────────────────────────────
REQUIRED_FONT_FAMILY = "TimesNewRoman"   # canonical name used for matching
FONT_ALIASES = [
    "timesnewroman", "times new roman", "times-new-roman",
    "timesnewromanpsmt", "timesnewroman,", "times"
]

FONT_SIZE_BODY       = 12.0
FONT_SIZE_HEADING_L1 = 14.0
FONT_SIZE_HEADING_L0 = 16.0
FONT_SIZE_CAPTION    = 10.0
FONT_SIZE_TOLERANCE  = 0.8   # ±0.8 pt tolerance

# ── Spacing & Alignment ────────────────────────────────────────────────────────
LINE_SPACING_FACTOR  = 1.5   # 1.5× line spacing
LINE_SPACING_TOLERANCE = 0.25
JUSTIFICATION_TOLERANCE_PT = 8.0  # max allowed right-edge variance for justified text

# ── Image Quality ──────────────────────────────────────────────────────────────
MIN_IMAGE_DPI = 600

# ── Heading Patterns ──────────────────────────────────────────────────────────
import re

# Level 0: UPPERCASE chapter title  e.g. "INTRODUCTION"
HEADING_L0_PATTERN = re.compile(r"^[A-Z][A-Z\s\-&/]+$")

# Level 1: "1.1 SOME HEADING"  (decimal + uppercase words)
HEADING_L1_PATTERN = re.compile(r"^\d+\.\d+\s+[A-Z][A-Z\s\-&/:]+$")

# Level 2: "1.1.1 Some Heading"  (two decimals + Title Case)
HEADING_L2_PATTERN = re.compile(r"^\d+\.\d+\.\d+\s+[A-Z][A-Za-z\s\-&/:]+$")

# Caption patterns
FIGURE_CAPTION_PATTERN = re.compile(
    r"^Figure\s+\d+\.\d+\s*[:–\-]", re.IGNORECASE
)
TABLE_CAPTION_PATTERN = re.compile(
    r"^Table\s+\d+\.\d+\s*[:–\-]", re.IGNORECASE
)

# Equation pattern: "(2.1)" at end of line
EQUATION_PATTERN = re.compile(r"\(\d+\.\d+\)\s*$")

# In-text citation: [Author, Year] or (Author, Year)
INTEXT_CITATION_PATTERN = re.compile(
    r"[\[\(][A-Z][a-zA-Z\s\-]+,?\s*\d{4}[a-z]?\s*[\]\)]"
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
