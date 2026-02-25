"""Tests for rule-based scorer."""

from src.core.config import ScoringConfig
from src.core.schemas import JobCandidate
from src.pipeline.scorer import score_candidate, score_candidates


def _candidate(
    *,
    title: str = "Senior Python Engineer",
    is_easy_apply: bool = False,
    workplace_type: str = "",
    posted_time: str = "",
    description_snippet: str = "",
) -> JobCandidate:
    return JobCandidate(
        external_id="1",
        platform="linkedin",
        title=title,
        company="Acme",
        url="https://example.com/1",
        is_easy_apply=is_easy_apply,
        workplace_type=workplace_type,
        posted_time=posted_time,
        description_snippet=description_snippet,
    )


def _config(**kwargs: float) -> ScoringConfig:
    return ScoringConfig(**kwargs)


# ---------------------------------------------------------------------------
# Individual bonuses
# ---------------------------------------------------------------------------


class TestScoreCandidate:
    def test_seniority_bonus(self) -> None:
        config = _config(seniority_match_bonus=15.0)
        result = score_candidate(_candidate(title="Senior Engineer"), config)
        assert result.score >= 15.0

    def test_no_seniority_no_bonus(self) -> None:
        config = _config(seniority_match_bonus=15.0)
        result = score_candidate(_candidate(title="Python Developer"), config)
        # No seniority keyword → no seniority bonus
        assert result.score < 15.0

    def test_easy_apply_bonus(self) -> None:
        config = _config(easy_apply_bonus=10.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(is_easy_apply=True), config)
        assert result.score >= 10.0

    def test_no_easy_apply_no_bonus(self) -> None:
        config = _config(easy_apply_bonus=10.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(is_easy_apply=False), config)
        # Should not include easy apply bonus
        assert result.score < 10.0 or result.score == 0.0

    def test_remote_bonus(self) -> None:
        config = _config(remote_bonus=10.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(workplace_type="remote"), config)
        assert result.score >= 10.0

    def test_non_remote_no_bonus(self) -> None:
        config = _config(remote_bonus=10.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(workplace_type="hybrid"), config)
        assert result.score < 10.0

    def test_title_keyword_bonus(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(
            _candidate(title="Python Developer"),
            config,
            require_keywords=["Python"],
        )
        assert result.score >= 20.0

    def test_multiple_title_keywords(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(
            _candidate(title="Senior Python Backend Engineer"),
            config,
            require_keywords=["Python", "Backend"],
        )
        assert result.score >= 40.0

    def test_no_require_keywords_no_title_bonus(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(), config, require_keywords=None)
        # No require_keywords → no title match bonus
        assert result.score < 20.0

    def test_recency_bonus_hours(self) -> None:
        config = _config(recency_weight=1.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(posted_time="2 hours ago"), config)
        assert result.score > 0.0

    def test_recency_bonus_days(self) -> None:
        config = _config(recency_weight=1.0, seniority_match_bonus=0.0)
        recent = score_candidate(_candidate(posted_time="1 day ago"), config)
        old = score_candidate(_candidate(posted_time="4 weeks ago"), config)
        assert recent.score > old.score

    def test_no_posted_time_no_recency(self) -> None:
        config = _config(recency_weight=1.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(posted_time=""), config)
        assert result.score == 0.0

    def test_unparseable_posted_time(self) -> None:
        config = _config(recency_weight=1.0, seniority_match_bonus=0.0)
        result = score_candidate(_candidate(posted_time="just now"), config)
        # "just now" doesn't match patterns → 0 recency
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Score clamping
# ---------------------------------------------------------------------------


class TestScoreClamping:
    def test_score_clamped_at_100(self) -> None:
        """Even with all bonuses maxed, score stays <= 100."""
        config = _config(
            title_match_bonus=50.0,
            seniority_match_bonus=30.0,
            easy_apply_bonus=20.0,
            remote_bonus=20.0,
            recency_weight=1.0,
        )
        result = score_candidate(
            _candidate(
                title="Senior Python Backend Staff Engineer",
                is_easy_apply=True,
                workplace_type="remote",
                posted_time="1 hour ago",
            ),
            config,
            require_keywords=["Python", "Backend", "Staff"],
        )
        assert result.score <= 100.0

    def test_score_never_negative(self) -> None:
        config = _config()
        result = score_candidate(
            _candidate(title="Random Job", workplace_type="onsite"),
            config,
        )
        assert result.score >= 0.0


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------


class TestScoreCandidates:
    def test_sorted_descending(self) -> None:
        config = _config(seniority_match_bonus=15.0, easy_apply_bonus=10.0)
        candidates = [
            _candidate(title="Python Developer", is_easy_apply=False),
            _candidate(title="Senior Python Engineer", is_easy_apply=True),
            _candidate(title="Lead Python Engineer", is_easy_apply=False),
        ]
        scored = score_candidates(candidates, config)
        assert scored[0].score >= scored[1].score >= scored[2].score

    def test_returns_scored_candidates(self) -> None:
        config = _config()
        candidates = [_candidate(), _candidate(title="Junior Dev")]
        scored = score_candidates(candidates, config)
        assert len(scored) == 2
        assert all(0.0 <= s.score <= 100.0 for s in scored)

    def test_empty_list(self) -> None:
        config = _config()
        assert score_candidates([], config) == []

    def test_all_scores_in_range(self) -> None:
        config = _config(
            title_match_bonus=20.0,
            seniority_match_bonus=15.0,
            easy_apply_bonus=10.0,
            remote_bonus=10.0,
            recency_weight=0.3,
        )
        candidates = [
            _candidate(title="Senior Python Engineer", is_easy_apply=True,
                        workplace_type="remote", posted_time="2 days ago"),
            _candidate(title="Junior Java Dev", posted_time="3 weeks ago"),
            _candidate(title="Staff Backend Lead", is_easy_apply=True,
                        workplace_type="remote", posted_time="1 hour ago"),
        ]
        scored = score_candidates(candidates, config, require_keywords=["Python"])
        for s in scored:
            assert 0.0 <= s.score <= 100.0


# ---------------------------------------------------------------------------
# Scoring keywords
# ---------------------------------------------------------------------------


class TestScoringKeywords:
    def test_scoring_keywords_add_title_bonus(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(
            _candidate(title="Python Developer"),
            config,
            scoring_keywords=["Python"],
        )
        assert result.score >= 20.0

    def test_scoring_and_require_accumulate(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(
            _candidate(title="Python Backend Developer"),
            config,
            require_keywords=["Python"],
            scoring_keywords=["Backend"],
        )
        assert result.score >= 40.0

    def test_none_scoring_keywords_backward_compat(self) -> None:
        config = _config(title_match_bonus=20.0, seniority_match_bonus=0.0)
        result = score_candidate(
            _candidate(title="Python Developer"),
            config,
            require_keywords=["Python"],
            scoring_keywords=None,
        )
        assert result.score >= 20.0
