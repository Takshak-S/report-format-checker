"""
checks/grammar_checks.py

Checks:
  1. Grammar and spelling using LanguageTool
  2. Custom CS/tech domain dictionary to suppress false positives
  3. Scans body text pages only (skips bibliography, cover pages)
"""
from __future__ import annotations

import re
from ingestion.pdf_loader import ParsedDocument
from utils.constants import Severity, Category
from utils.error_model import Violation

try:
    import language_tool_python
    LT_AVAILABLE = True
except ImportError:
    LT_AVAILABLE = False


# ── CS / Technical domain dictionary ─────────────────────────────────────────
# Words LanguageTool may flag as errors but are valid CS terms

CS_DICTIONARY = {
    # Algorithms & Data Structures
    "autoencoder", "autoencoders", "automl", "backpropagation",
    "bigram", "bigrams", "bitwise", "blockchain", "brute-force",
    "bytecode", "cacheable", "checkpointing", "codebase", "config",
    "configs", "containerization", "containerized", "convolutional",
    "coroutine", "coroutines", "crossentropy", "cuda", "dataloader",
    "dataset", "datasets", "datatype", "datatypes", "deallocate",
    "deallocation", "debugger", "dequeue", "deserialize", "deserialization",
    "deterministic", "devops", "dockerfile", "dropout", "embeddings",
    "encoder", "decoders", "endian", "epochs", "feedforward",
    "finetune", "finetuned", "finetuning", "frontend", "backend",
    "fullstack", "fuzzing", "generative", "geospatial", "gpu",
    "gradients", "groundtruth", "hardcode", "hardcoded", "heatmap",
    "hyperparameter", "hyperparameters", "idempotent", "inferencing",
    "instantiate", "instantiation", "json", "jupyter", "keras",
    "keyvalue", "latency", "leaderboard", "lookup", "lstm",
    "makefile", "middleware", "minibatch", "minibatches", "mnist",
    "multiclass", "multilabel", "multimodal", "multithreading",
    "namespace", "numpy", "ontology", "overfit", "overfitting",
    "pandas", "parallelism", "parameterize", "parser", "parsers",
    "payload", "pipeline", "pipelines", "pytorch", "regex",
    "relu", "repo", "repos", "repository", "rollback", "runtime",
    "scalability", "scikit", "sklearn", "softmax", "sql", "nosql",
    "sqlite", "submodule", "subprocess", "tensorflow", "tokenize",
    "tokenizer", "tokenizers", "tokenization", "tooltip", "trainable",
    "tuple", "tuples", "underfit", "underfitting", "unidirectional",
    "unpickle", "upsampling", "variational", "vectorize", "vectorized",
    "webhook", "websocket", "workflow", "yaml", "api", "apis",
    "cpu", "ram", "ssd", "hdd", "url", "urls", "http", "https",
    "tcp", "udp", "ip", "ipv4", "ipv6", "dns", "dhcp", "ssh",
    "ftp", "smtp", "imap", "pop3", "ide", "cli", "gui", "sdk",
    "nlp", "cv", "ml", "ai", "dl", "rl", "gan", "vae", "cnn",
    "rnn", "gru", "bert", "gpt", "llm", "llms", "transformer",
    "transformers", "resnet", "vgg", "alexnet", "yolo",
    # Institutions / common abbreviations
    "github", "gitlab", "bitbucket", "stackoverflow", "colab",
    "kaggle", "huggingface", "openai", "anthropic",
}


def _build_allowlist_pattern() -> re.Pattern:
    """Compile a pattern to quickly check if a flagged word is in CS dict."""
    escaped = [re.escape(w) for w in CS_DICTIONARY]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


_ALLOWLIST_PATTERN = _build_allowlist_pattern()


def _is_cs_term(text: str) -> bool:
    return bool(_ALLOWLIST_PATTERN.search(text))


# ── Grammar check ─────────────────────────────────────────────────────────────

def run_grammar_checks(doc: ParsedDocument) -> list[Violation]:
    violations = []

    if not LT_AVAILABLE:
        violations.append(Violation(
            category=Category.GRAMMAR,
            severity=Severity.INFO,
            page=-1,
            description="language-tool-python not available — grammar check skipped",
            detail="Install with: pip install language-tool-python",
        ))
        return violations

    # Initialise LanguageTool (downloads server jar on first run)
    try:
        tool = language_tool_python.LanguageTool("en-US")
    except Exception as e:
        violations.append(Violation(
            category=Category.GRAMMAR,
            severity=Severity.INFO,
            page=-1,
            description="LanguageTool initialisation failed — grammar check skipped",
            detail=str(e),
        ))
        return violations

    # Rules to ignore (noise-heavy or CS-specific)
    IGNORED_RULES = {
        "WHITESPACE_RULE",
        "EN_QUOTES",
        "CONSECUTIVE_SPACES",
        "UNPAIRED_BRACKETS",
        "COMMA_PARENTHESIS_WHITESPACE",
        "EN_UNPAIRED_BRACKETS",
    }

    # Detect bibliography start page to skip
    bib_start = doc.page_count
    for page_idx, text in enumerate(doc.raw_text_by_page):
        if re.search(r"^(references|bibliography)\s*$", text, re.IGNORECASE | re.MULTILINE):
            bib_start = page_idx + 1
            break

    # Check pages in chunks (skip first 3 cover/ToC pages and bib)
    max_grammar_pages = 30   # cap to avoid very long runtime
    pages_to_check = range(4, min(bib_start, 4 + max_grammar_pages))

    for page_idx in pages_to_check:
        text = doc.raw_text_by_page[page_idx - 1] if page_idx <= len(doc.raw_text_by_page) else ""
        if not text.strip():
            continue

        try:
            matches = tool.check(text)
        except Exception:
            continue

        for match in matches:
            if match.ruleId in IGNORED_RULES:
                continue

            flagged_text = text[match.offset: match.offset + match.errorLength]

            # Skip if the flagged word is a CS term
            if _is_cs_term(flagged_text):
                continue

            # Skip pure numbers, single chars, and very short tokens
            if re.fullmatch(r"[\d\W]+", flagged_text) or len(flagged_text) < 3:
                continue

            severity = Severity.WARNING if "spell" in match.ruleId.lower() else Severity.INFO
            violations.append(Violation(
                category=Category.GRAMMAR,
                severity=severity,
                page=page_idx,
                description=match.message,
                detail=f"'{flagged_text}' — suggested: {match.replacements[:3]}",
            ))

    tool.close()
    return violations
