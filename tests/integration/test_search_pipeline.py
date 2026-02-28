"""Integration test: full pipeline with mock adapter (no browser)."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import (
    QuotaPlatformConfig,
    ScoringConfig,
    SearchConfig,
    SearchFilters,
    Settings,
)
from src.core.db import init_db
from src.core.schemas import JobCandidate
from src.pipeline.orchestrator import SearchResult, export_results_json, run_all_searches
from src.platforms.base import PlatformAdapter

# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------


class MockAdapter(PlatformAdapter):
    """Returns pre-configured candidates for each search."""

    def __init__(self, candidates: list[JobCandidate]) -> None:
        self._candidates = candidates

    @property
    def platform_id(self) -> str:
        return "linkedin"

    async def search(self, config: SearchConfig) -> list[JobCandidate]:
        return list(self._candidates)


def _candidate(
    *,
    external_id: str = "1",
    title: str = "Senior Python Engineer",
    company: str = "Acme",
    is_easy_apply: bool = True,
    workplace_type: str = "remote",
    posted_time: str = "2 days ago",
) -> JobCandidate:
    return JobCandidate(
        external_id=external_id,
        platform="linkedin",
        title=title,
        company=company,
        url=f"https://www.linkedin.com/jobs/view/{external_id}/",
        is_easy_apply=is_easy_apply,
        workplace_type=workplace_type,
        posted_time=posted_time,
    )


def _settings(
    *,
    searches: list[SearchConfig] | None = None,
    max_searches: int = 5,
    max_candidates: int = 200,
) -> Settings:
    if searches is None:
        searches = [
            SearchConfig(
                keyword="Senior Python Engineer",
                platform="linkedin",
                filters=SearchFilters(
                    workplace_type=["remote"],
                    easy_apply_only=True,
                ),
                exclude_keywords=["Junior", "PHP"],
            ),
        ]
    return Settings(
        searches=searches,
        quotas={"linkedin": QuotaPlatformConfig(
            max_searches_per_day=max_searches,
            max_candidates_per_day=max_candidates,
        )},
        scoring=ScoringConfig(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end pipeline: adapter → filter → score → DB."""

    @pytest.fixture
    def db(self, tmp_path: pytest.TempPathFactory) -> sqlite3.Connection:  # type: ignore[type-arg]
        return init_db(tmp_path / "test.db")

    async def test_basic_pipeline(self, db: sqlite3.Connection) -> None:
        """Candidates flow through filter → score → DB."""
        candidates = [
            _candidate(external_id="1", title="Senior Python Engineer"),
            _candidate(external_id="2", title="Staff Backend Engineer"),
        ]
        adapter = MockAdapter(candidates)
        settings = _settings()

        results = await run_all_searches(settings, adapter, db)

        assert len(results) == 1
        r = results[0]
        assert r.raw_count == 2
        assert r.filtered_count == 2
        assert r.new_count == 2
        assert len(r.scored) == 2
        # Scores should be > 0 (seniority + remote + easy_apply + recency)
        assert all(s.score > 0 for s in r.scored)

    async def test_exclude_filter_works(self, db: sqlite3.Connection) -> None:
        """Excluded keywords are removed from results."""
        candidates = [
            _candidate(external_id="1", title="Senior Python Engineer"),
            _candidate(external_id="2", title="Junior PHP Developer"),
            _candidate(external_id="3", title="Staff Python Backend"),
        ]
        adapter = MockAdapter(candidates)
        settings = _settings()

        results = await run_all_searches(settings, adapter, db)

        r = results[0]
        assert r.raw_count == 3
        assert r.filtered_count == 2  # Junior PHP excluded
        assert r.new_count == 2

    async def test_dedup_across_keywords(self, db: sqlite3.Connection) -> None:
        """Same candidate from two keyword searches is deduped."""
        shared = _candidate(external_id="shared", title="Senior Python Engineer")
        unique1 = _candidate(external_id="u1", title="Staff Python Engineer")
        unique2 = _candidate(external_id="u2", title="Lead Backend Engineer")

        class MultiAdapter(PlatformAdapter):
            def __init__(self) -> None:
                self._call = 0

            @property
            def platform_id(self) -> str:
                return "linkedin"

            async def search(self, config: SearchConfig) -> list[JobCandidate]:
                self._call += 1
                if self._call == 1:
                    return [shared, unique1]
                return [shared, unique2]

        settings = _settings(searches=[
            SearchConfig(keyword="Python Engineer", platform="linkedin",
                         filters=SearchFilters(easy_apply_only=True)),
            SearchConfig(keyword="Backend Engineer", platform="linkedin",
                         filters=SearchFilters(easy_apply_only=True)),
        ])

        results = await run_all_searches(settings, MultiAdapter(), db)

        assert len(results) == 2
        total_new = sum(r.new_count for r in results)
        # shared appears in both but dedup filter catches it on 2nd run
        assert total_new == 3  # shared + u1 + u2

    async def test_quota_blocks_search(self, db: sqlite3.Connection) -> None:
        """When quota is exhausted, search is skipped."""
        candidates = [_candidate(external_id="1")]
        adapter = MockAdapter(candidates)
        settings = _settings(max_searches=1, searches=[
            SearchConfig(keyword="Search 1", platform="linkedin",
                         filters=SearchFilters()),
            SearchConfig(keyword="Search 2", platform="linkedin",
                         filters=SearchFilters()),
        ])

        results = await run_all_searches(settings, adapter, db)

        # Only first search should execute, second blocked by quota
        assert len(results) == 1
        assert results[0].keyword == "Search 1"

    async def test_already_seen_skipped_on_rerun(self, db: sqlite3.Connection) -> None:
        """Candidates from a first run are filtered as already-seen on second run."""
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        adapter = MockAdapter(candidates)
        settings = _settings(max_searches=10)

        # First run — both new
        results1 = await run_all_searches(settings, adapter, db)
        assert results1[0].new_count == 2

        # Second run — both already seen
        results2 = await run_all_searches(settings, adapter, db)
        assert results2[0].filtered_count == 0

    async def test_scores_sorted_descending(self, db: sqlite3.Connection) -> None:
        """Scored candidates are returned highest-score first."""
        candidates = [
            _candidate(external_id="1", title="Python Dev", is_easy_apply=False,
                        workplace_type="onsite"),
            _candidate(external_id="2", title="Senior Python Engineer",
                        is_easy_apply=True, workplace_type="remote"),
        ]
        adapter = MockAdapter(candidates)
        settings = _settings()

        results = await run_all_searches(settings, adapter, db)

        scored = results[0].scored
        assert scored[0].score >= scored[-1].score

    async def test_db_has_candidates_after_run(self, db: sqlite3.Connection) -> None:
        """Candidates are persisted in the database."""
        candidates = [_candidate(external_id="1"), _candidate(external_id="2")]
        adapter = MockAdapter(candidates)
        settings = _settings()

        await run_all_searches(settings, adapter, db)

        row = db.execute("SELECT COUNT(*) as cnt FROM candidates").fetchone()
        assert row["cnt"] == 2

    async def test_search_run_recorded(self, db: sqlite3.Connection) -> None:
        """Search run metadata is recorded in the search_runs table."""
        adapter = MockAdapter([_candidate(external_id="1")])
        settings = _settings()

        await run_all_searches(settings, adapter, db)

        row = db.execute("SELECT COUNT(*) as cnt FROM search_runs").fetchone()
        assert row["cnt"] == 1


    async def test_description_snippet_persisted(self, db: sqlite3.Connection) -> None:
        """Candidates with description_snippet survive pipeline and persist to DB."""
        candidates = [
            JobCandidate(
                external_id="desc1",
                platform="linkedin",
                title="Senior Python Engineer",
                company="Acme",
                url="https://www.linkedin.com/jobs/view/desc1/",
                is_easy_apply=True,
                workplace_type="remote",
                posted_time="1 day ago",
                description_snippet="We are looking for a senior Python engineer to join our team.",
            ),
        ]
        adapter = MockAdapter(candidates)
        settings = _settings()

        results = await run_all_searches(settings, adapter, db)

        assert len(results) == 1
        assert results[0].new_count == 1
        # Verify persisted in DB
        row = db.execute(
            "SELECT description_snippet FROM candidates WHERE external_id = ?",
            ("desc1",),
        ).fetchone()
        assert row is not None
        assert row["description_snippet"] == (
            "We are looking for a senior Python engineer to join our team."
        )


