"""
Structured violation / finding model used across all checks.
"""
from dataclasses import dataclass, field
from typing import Optional, List
from utils.constants import Severity


@dataclass
class Violation:
    """Represents a single format violation found in the PDF with full explainability."""
    category:    str                    # Category constant (e.g. Category.FONT)
    severity:    str                    # Severity constant (CRITICAL / MAJOR / MINOR / WARNING / SUGGESTION / INFO)
    page:        int                    # 1-based page number  (-1 = document-level)
    description: str                    # Human-readable description (Rule)
    detail:      Optional[str] = None   # Expected vs Detected (e.g. Expected <= 523pt, found 534pt)
    
    # Explainability Fields
    expected:    Optional[str] = None
    detected:    Optional[str] = None
    confidence:  float = 0.0
    signals:     List[str] = field(default_factory=list)
    reason:      Optional[str] = None
    suggested_fix: Optional[str] = None
    
    location:    Optional[str] = None   # Section/heading name if known
    bbox:        Optional[tuple[float, float, float, float]] = None # (x0, y0, x1, y1) bounding box

    def to_dict(self) -> dict:
        return {
            "Category":    self.category,
            "Severity":    self.severity,
            "Page":        self.page if self.page > 0 else "Doc",
            "Rule":        self.description,
            "Expected":    self.expected or "",
            "Detected":    self.detected or "",
            "Confidence":  round(self.confidence, 4) if self.confidence else 0.0,
            "Reason":      self.reason or "",
            "SuggestedFix": self.suggested_fix or "",
            "Detail":      self.detail or "",
            "Location":    self.location or "",
        }

    def __str__(self) -> str:
        page_str = f"p.{self.page}" if self.page > 0 else "doc"
        loc = f" [{self.location}]" if self.location else ""
        detail = f" → {self.detail}" if self.detail else ""
        return f"[{self.severity}] ({page_str}){loc} {self.category}: {self.description}{detail}"


class ViolationCollector:
    """Aggregates violations from all checks and provides summary statistics."""

    def __init__(self):
        self._violations: list[Violation] = []

    def add(self, violation: Violation):
        self._violations.append(violation)

    def add_all(self, violations: list[Violation]):
        self._violations.extend(violations)

    @property
    def all(self) -> list[Violation]:
        return list(self._violations)

    @property
    def critical(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.CRITICAL]

    @property
    def major(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.MAJOR]
        
    @property
    def minor(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.MINOR]
        
    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.WARNING]
        
    @property
    def suggestions(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.SUGGESTION]

    @property
    def info(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.INFO]

    def by_category(self) -> dict[str, list[Violation]]:
        result: dict[str, list[Violation]] = {}
        for v in self._violations:
            result.setdefault(v.category, []).append(v)
        return result

    def by_page(self) -> dict[int, list[Violation]]:
        """Group violations by page number for efficient per-page processing."""
        result: dict[int, list[Violation]] = {}
        for v in self._violations:
            result.setdefault(v.page, []).append(v)
        return result

    def summary(self) -> dict:
        return {
            "total":       len(self._violations),
            "critical":    len(self.critical),
            "major":       len(self.major),
            "minor":       len(self.minor),
            "warnings":    len(self.warnings),
            "suggestions": len(self.suggestions),
            "info":        len(self.info),
        }
