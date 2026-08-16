"""
utils/fonts.py

Shared font helpers used by the layout classifier and the validators:
  - is_code_font()      : detect monospaced / typewriter font families
  - looks_like_code()   : content-based detection of code listings
  - normalize_font_name(): lowercase, strip PDF subset prefix and punctuation
"""
from __future__ import annotations

import re

# Monospaced / typewriter font substrings.  Covers LaTeX classics (cmtt,
# lmtt, ectt, txtt, Nimbus Mono L = "nimbusmonl") plus common system fonts.
MONO_SUBSTRINGS = [
    "nimbusmon",       # Nimbus Mono L  (LaTeX default mono)
    "cmtt", "lmtt", "ectt", "txtt", "ntxtt", "initex",
    "courier", "cour", "consolas", "menlo", "monaco",
    "liberationmono", "dejavusansmono", "dejavumono",
    "inconsolata", "sourcecodepro", "juliamono", "hack",
    "jetbrainsmono", "cascadia", "ubuntumono", "robotomono",
    "notosansmono", "sfmono", "fira code", "firacode", "beramono",
    "zfcm", "zi4", "zrtt", "texgyrecursor", "andale mono", "lucida console",
    "ocr", "teletype", "typewriter", "fixed", "screen",
]

# Regexes used by looks_like_code()
_LINE_NUMBER_RE = re.compile(r"^\d{1,3}\s+\S")
_YAML_KEY_RE = re.compile(r"^[a-z0-9_.\-/]+\s*:")
_SHELL_RE = re.compile(r"^[$#>]")
_DOCKER_CI_RE = re.compile(
    r"^(FROM|WORKDIR|RUN|CMD|ENTRYPOINT|ENV|COPY|ADD|EXPOSE|VOLUME|"
    r"STAGES|PIPELINE|AGENT|WHEN|STAGE|KIND|METADATA|SPEC|SELECTOR)\b"
)
_PGM_KEYWORD_RE = re.compile(r"^(import|def|class|return|print|echo)\b")

# Computer Modern Typewriter: matches "cmt10" / "cmtt10" but NOT "cmti10"
# (Computer Modern Text Italic — a serif font).
_CM_TYPEFACE_RE = re.compile(r"^cmt(t|\d)", re.IGNORECASE)


def normalize_font_name(font_name: str) -> str:
    """Lowercase a font name, strip PDF subset prefixes and separators."""
    if not font_name:
        return ""
    name = re.sub(r"^[A-Z]{6}\+", "", font_name)
    name = re.sub(r"[-,_\s]+", "", name.lower())
    return name


def is_code_font(font_name: str | None) -> bool:
    """True if the font family is monospaced / typewriter."""
    if not font_name:
        return False
    lower = re.sub(r"^[A-Z]{6}\+", "", font_name).lower()
    return (any(sub in lower for sub in MONO_SUBSTRINGS)
            or bool(_CM_TYPEFACE_RE.match(lower)))


def _line_is_code_signature(line: str) -> bool:
    """Strong, unambiguous code-listing signatures. Prose rarely matches."""
    if _LINE_NUMBER_RE.match(line):
        return True
    if _YAML_KEY_RE.match(line):
        return True
    if _SHELL_RE.match(line):
        return True
    if _DOCKER_CI_RE.match(line):
        return True
    if _PGM_KEYWORD_RE.match(line):
        return True
    return False


def looks_like_code(text: str) -> bool:
    """
    Content-based heuristic for code listings.  Deliberately conservative:
    only line-numbered listings, YAML documents, shell prompts, Docker/CI
    keywords and unambiguous programming keywords count, and a majority of
    the block's lines must match.  Plain prose that merely starts with
    "For/If/Kind..." is never flagged.
    """
    if not text:
        return False
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    n = len(lines)
    if n < 2:
        return False

    strong = sum(1 for ln in lines if _line_is_code_signature(ln))
    return strong >= 2 and strong / n >= 0.5
