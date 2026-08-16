"""
checks/image_validator.py

ImageValidator validates images in the PDF against the configured template.

Currently disabled — image validation is handled by image_checks.py (graph axis OCR).
"""
from __future__ import annotations

from typing import List

from nlp.dom import DocumentModel
from utils.error_model import Violation
from checks.validators import ValidationRule


class ImageValidator(ValidationRule):
    def validate(self, doc: DocumentModel) -> List[Violation]:
        # Image validation (DPI, margins, references) disabled per user request.
        # Graph axis OCR check runs via checks/image_checks.py
        return []