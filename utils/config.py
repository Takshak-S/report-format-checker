import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class PageConfig:
    format: str = "A4"

@dataclass
class MarginsConfig:
    left_inches: float = 1.5
    right_inches: float = 1.0
    top_inches: float = 1.0
    bottom_inches: float = 1.0

@dataclass
class TypographyConfig:
    allowed_fonts: List[str] = field(default_factory=lambda: ["Times New Roman", "TimesNewRomanPSMT", "Nimbus Roman", "TeX Gyre Termes", "nimbusromno9l-regu"])
    body_size: float = 12.0
    caption_size: float = 10.0

@dataclass
class ParagraphConfig:
    line_spacing: float = 1.5
    alignment: str = "justified"

@dataclass
class PageNumberConfig:
    alignment: str = "center"
    position: str = "bottom"

@dataclass
class HeadingLevelConfig:
    size: float
    name: str = ""
    case: str = ""
    new_page: bool = False
    bold: bool = False
    italic: bool = False
    numbering: str = ""

@dataclass
class HeadingsConfig:
    level_0: HeadingLevelConfig
    level_1: HeadingLevelConfig
    level_2: HeadingLevelConfig
    level_3: HeadingLevelConfig

@dataclass
class FiguresConfig:
    caption_position: str = "below"
    numbering: str = "chapter_wise"

@dataclass
class TablesConfig:
    caption_position: str = "above"
    numbering: str = "chapter_wise"

@dataclass
class ImagesConfig:
    min_dpi: int = 600

@dataclass
class EquationsConfig:
    numbering: str = "chapter_wise"

@dataclass
class BibliographyConfig:
    style: str = "APA"

@dataclass
class GrammarConfig:
    engine: str = "LanguageTool"
    dictionary: str = "CS"

@dataclass
class TemplateConfig:
    page: PageConfig = field(default_factory=PageConfig)
    margins: MarginsConfig = field(default_factory=MarginsConfig)
    typography: TypographyConfig = field(default_factory=TypographyConfig)
    paragraph: ParagraphConfig = field(default_factory=ParagraphConfig)
    page_number: PageNumberConfig = field(default_factory=PageNumberConfig)
    headings: HeadingsConfig = None
    figures: FiguresConfig = field(default_factory=FiguresConfig)
    tables: TablesConfig = field(default_factory=TablesConfig)
    images: ImagesConfig = field(default_factory=ImagesConfig)
    equations: EquationsConfig = field(default_factory=EquationsConfig)
    bibliography: BibliographyConfig = field(default_factory=BibliographyConfig)
    grammar: GrammarConfig = field(default_factory=GrammarConfig)

def _parse_heading_level(data: Dict[str, Any]) -> HeadingLevelConfig:
    return HeadingLevelConfig(
        size=data.get("size", 12.0),
        name=data.get("name", ""),
        case=data.get("case", ""),
        new_page=data.get("new_page", False),
        bold=data.get("bold", False),
        italic=data.get("italic", False),
        numbering=data.get("numbering", "")
    )

def load_config(config_path: str | Path = None) -> TemplateConfig:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "vit_template.json"
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    headings_data = data.get("headings", {})
    
    headings_config = HeadingsConfig(
        level_0=_parse_heading_level(headings_data.get("level_0", {})),
        level_1=_parse_heading_level(headings_data.get("level_1", {})),
        level_2=_parse_heading_level(headings_data.get("level_2", {})),
        level_3=_parse_heading_level(headings_data.get("level_3", {}))
    )
    
    return TemplateConfig(
        page=PageConfig(**data.get("page", {})),
        margins=MarginsConfig(**data.get("margins", {})),
        typography=TypographyConfig(**data.get("typography", {})),
        paragraph=ParagraphConfig(**data.get("paragraph", {})),
        page_number=PageNumberConfig(**data.get("page_number", {})),
        headings=headings_config,
        figures=FiguresConfig(**data.get("figures", {})),
        tables=TablesConfig(**data.get("tables", {})),
        images=ImagesConfig(**data.get("images", {})),
        equations=EquationsConfig(**data.get("equations", {})),
        bibliography=BibliographyConfig(**data.get("bibliography", {})),
        grammar=GrammarConfig(**data.get("grammar", {}))
    )

# Singleton global configuration instance
_GLOBAL_CONFIG = None

def get_config() -> TemplateConfig:
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None:
        _GLOBAL_CONFIG = load_config()
    return _GLOBAL_CONFIG
