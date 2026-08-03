"""Unit tests for the token-aware job relevance matcher (src/scan/matcher.py).

Covers (spec: job-relevance-matcher):
- tokenize: NFKD accent folding, lowercase, alnum-run tokenization, and
  punctuation variants ("ci/cd" == "ci_cd" == "ci-cd" -> ["ci", "cd"])
- contiguous phrase matching: "data engineer" matches "data engineer is
  required" but NOT "data science engineer"
- matches_relevance: OR gate over title + company + description; empty or
  unparseable description never silently excludes; case-insensitive;
  SYNONYMS_V1 expansion (kubernetes<->k8s, ci/cd<->ci_cd, sre<->site
  reliability)
"""

from __future__ import annotations

from src.core.models.job import Job
from src.scan.matcher import SYNONYMS_V1, matches_relevance, tokenize


def _job(title: str, company: str = "", description: str = "") -> Job:
    """Build a minimal Job for relevance matcher tests."""
    return Job(
        source="test",
        title=title,
        url=f"https://example.com/{title}",
        company=company,
        description=description,
    )


class TestTokenize:
    """Spec: token normalization — fold accents, lowercase, alnum runs."""

    def test_lowercases_and_splits_alnum_runs(self) -> None:
        """RED: 'DevOps Engineer' -> ['devops', 'engineer']."""
        assert tokenize("DevOps Engineer") == ["devops", "engineer"]

    def test_folds_accents_via_nfkd(self) -> None:
        """TRIANGULATE: accented characters fold to their base letters."""
        assert tokenize("Administración") == ["administracion"]

    def test_separators_are_token_boundaries(self) -> None:
        """TRIANGULATE: '/', '_' and '-' all split tokens identically."""
        assert tokenize("ci/cd") == ["ci", "cd"]
        assert tokenize("ci_cd") == ["ci", "cd"]
        assert tokenize("ci-cd") == ["ci", "cd"]

    def test_apostrophe_is_a_token_boundary(self) -> None:
        """TRIANGULATE: apostrophes separate runs too."""
        assert tokenize("l'équipe") == ["l", "equipe"]

    def test_empty_text_yields_no_tokens(self) -> None:
        """EDGE: empty string produces an empty token list."""
        assert tokenize("") == []


class TestContiguousPhrase:
    """Spec: a multi-token phrase matches only as a contiguous sequence."""

    def test_contiguous_phrase_matches(self) -> None:
        """RED: 'data engineer' is contiguous inside 'data engineer is required'."""
        job = _job("Engineer", "Acme", "data engineer is required")
        assert matches_relevance(job, ["data engineer"])

    def test_non_contiguous_phrase_does_not_match(self) -> None:
        """TRIANGULATE: 'data science engineer' must NOT match 'data engineer'."""
        job = _job("Engineer", "Acme", "data science engineer")
        assert not matches_relevance(job, ["data engineer"])

    def test_phrase_across_separator_variants(self) -> None:
        """TRIANGULATE: 'ci/cd' phrase matches candidate tokenized from 'ci_cd'."""
        job = _job("Engineer", "Acme", "ci_cd pipeline")
        assert matches_relevance(job, ["ci/cd"])


class TestMatchesRelevance:
    """Spec: OR gate over title + company + description."""

    def test_keyword_in_title_matches(self) -> None:
        """RED: keyword present in title passes."""
        assert matches_relevance(_job("DevOps Engineer", "Acme", "backend"), ["devops"])

    def test_keyword_in_company_matches(self) -> None:
        """TRIANGULATE: keyword present in company passes."""
        assert matches_relevance(_job("Platform Engineer", "SRE Corp"), ["sre"])

    def test_keyword_only_in_description_matches(self) -> None:
        """RED (spec 'Keyword only in description'): desc-only match passes."""
        job = _job("Platform Engineer", "Acme", "We need terraform for our infra")
        assert matches_relevance(job, ["terraform"])

    def test_empty_description_passes_on_title_match(self) -> None:
        """RED (spec 'Empty description'): title match survives empty description."""
        assert matches_relevance(_job("DevOps Engineer", "Acme", ""), ["devops"])

    def test_empty_description_no_match_is_filtered(self) -> None:
        """TRIANGULATE (spec 'Empty description'): no t/c match -> filtered out."""
        assert not matches_relevance(_job("Backend Engineer", "Acme", ""), ["devops"])

    def test_no_match_anywhere_is_filtered(self) -> None:
        """RED (spec 'No match anywhere'): no keyword in any field -> filtered out."""
        job = _job("Backend Engineer", "Acme", "java spring boot")
        assert not matches_relevance(job, ["devops"])

    def test_case_insensitive(self) -> None:
        """RED (spec 'Case insensitivity'): 'DEVOPS' matches 'devops engineer'."""
        job = _job("Engineer", "Acme", "devops engineer")
        assert matches_relevance(job, ["DEVOPS"])

    def test_any_keyword_matches(self) -> None:
        """TRIANGULATE: any of several keywords is enough (OR semantics)."""
        job = _job("Engineer", "Acme", "python pipeline")
        assert matches_relevance(job, ["devops", "python"])

    def test_empty_keyword_list_matches_everything(self) -> None:
        """EDGE: no keywords = no keyword filter (legacy behavior)."""
        assert matches_relevance(_job("Backend Engineer", "Acme"), [])

    def test_none_description_never_crashes(self) -> None:
        """EDGE: unparseable (None) description contributes no matches, no crash."""
        job = _job("Backend Engineer", "Acme")
        job.description = None  # type: ignore[assignment]
        assert not matches_relevance(job, ["devops"])


class TestSynonyms:
    """Spec: curated, versioned synonym map expands keywords before matching."""

    def test_map_is_versioned_constant(self) -> None:
        """RED (spec 'Map versioned in code'): v1 entries present both ways."""
        assert SYNONYMS_V1["kubernetes"] == ("k8s",)
        assert SYNONYMS_V1["k8s"] == ("kubernetes",)
        assert SYNONYMS_V1["ci/cd"] == ("ci_cd",)
        assert SYNONYMS_V1["ci_cd"] == ("ci/cd",)
        assert SYNONYMS_V1["sre"] == ("site reliability",)
        assert SYNONYMS_V1["site reliability"] == ("sre",)

    def test_kubernetes_matches_k8s(self) -> None:
        """RED (spec 'Synonym match passes'): 'kubernetes' matches 'k8s' desc."""
        job = _job("Engineer", "Acme", "k8s admin")
        assert matches_relevance(job, ["kubernetes"])

    def test_k8s_matches_kubernetes(self) -> None:
        """TRIANGULATE: reverse direction of the kubernetes<->k8s entry."""
        job = _job("Engineer", "Acme", "kubernetes admin")
        assert matches_relevance(job, ["k8s"])

    def test_ci_cd_matches_ci_slash_cd(self) -> None:
        """TRIANGULATE: 'ci_cd' keyword matches 'CI/CD' description."""
        job = _job("Engineer", "Acme", "CI/CD pipeline")
        assert matches_relevance(job, ["ci_cd"])

    def test_sre_matches_site_reliability(self) -> None:
        """TRIANGULATE: 'sre' expands to the 'site reliability' phrase."""
        job = _job("Engineer", "Acme", "site reliability practice")
        assert matches_relevance(job, ["sre"])

    def test_synonym_matches_in_company(self) -> None:
        """TRIANGULATE: synonyms apply to every field, not only description."""
        assert matches_relevance(_job("Engineer", "K8s Cloud"), ["kubernetes"])
