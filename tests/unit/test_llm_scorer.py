"""Tests for LLM-assisted relevance scoring (M10)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.core.config import ScoringConfig
from src.core.schemas import JobCandidate, ScoredCandidate
from src.pipeline.llm_scorer import (
    _build_user_prompt,
    _parse_llm_score,
    score_candidate_llm,
    score_candidates_llm,
)
from src.profile.schema import ProfileData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**overrides: object) -> ProfileData:
    defaults: dict[str, object] = {
        "name": "Jane Dev",
        "search_keywords": ["Senior Python Engineer", "Staff Backend Engineer"],
        "seniority": "senior",
        "scoring_keywords": ["Python", "FastAPI", "PostgreSQL"],
        "years_of_experience": 8,
        "preferred_workplace": ["remote"],
    }
    defaults.update(overrides)
    return ProfileData(**defaults)  # type: ignore[arg-type]


def _make_candidate(**overrides: object) -> JobCandidate:
    defaults: dict[str, object] = {
        "external_id": "job-123",
        "platform": "linkedin",
        "title": "Senior Python Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "url": "https://linkedin.com/jobs/view/123",
        "is_easy_apply": True,
        "workplace_type": "remote",
        "posted_time": "2 days ago",
        "description_snippet": "We are looking for a Senior Python Engineer...",
        "found_at": datetime(2026, 1, 1),
    }
    defaults.update(overrides)
    return JobCandidate(**defaults)  # type: ignore[arg-type]


def _make_scored(score: float = 50.0, **candidate_overrides: object) -> ScoredCandidate:
    return ScoredCandidate(candidate=_make_candidate(**candidate_overrides), score=score)


def _make_config(**overrides: object) -> ScoringConfig:
    defaults: dict[str, object] = {
        "llm_enabled": True,
        "llm_provider": "gemini",
        "llm_model": None,
        "rule_weight": 0.4,
        "llm_weight": 0.6,
    }
    defaults.update(overrides)
    return ScoringConfig(**defaults)  # type: ignore[arg-type]


def _mock_provider(response: str) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = response
    return provider


# ---------------------------------------------------------------------------
# TestBuildUserPrompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_includes_profile_name(self) -> None:
        prompt = _build_user_prompt(_make_candidate(), _make_profile())
        assert "Jane Dev" in prompt

    def test_includes_target_roles(self) -> None:
        prompt = _build_user_prompt(_make_candidate(), _make_profile())
        assert "Senior Python Engineer" in prompt
        assert "Staff Backend Engineer" in prompt

    def test_includes_seniority(self) -> None:
        prompt = _build_user_prompt(_make_candidate(), _make_profile())
        assert "senior" in prompt

    def test_includes_skills(self) -> None:
        prompt = _build_user_prompt(_make_candidate(), _make_profile())
        assert "Python" in prompt
        assert "FastAPI" in prompt

    def test_includes_job_title(self) -> None:
        prompt = _build_user_prompt(_make_candidate(), _make_profile())
        assert "Senior Python Engineer" in prompt

    def test_includes_description_when_present(self) -> None:
        candidate = _make_candidate(description_snippet="Looking for Python expert")
        prompt = _build_user_prompt(candidate, _make_profile())
        assert "Looking for Python expert" in prompt

    def test_no_description_section_when_empty(self) -> None:
        candidate = _make_candidate(description_snippet="")
        prompt = _build_user_prompt(candidate, _make_profile())
        assert "Description:" not in prompt

    def test_years_not_specified_when_none(self) -> None:
        profile = _make_profile(years_of_experience=None)
        prompt = _build_user_prompt(_make_candidate(), profile)
        assert "not specified" in prompt

    def test_no_workplace_preference(self) -> None:
        profile = _make_profile(preferred_workplace=[])
        prompt = _build_user_prompt(_make_candidate(), profile)
        assert "no preference" in prompt


# ---------------------------------------------------------------------------
# TestParseLlmScore
# ---------------------------------------------------------------------------

class TestParseLlmScore:
    def test_valid_json(self) -> None:
        raw = '{"score": 85, "reasoning": "Strong match"}'
        score, reasoning = _parse_llm_score(raw)
        assert score == 85.0
        assert reasoning == "Strong match"

    def test_markdown_wrapped_json(self) -> None:
        raw = '```json\n{"score": 72, "reasoning": "Good fit"}\n```'
        score, reasoning = _parse_llm_score(raw)
        assert score == 72.0
        assert reasoning == "Good fit"

    def test_score_clamped_above_100(self) -> None:
        raw = '{"score": 150, "reasoning": "Off the charts"}'
        score, _ = _parse_llm_score(raw)
        assert score == 100.0

    def test_score_clamped_below_zero(self) -> None:
        raw = '{"score": -10, "reasoning": "Terrible"}'
        score, _ = _parse_llm_score(raw)
        assert score == 0.0

    def test_missing_reasoning_defaults_empty(self) -> None:
        raw = '{"score": 60}'
        score, reasoning = _parse_llm_score(raw)
        assert score == 60.0
        assert reasoning == ""

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ValueError, match="Failed to parse"):
            _parse_llm_score("not json at all")

    def test_missing_score_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'score'"):
            _parse_llm_score('{"reasoning": "forgot score"}')

    def test_float_score_accepted(self) -> None:
        raw = '{"score": 77.5, "reasoning": "Close"}'
        score, _ = _parse_llm_score(raw)
        assert score == 77.5


# ---------------------------------------------------------------------------
# TestScoreCandidateLlm
# ---------------------------------------------------------------------------

class TestScoreCandidateLlm:
    def test_blends_correctly(self) -> None:
        # rule=50, llm=80 -> 0.4*50 + 0.6*80 = 20+48 = 68
        scored = _make_scored(score=50.0)
        provider = _mock_provider('{"score": 80, "reasoning": "Great fit"}')
        config = _make_config(rule_weight=0.4, llm_weight=0.6)

        result = score_candidate_llm(scored, _make_profile(), config, provider)

        assert result.score == 68.0
        assert result.llm_score == 80.0
        assert result.llm_reasoning == "Great fit"

    def test_skips_empty_description(self) -> None:
        scored = _make_scored(description_snippet="")
        provider = _mock_provider('{"score": 90, "reasoning": "x"}')
        config = _make_config()

        result = score_candidate_llm(scored, _make_profile(), config, provider)

        assert result is scored  # unchanged
        provider.complete.assert_not_called()

    def test_llm_api_failure_fallback(self) -> None:
        scored = _make_scored(score=42.0)
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("API down")
        config = _make_config()

        result = score_candidate_llm(scored, _make_profile(), config, provider)

        assert result is scored  # original returned
        assert result.score == 42.0
        assert result.llm_score is None

    def test_parse_failure_fallback(self) -> None:
        scored = _make_scored(score=30.0)
        provider = _mock_provider("bad json }{")
        config = _make_config()

        result = score_candidate_llm(scored, _make_profile(), config, provider)

        assert result is scored
        assert result.score == 30.0

    def test_populates_llm_score_and_reasoning(self) -> None:
        scored = _make_scored(score=60.0)
        provider = _mock_provider('{"score": 90, "reasoning": "Perfect match"}')
        config = _make_config(rule_weight=0.4, llm_weight=0.6)

        result = score_candidate_llm(scored, _make_profile(), config, provider)

        assert result.llm_score == 90.0
        assert result.llm_reasoning == "Perfect match"
        assert result.score == round(0.4 * 60 + 0.6 * 90, 2)

    def test_passes_custom_system_prompt_to_provider(self) -> None:
        scored = _make_scored()
        provider = _mock_provider('{"score": 70, "reasoning": "ok"}')
        config = _make_config()

        score_candidate_llm(scored, _make_profile(), config, provider)

        call_kwargs = provider.complete.call_args
        assert "system" in call_kwargs.kwargs
        assert "recruiter" in call_kwargs.kwargs["system"].lower()


# ---------------------------------------------------------------------------
# TestScoreCandidatesLlm
# ---------------------------------------------------------------------------

class TestScoreCandidatesLlm:
    def test_disabled_returns_unchanged(self) -> None:
        scored_list = [_make_scored(50.0), _make_scored(70.0)]
        config = ScoringConfig(llm_enabled=False)

        result = score_candidates_llm(scored_list, _make_profile(), config)

        assert result is scored_list

    def test_re_sorts_after_blending(self) -> None:
        # First candidate starts higher rule-score but LLM will push second up
        c1 = _make_scored(score=80.0, external_id="job-1")
        c2 = _make_scored(score=40.0, external_id="job-2")

        # LLM gives c1=20, c2=100 → blended: c1=0.4*80+0.6*20=44, c2=0.4*40+0.6*100=76
        responses = iter([
            '{"score": 20, "reasoning": "bad for job-1"}',
            '{"score": 100, "reasoning": "perfect for job-2"}',
        ])
        provider = MagicMock()
        provider.complete.side_effect = lambda *a, **kw: next(responses)
        config = _make_config(rule_weight=0.4, llm_weight=0.6)

        from unittest.mock import patch
        with patch("src.pipeline.llm_scorer.get_provider", return_value=provider):
            result = score_candidates_llm([c1, c2], _make_profile(), config)

        assert result[0].candidate.external_id == "job-2"
        assert result[1].candidate.external_id == "job-1"

    def test_candidates_without_description_kept(self) -> None:
        c_with = _make_scored(50.0, description_snippet="Python engineer needed")
        c_without = _make_scored(90.0, external_id="job-no-desc", description_snippet="")

        provider = _mock_provider('{"score": 60, "reasoning": "ok"}')
        config = _make_config()

        from unittest.mock import patch
        with patch("src.pipeline.llm_scorer.get_provider", return_value=provider):
            result = score_candidates_llm([c_with, c_without], _make_profile(), config)

        # Both should appear
        assert len(result) == 2
        # c_without keeps its rule-based score and has no llm_score
        no_desc = next(r for r in result if r.candidate.external_id == "job-no-desc")
        assert no_desc.llm_score is None
        assert no_desc.score == 90.0

    def test_partial_failure_does_not_crash_batch(self) -> None:
        c1 = _make_scored(50.0, external_id="job-ok")
        c2 = _make_scored(60.0, external_id="job-fail")

        call_count = 0

        def side_effect(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM exploded")
            return '{"score": 80, "reasoning": "good"}'

        provider = MagicMock()
        provider.complete.side_effect = side_effect
        config = _make_config()

        from unittest.mock import patch
        with patch("src.pipeline.llm_scorer.get_provider", return_value=provider):
            result = score_candidates_llm([c1, c2], _make_profile(), config)

        assert len(result) == 2
        # c2 (the failed one) should keep its original score
        failed = next(r for r in result if r.candidate.external_id == "job-fail")
        assert failed.score == 60.0
        assert failed.llm_score is None
