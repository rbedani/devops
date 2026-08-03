"""Token-aware job relevance matcher over title + company + description.

Pure functions with no I/O so the whole gate is unit-testable (spec:
job-relevance-matcher). Matching is case-insensitive and token-aware:
keywords and candidate fields are NFKD-folded (accents stripped),
lowercased, and split into alphanumeric runs. Characters between runs
(spaces, slashes, underscores, hyphens, apostrophes) are token boundaries,
so "ci/cd", "ci_cd" and "ci-cd" are equivalent. A multi-token phrase
matches only as a contiguous token sequence. Each keyword is expanded with
its curated, versioned synonym entries before matching.
"""

from __future__ import annotations

import unicodedata

from src.core.models.job import Job

# Versioned, curated synonym map (v1). Additions, edits and removals are
# tracked SDD changes, never runtime edits (spec: Curated Synonym Map).
SYNONYMS_V1: dict[str, tuple[str, ...]] = {
    "kubernetes": ("k8s",),
    "k8s": ("kubernetes",),
    "ci/cd": ("ci_cd",),
    "ci_cd": ("ci/cd",),
    "sre": ("site reliability",),
    "site reliability": ("sre",),
}

_MATCH_FIELDS = ("title", "company", "description")


def tokenize(text: str) -> list[str]:
    """Fold accents (NFKD), lowercase, split into alphanumeric runs.

    Everything else is a token boundary: "ci/cd", "ci_cd" and "ci-cd" all
    yield ["ci", "cd"]. Empty or whitespace-only text yields no tokens.
    """
    folded = _fold(text)
    tokens: list[str] = []
    current: list[str] = []
    for ch in folded:
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def normalize_keywords(
    keywords: list[str],
    synonyms: dict[str, tuple[str, ...]] = SYNONYMS_V1,
) -> list[list[str]]:
    """Map each keyword to its token phrases, expanded with its synonyms.

    "kubernetes" -> [["kubernetes"], ["k8s"]]; a phrase keyword such as
    "site reliability" stays one contiguous phrase ["site", "reliability"].
    """
    phrases: list[list[str]] = []
    for keyword in keywords:
        phrases.append(tokenize(keyword))
        for synonym in synonyms.get(keyword, ()):
            phrases.append(tokenize(synonym))
    return phrases


def _phrase_matches(phrase: list[str], tokens: list[str]) -> bool:
    """True when the phrase tokens appear contiguously inside tokens."""
    if not phrase:
        return False
    width = len(phrase)
    return any(tokens[i : i + width] == phrase for i in range(len(tokens) - width + 1))


def matches_relevance(
    job: Job,
    keywords: list[str],
    synonyms: dict[str, tuple[str, ...]] = SYNONYMS_V1,
) -> bool:
    """Return True when any keyword (or synonym) matches title, company or
    description (OR semantics).

    An empty keyword list matches everything (no keyword filter). An empty
    or unparseable description contributes no matches and never excludes an
    offer that matches on title/company (spec: Expanded Match Surface).
    """
    if not keywords:
        return True
    phrases = normalize_keywords(keywords, synonyms)
    if not phrases:
        return True
    for field in _MATCH_FIELDS:
        tokens = tokenize(getattr(job, field) or "")
        if any(_phrase_matches(phrase, tokens) for phrase in phrases):
            return True
    return False


def _fold(text: str) -> str:
    """NFKD-decompose and strip combining marks (accent folding), lowercase."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()