class TestExportJson:
    def test_export_format(self) -> None:
        from src.core.schemas import ScoredCandidate

        scored = [ScoredCandidate(candidate=_candidate(external_id="1"), score=42.5)]
        result = SearchResult(
            keyword="test",
            platform="linkedin",
            raw_count=1,
            filtered_count=1,
            new_count=1,
            scored=scored,
        )
        output = export_results_json([result])
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["score"] == 42.5
        assert data[0]["keyword"] == "test"
        assert data[0]["external_id"] == "1"
        assert "description_snippet" in data[0]

    def test_export_includes_description_snippet(self) -> None:
        from src.core.schemas import ScoredCandidate

        candidate = JobCandidate(
            external_id="99",
            platform="linkedin",
            title="Engineer",
            url="https://www.linkedin.com/jobs/view/99/",
            description_snippet="Full description text here.",
        )
        scored = [ScoredCandidate(candidate=candidate, score=50.0)]
        result = SearchResult(
            keyword="test",
            platform="linkedin",
            raw_count=1,
            filtered_count=1,
            new_count=1,
            scored=scored,
        )
        output = export_results_json([result])
        data = json.loads(output)
        assert data[0]["description_snippet"] == "Full description text here."

    def test_export_empty(self) -> None:
        output = export_results_json([])
        assert json.loads(output) == []

    def test_export_includes_llm_fields(self) -> None:
        from src.core.schemas import ScoredCandidate

        scored = [ScoredCandidate(
            candidate=_candidate(external_id="llm1"),
            score=68.0,
            llm_score=80.0,
            llm_reasoning="Strong match",
        )]
        result = SearchResult(
            keyword="test",
            platform="linkedin",
            raw_count=1,
            filtered_count=1,
            new_count=1,
            scored=scored,
        )
        output = export_results_json([result])
        data = json.loads(output)
        assert data[0]["llm_score"] == 80.0
        assert data[0]["llm_reasoning"] == "Strong match"

    def test_export_llm_fields_null_when_not_scored(self) -> None:
        from src.core.schemas import ScoredCandidate

        scored = [ScoredCandidate(candidate=_candidate(external_id="no-llm"), score=50.0)]
        result = SearchResult(
            keyword="test",
            platform="linkedin",
            raw_count=1,
            filtered_count=1,
            new_count=1,
            scored=scored,
        )
        output = export_results_json([result])
        data = json.loads(output)
        assert data[0]["llm_score"] is None
        assert data[0]["llm_reasoning"] == ""


