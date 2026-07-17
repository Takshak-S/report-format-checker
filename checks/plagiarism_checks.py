"""
checks/plagiarism_checks.py

Checks uploaded report text against a local corpus of existing works.
Place reference PDFs or .txt files in the project corpus/ directory.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from ingestion.pdf_loader import ParsedDocument
from utils.constants import (
    PLAGIARISM_SIMILARITY_THRESHOLD,
    PLAGIARISM_MIN_SENTENCE_LEN,
    PLAGIARISM_NGRAM_SIZE,
    Severity, Category,
)
from utils.error_model import Violation

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= PLAGIARISM_MIN_SENTENCE_LEN]


def _ngrams(text: str, n: int) -> set[str]:
    normalized = _normalize(text)
    if len(normalized) < n:
        return set()
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def _load_corpus_texts() -> dict[str, str]:
    """Load all .txt and .pdf files from corpus/ directory."""
    texts: dict[str, str] = {}

    if not CORPUS_DIR.is_dir():
        return texts

    for path in sorted(CORPUS_DIR.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix.lower() == ".txt":
            try:
                texts[path.name] = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
        elif path.suffix.lower() == ".pdf":
            try:
                from ingestion.pdf_loader import load_pdf
                doc = load_pdf(path)
                texts[path.name] = "\n".join(doc.raw_text_by_page)
            except Exception:
                continue

    return texts


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def check_plagiarism(doc: ParsedDocument) -> list[Violation]:
    violations = []
    corpus = _load_corpus_texts()

    if not corpus:
        violations.append(Violation(
            category=Category.PLAGIARISM,
            severity=Severity.INFO,
            page=-1,
            description="Plagiarism check skipped — no corpus files found",
            detail=f"Add .txt or .pdf reference works to {CORPUS_DIR} to enable comparison",
        ))
        return violations

    doc_text = "\n".join(doc.raw_text_by_page)
    doc_sentences = _split_sentences(doc_text)
    doc_ngrams = _ngrams(doc_text, PLAGIARISM_NGRAM_SIZE)

    matches_found = 0
    seen_matches: set[str] = set()
    max_sentence_matches = 20

    for source_name, source_text in corpus.items():
        source_sentences = _split_sentences(source_text)
        source_ngrams = _ngrams(source_text, PLAGIARISM_NGRAM_SIZE)

        if doc_ngrams and source_ngrams:
            overlap = len(doc_ngrams & source_ngrams)
            union = len(doc_ngrams | source_ngrams)
            jaccard = overlap / union if union else 0.0
            if jaccard >= 0.15:
                violations.append(Violation(
                    category=Category.PLAGIARISM,
                    severity=Severity.WARNING,
                    page=-1,
                    description=f"Significant text overlap with existing work: {source_name}",
                    detail=f"N-gram similarity index: {jaccard:.1%} (threshold 15%)",
                ))
                matches_found += 1

        for doc_sent in doc_sentences:
            best_ratio = 0.0
            best_match = ""
            for src_sent in source_sentences:
                ratio = _similarity(doc_sent, src_sent)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = src_sent

            if best_ratio >= PLAGIARISM_SIMILARITY_THRESHOLD:
                match_key = f"{source_name}:{doc_sent[:60]}"
                if match_key in seen_matches or matches_found >= max_sentence_matches:
                    continue
                seen_matches.add(match_key)

                page_hint = -1
                for page_idx, page_text in enumerate(doc.raw_text_by_page):
                    if doc_sent[:40] in page_text:
                        page_hint = page_idx + 1
                        break

                violations.append(Violation(
                    category=Category.PLAGIARISM,
                    severity=Severity.CRITICAL if best_ratio >= 0.85 else Severity.WARNING,
                    page=page_hint,
                    description=f"Possible plagiarism match with '{source_name}'",
                    detail=(
                        f"Similarity {best_ratio:.0%}: \"{doc_sent[:80]}...\" "
                        f"↔ \"{best_match[:80]}...\""
                    ),
                ))
                matches_found += 1

    if matches_found == 0:
        violations.append(Violation(
            category=Category.PLAGIARISM,
            severity=Severity.INFO,
            page=-1,
            description="No plagiarism detected against corpus",
            detail=f"Compared against {len(corpus)} reference work(s) in corpus/",
        ))

    return violations


def run_plagiarism_checks(doc: ParsedDocument) -> list[Violation]:
    return check_plagiarism(doc)
