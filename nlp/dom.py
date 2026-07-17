from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Any
from enum import Enum

class BlockType(Enum):
    BODY_TEXT = "BODY_TEXT"
    CHAPTER_TITLE = "CHAPTER_TITLE"
    HEADING_1 = "HEADING_1"
    HEADING_2 = "HEADING_2"
    HEADING_3 = "HEADING_3"
    CAPTION = "CAPTION"
    TABLE = "TABLE"
    FIGURE = "FIGURE"
    EQUATION = "EQUATION"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    TOC = "TOC"
    REFERENCE = "REFERENCE"
    CODE_BLOCK = "CODE_BLOCK"
    LIST = "LIST"
    APPENDIX = "APPENDIX"
    UNKNOWN = "UNKNOWN"

@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float
    
    def width(self) -> float:
        return self.x1 - self.x0
    
    def height(self) -> float:
        return self.y1 - self.y0
    
    def intersects(self, other: 'BBox') -> bool:
        return not (self.x1 < other.x0 or self.x0 > other.x1 or self.y1 < other.y0 or self.y0 > other.y1)
    
    def merge(self, other: 'BBox') -> 'BBox':
        return BBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1)
        )

@dataclass
class DOMNode:
    id: str
    page_num: int
    bbox: BBox
    parent: Optional['DOMNode'] = None
    children: List['DOMNode'] = field(default_factory=list)
    
    def add_child(self, child: 'DOMNode'):
        child.parent = self
        self.children.append(child)

@dataclass
class Word(DOMNode):
    text: str = ""
    font: str = ""
    font_size: float = 0.0
    bold: bool = False
    italic: bool = False

@dataclass
class Line(DOMNode):
    text: str = ""
    font: str = ""
    font_size: float = 0.0
    bold: bool = False
    italic: bool = False
    alignment: str = "" # "left", "center", "right", "justified"
    line_spacing: float = 0.0
    
    def get_words(self) -> List[Word]:
        return [c for c in self.children if isinstance(c, Word)]

@dataclass
class Paragraph(DOMNode):
    text: str = ""
    block_type: BlockType = BlockType.UNKNOWN
    classification_confidence: float = 0.0
    classification_reasons: List[str] = field(default_factory=list)
    alternative_candidates: dict[BlockType, float] = field(default_factory=dict)
    
    # Pre-computed layout info for margin and font checks
    dominant_font: str = ""
    dominant_font_size: float = 0.0
    dominant_bold: bool = False
    dominant_italic: bool = False
    alignment: str = ""
    
    def get_lines(self) -> List[Line]:
        return [c for c in self.children if isinstance(c, Line)]

@dataclass
class ImageNode(DOMNode):
    dpi_x: int = 0
    dpi_y: int = 0
    width_px: int = 0
    height_px: int = 0
    colorspace: str = ""

@dataclass
class TableNode(DOMNode):
    rows: List[List[Optional[str]]] = field(default_factory=list)

@dataclass
class Page(DOMNode):
    width: float = 0.0
    height: float = 0.0
    
    def get_paragraphs(self) -> List[Paragraph]:
        return [c for c in self.children if isinstance(c, Paragraph)]
    
    def get_images(self) -> List[ImageNode]:
        return [c for c in self.children if isinstance(c, ImageNode)]
        
    def get_tables(self) -> List[TableNode]:
        return [c for c in self.children if isinstance(c, TableNode)]

@dataclass
class DocumentModel:
    pages: List[Page] = field(default_factory=list)
    raw_text: str = ""
    
    def get_all_paragraphs(self) -> List[Paragraph]:
        paragraphs = []
        for p in self.pages:
            paragraphs.extend(p.get_paragraphs())
        return paragraphs
