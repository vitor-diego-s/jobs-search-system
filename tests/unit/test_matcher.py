"""Tests for filter chain: each filter in isolation + full chain."""

import sqlite3

import pytest

from src.core.db import init_db, upsert_candidate
from src.core.schemas import JobCandidate, ScoredCandidate
from src.pipeline.matcher import (
    AlreadySeenFilter,
    DeduplicationFilter,
    ExcludeKeywordsFilter,
    PositiveKeywordsFilter,
    run_filter_chain,
)


def _candidate(
    *,
    external_id: str = "1",
    platform: str = "linkedin",
    title: str = "Senior Python Engineer",
    company: str = "Acme",
    url: str = "https://example.com/1",
    description_snippet: str = "",
    is_easy_apply: bool = False,
    workplace_type: str = "",
) -> JobCandidate:
    return JobCandidate(
        external_id=external_id,
        platform=platform,
        title=title,
        company=company,
        url=url,
        description_snippet=description_snippet,
        is_easy_apply=is_easy_apply,
        workplace_type=workplace_type,
    )


# ---------------------------------------------------------------------------
# ExcludeKeywordsFilter
# ---------------------------------------------------------------------------


class TestExcludeKeywordsFilter:
    def test_removes_matching_title(self) -> None:
        f = ExcludeKeywordsFilter(["Junior", "PHP"])
        candidates = [
            _candidate(external_id="1", title="Junior Python Dev"),
            _candidate(external_id="2", title="Senior Python Engineer"),
            _candidate(external_id="3", title="PHP Backend Developer"),
        ]
        result = f(candidates)
        assert len(result) == 1
        assert result[0].external_id == "2"

    def test_case_insensitive(self) -> None:
        f = ExcludeKeywordsFilter(["frontend"])
        candidates = [_candidate(title="Frontend Engineer"), _candidate(title="Backend Engineer")]
        result = f(candidates)
        assert len(result) == 1
        assert "Backend" in result[0].title

    def test_empty_keywords_passes_all(self) -> None:
        f = ExcludeKeywordsFilter([])
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        assert len(f(candidates)) == 2

    def test_no_match_passes_all(self) -> None:
        f = ExcludeKeywordsFilter(["Cobol"])
        candidates = [_candidate(title="Python Engineer")]
        assert len(f(candidates)) == 1

    def test_whitespace_keywords_ignored(self) -> None:
        f = ExcludeKeywordsFilter(["  ", ""])
        candidates = [_candidate()]
        assert len(f(candidates)) == 1

    def test_partial_match(self) -> None:
        """'React' matches 'React Native Engineer'."""
        f = ExcludeKeywordsFilter(["React"])
        candidates = [_candidate(title="React Native Engineer")]
        assert len(f(candidates)) == 0


# ---------------------------------------------------------------------------
# PositiveKeywordsFilter
# ---------------------------------------------------------------------------


class TestPositiveKeywordsFilter:
    def test_keeps_matching_title(self) -> None:
        f = PositiveKeywordsFilter(["Python"])
        candidates = [
            _candidate(external_id="1", title="Senior Python Engineer"),
            _candidate(external_id="2", title="Java Developer"),
        ]
        result = f(candidates)
        assert len(result) == 1
        assert result[0].external_id == "1"

    def test_matches_snippet(self) -> None:
        f = PositiveKeywordsFilter(["Django"])
        candidates = [
            _candidate(title="Backend Engineer", description_snippet="Django, FastAPI"),
        ]
        assert len(f(candidates)) == 1

    def test_empty_keywords_passes_all(self) -> None:
        f = PositiveKeywordsFilter([])
        candidates = [_candidate(), _candidate(external_id="2")]
        assert len(f(candidates)) == 2

    def test_case_insensitive(self) -> None:
        f = PositiveKeywordsFilter(["python"])
        candidates = [_candidate(title="PYTHON DEVELOPER")]
        assert len(f(candidates)) == 1

    def test_no_match_removes_all(self) -> None:
        f = PositiveKeywordsFilter(["Rust"])
        candidates = [_candidate(title="Python Engineer")]
        assert len(f(candidates)) == 0


# ---------------------------------------------------------------------------
# DeduplicationFilter
# ---------------------------------------------------------------------------


