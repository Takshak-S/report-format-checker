from abc import ABC, abstractmethod
from typing import List, Optional
from nlp.dom import DocumentModel
from utils.error_model import Violation, ViolationCollector
from utils.config import get_config
from utils.profile import DocumentProfile, build_profile

class ValidationRule(ABC):
    def __init__(self):
        self.config = get_config()
        self.profile: Optional[DocumentProfile] = None

    def set_profile(self, profile: DocumentProfile):
        """Attach the per-document calibrated profile before validation."""
        self.profile = profile

    @abstractmethod
    def validate(self, doc: DocumentModel) -> List[Violation]:
        """
        Validates the document and returns a list of Violations.
        """
        pass
