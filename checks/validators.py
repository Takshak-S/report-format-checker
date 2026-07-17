from abc import ABC, abstractmethod
from typing import List
from nlp.dom import DocumentModel
from utils.error_model import Violation, ViolationCollector
from utils.config import get_config

class ValidationRule(ABC):
    def __init__(self):
        self.config = get_config()
        
    @abstractmethod
    def validate(self, doc: DocumentModel) -> List[Violation]:
        """
        Validates the document and returns a list of Violations.
        """
        pass
