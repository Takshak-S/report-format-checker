"""
Structured violation / finding model used across all checks.
"""
from dataclasses import dataclass, field
from typing import Optional
from utils.constants import Severity


@dataclass
class Violation:
    """Represents a single format violation found in the PDF."""
    category:    str                    # Category constant (e.g. Category.FONT)
    severity:    str                    # Severity constant (ERROR / WARNING / INFO)
    page:        int                    # 1-based page number  (-1 = document-level)
    description: str                    # Human-readable description
    detail:      Optional[str] = None   # Extra context (e.g. found value vs expected)
    location:    Optional[str] = None   # Section/heading name if known

    def to_dict(self) -> dict:
        return {
            "Category":    self.category,
            "Severity":    self.severity,
            "Page":        self.page if self.page > 0 else "Doc",
            "Description": self.description,
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
    def errors(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.WARNING]

    @property
    def info(self) -> list[Violation]:
        return [v for v in self._violations if v.severity == Severity.INFO]

    def by_category(self) -> dict[str, list[Violation]]:
        result: dict[str, list[Violation]] = {}
        for v in self._violations:
            result.setdefault(v.category, []).append(v)
        return result

    def summary(self) -> dict:
        return {
            "total":    len(self._violations),
            "errors":   len(self.errors),
            "warnings": len(self.warnings),
            "info":     len(self.info),
        }