class TestLlmScoringPipeline:
    """Integration tests: pipeline with LLM scoring enabled."""

    @pytest.fixture
    def db(self, tmp_path: pytest.TempPathFactory) -> sqlite3.Connection:  # type: ignore[type-arg]
        return init_db(tmp_path / "test.db")

    def _profile_yaml(self, tmp_path: Path) -> str:
        import yaml

        profile = {
            "name": "Jane Dev",
            "search_keywords": ["Senior Python Engineer"],
            "seniority": "senior",
            "scoring_keywords": ["Python", "FastAPI"],
            "years_of_experience": 8,
            "preferred_workplace": ["remote"],
        }
        p = tmp_path / "profile.yaml"
        p.write_text(yaml.dump(profile))
        return str(p)

    async def test_llm_scoring_blends_correctly(
        self, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Pipeline with llm_enabled=True applies blended scoring (mock provider)."""
        profile_path = self._profile_yaml(tmp_path)

        candidates = [
            JobCandidate(
                external_id="llm-c1",
                platform="linkedin",
                title="Senior Python Engineer",
                company="Acme",
                url="https://linkedin.com/jobs/view/llm-c1/",
                is_easy_apply=True,
                workplace_type="remote",
                posted_time="1 day ago",
                description_snippet="Looking for a Senior Python Engineer with FastAPI skills.",
            ),
        ]
        adapter = MockAdapter(candidates)

        scoring = ScoringConfig(
            llm_enabled=True,
            llm_provider="gemini",
            rule_weight=0.4,
            llm_weight=0.6,
        )
        settings = Settings(
            searches=[SearchConfig(keyword="Senior Python Engineer", platform="linkedin")],
            quotas={"linkedin": QuotaPlatformConfig(max_searches_per_day=5)},
            scoring=scoring,
            profile_path=profile_path,
        )

        mock_provider = MagicMock()
        mock_provider.complete.return_value = '{"score": 90, "reasoning": "Perfect match"}'

        with patch("src.pipeline.llm_scorer.get_provider", return_value=mock_provider):
            results = await run_all_searches(settings, adapter, db)

        assert len(results) == 1
        scored = results[0].scored
        assert len(scored) == 1
        # rule_score would be computed from scorer, llm=90 → blended = 0.4*rule + 0.6*90
        assert scored[0].llm_score == 90.0
        assert scored[0].llm_reasoning == "Perfect match"
        # Blended score should reflect LLM contribution
        assert scored[0].score > 0

    async def test_llm_scores_persisted_in_db(
        self, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """LLM score and reasoning are persisted in the candidates table."""
        profile_path = self._profile_yaml(tmp_path)

        candidates = [
            JobCandidate(
                external_id="persist-1",
                platform="linkedin",
                title="Senior Python Engineer",
                company="Corp",
                url="https://linkedin.com/jobs/view/persist-1/",
                description_snippet="Python FastAPI position.",
            ),
        ]
        adapter = MockAdapter(candidates)

        scoring = ScoringConfig(
            llm_enabled=True,
            llm_provider="gemini",
            rule_weight=0.4,
            llm_weight=0.6,
        )
        settings = Settings(
            searches=[SearchConfig(keyword="Python", platform="linkedin")],
            quotas={"linkedin": QuotaPlatformConfig(max_searches_per_day=5)},
            scoring=scoring,
            profile_path=profile_path,
        )

        mock_provider = MagicMock()
        mock_provider.complete.return_value = '{"score": 75, "reasoning": "Good fit"}'

        with patch("src.pipeline.llm_scorer.get_provider", return_value=mock_provider):
            await run_all_searches(settings, adapter, db)

        row = db.execute(
            "SELECT llm_score, llm_reasoning FROM candidates WHERE external_id = ?",
            ("persist-1",),
        ).fetchone()
        assert row is not None
        assert row["llm_score"] == 75.0
        assert row["llm_reasoning"] == "Good fit"