class TestDeduplicationFilter:
    def test_removes_duplicates(self) -> None:
        f = DeduplicationFilter()
        candidates = [
            _candidate(external_id="1", platform="linkedin"),
            _candidate(external_id="1", platform="linkedin"),
            _candidate(external_id="2", platform="linkedin"),
        ]
        result = f(candidates)
        assert len(result) == 2

    def test_different_platforms_not_deduped(self) -> None:
        f = DeduplicationFilter()
        candidates = [
            _candidate(external_id="1", platform="linkedin"),
            _candidate(external_id="1", platform="glassdoor"),
        ]
        assert len(f(candidates)) == 2

    def test_stateful_across_calls(self) -> None:
        """Dedup remembers IDs from previous calls on same instance."""
        f = DeduplicationFilter()
        batch1 = [_candidate(external_id="1")]
        batch2 = [_candidate(external_id="1"), _candidate(external_id="2")]
        f(batch1)
        result = f(batch2)
        assert len(result) == 1
        assert result[0].external_id == "2"

    def test_empty_list(self) -> None:
        f = DeduplicationFilter()
        assert f([]) == []


# ---------------------------------------------------------------------------
# AlreadySeenFilter
# ---------------------------------------------------------------------------


class TestAlreadySeenFilter:
    @pytest.fixture
    def db(self, tmp_path: "pytest.TempPathFactory") -> sqlite3.Connection:  # type: ignore[type-arg]
        return init_db(tmp_path / "test.db")

    def test_removes_seen_candidates(self, db: sqlite3.Connection) -> None:
        # Insert a candidate into DB
        upsert_candidate(db, ScoredCandidate(candidate=_candidate(external_id="1"), score=0.0))
        f = AlreadySeenFilter(db)
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        result = f(candidates)
        assert len(result) == 1
        assert result[0].external_id == "2"

    def test_empty_db_passes_all(self, db: sqlite3.Connection) -> None:
        f = AlreadySeenFilter(db)
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        assert len(f(candidates)) == 2

    def test_different_platform_not_seen(self, db: sqlite3.Connection) -> None:
        upsert_candidate(
            db,
            ScoredCandidate(
                candidate=_candidate(external_id="1", platform="glassdoor"),
                score=0.0,
            ),
        )
        f = AlreadySeenFilter(db)
        candidates = [_candidate(external_id="1", platform="linkedin")]
        assert len(f(candidates)) == 1


# ---------------------------------------------------------------------------
# Full chain integration
# ---------------------------------------------------------------------------


class TestRunFilterChain:
    """Synthetic run: 10 in → exclude → dedup → already_seen."""

    @pytest.fixture
    def db(self, tmp_path: "pytest.TempPathFactory") -> sqlite3.Connection:  # type: ignore[type-arg]
        return init_db(tmp_path / "test.db")

    def test_full_chain_synthetic(self, db: sqlite3.Connection) -> None:
        # Pre-seed DB with one candidate
        upsert_candidate(
            db, ScoredCandidate(candidate=_candidate(external_id="seen1"), score=0.0)
        )

        candidates = [
            # 3 will be excluded (Junior, PHP, Frontend)
            _candidate(external_id="exc1", title="Junior Python Dev"),
            _candidate(external_id="exc2", title="PHP Backend Dev"),
            _candidate(external_id="exc3", title="Frontend React Engineer"),
            # 2 duplicates of each other
            _candidate(external_id="dup1", title="Senior Python Engineer"),
            _candidate(external_id="dup1", title="Senior Python Engineer"),
            # 1 already seen in DB
            _candidate(external_id="seen1", title="Senior Python Engineer"),
            # 4 unique, valid candidates
            _candidate(external_id="ok1", title="Senior Python Engineer"),
            _candidate(external_id="ok2", title="Staff Backend Engineer"),
            _candidate(external_id="ok3", title="Lead Python Developer"),
            _candidate(external_id="ok4", title="Senior Software Engineer"),
        ]
        assert len(candidates) == 10

        filters = [
            ExcludeKeywordsFilter(["Junior", "PHP", "Frontend"]),
            DeduplicationFilter(),
            AlreadySeenFilter(db),
        ]
        result = run_filter_chain(candidates, filters)

        # 10 - 3 excluded - 1 dedup - 1 already_seen = 5
        assert len(result) == 5
        result_ids = {c.external_id for c in result}
        assert "exc1" not in result_ids
        assert "exc2" not in result_ids
        assert "exc3" not in result_ids
        assert "seen1" not in result_ids
        assert "ok1" in result_ids
        assert "ok2" in result_ids

    def test_chain_with_positive_filter(self, db: sqlite3.Connection) -> None:
        candidates = [
            _candidate(external_id="1", title="Senior Python Engineer"),
            _candidate(external_id="2", title="Senior Java Developer"),
            _candidate(external_id="3", title="Staff Python Backend"),
        ]
        filters = [
            PositiveKeywordsFilter(["Python"]),
        ]
        result = run_filter_chain(candidates, filters)
        assert len(result) == 2
        assert all("Python" in c.title for c in result)

    def test_empty_chain_passes_all(self) -> None:
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        result = run_filter_chain(candidates, [])
        assert len(result) == 2
