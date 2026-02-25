"""Tests for the database layer: init, upsert, dedup, seen check, quota."""

from datetime import date, datetime, timedelta

import pytest

from src.core.db import (
    get_quota,
    init_db,
    insert_search_run,
    is_candidate_seen,
    update_quota,
    upsert_candidate,
)
from src.core.schemas import JobCandidate, ScoredCandidate


def _scored(external_id: str = "123", platform: str = "linkedin", **kw: object) -> ScoredCandidate:
    defaults: dict[str, object] = {
        "external_id": external_id,
        "platform": platform,
        "title": "Engineer",
        "url": f"https://example.com/{external_id}",
        "found_at": datetime.now(),
    }
    defaults.update(kw)
    return ScoredCandidate(candidate=JobCandidate(**defaults), score=50.0)  # type: ignore[arg-type]


@pytest.fixture()
def db(tmp_path):  # type: ignore[no-untyped-def]
    """Provide a fresh in-memory-like SQLite connection per test."""
    return init_db(tmp_path / "test.db")


class TestInitDb:
    def test_creates_tables(self, db) -> None:  # type: ignore[no-untyped-def]
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "candidates" in tables
        assert "quota" in tables
        assert "search_runs" in tables

    def test_idempotent(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Calling init_db twice on the same path doesn't error."""
        p = tmp_path / "double.db"
        conn1 = init_db(p)
        conn1.close()
        conn2 = init_db(p)
        conn2.close()


class TestUpsertCandidate:
    def test_insert_new(self, db) -> None:  # type: ignore[no-untyped-def]
        assert upsert_candidate(db, _scored("1")) is True

    def test_duplicate_ignored(self, db) -> None:  # type: ignore[no-untyped-def]
        upsert_candidate(db, _scored("1"))
        assert upsert_candidate(db, _scored("1")) is False
        count = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        assert count == 1

    def test_different_ids_both_inserted(self, db) -> None:  # type: ignore[no-untyped-def]
        upsert_candidate(db, _scored("1"))
        upsert_candidate(db, _scored("2"))
        count = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        assert count == 2

    def test_same_id_different_platform(self, db) -> None:  # type: ignore[no-untyped-def]
        upsert_candidate(db, _scored("1", platform="linkedin"))
        assert upsert_candidate(db, _scored("1", platform="glassdoor")) is True
        count = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        assert count == 2

    def test_score_stored(self, db) -> None:  # type: ignore[no-untyped-def]
        sc = ScoredCandidate(
            candidate=JobCandidate(
                external_id="99",
                platform="linkedin",
                title="Dev",
                url="https://example.com/99",
            ),
            score=87.5,
        )
        upsert_candidate(db, sc)
        row = db.execute("SELECT score FROM candidates WHERE external_id = '99'").fetchone()
        assert row["score"] == 87.5


class TestIsCandidateSeen:
    def test_not_seen_when_empty(self, db) -> None:  # type: ignore[no-untyped-def]
        assert is_candidate_seen(db, "1", "linkedin") is False

    def test_seen_after_insert(self, db) -> None:  # type: ignore[no-untyped-def]
        upsert_candidate(db, _scored("1"))
        assert is_candidate_seen(db, "1", "linkedin") is True

    def test_not_seen_different_platform(self, db) -> None:  # type: ignore[no-untyped-def]
        upsert_candidate(db, _scored("1", platform="linkedin"))
        assert is_candidate_seen(db, "1", "glassdoor") is False

    def test_expired_ttl(self, db) -> None:  # type: ignore[no-untyped-def]
        old_time = datetime.now() - timedelta(days=60)
        upsert_candidate(db, _scored("1", found_at=old_time))
        assert is_candidate_seen(db, "1", "linkedin", ttl_days=30) is False

    def test_within_ttl(self, db) -> None:  # type: ignore[no-untyped-def]
        recent_time = datetime.now() - timedelta(days=5)
        upsert_candidate(db, _scored("1", found_at=recent_time))
        assert is_candidate_seen(db, "1", "linkedin", ttl_days=30) is True


class TestQuota:
    def test_default_zero(self, db) -> None:  # type: ignore[no-untyped-def]
        searches, candidates = get_quota(db, "linkedin")
        assert searches == 0
        assert candidates == 0

    def test_increment_searches(self, db) -> None:  # type: ignore[no-untyped-def]
        update_quota(db, "linkedin", searches_delta=1)
        searches, candidates = get_quota(db, "linkedin")
        assert searches == 1
        assert candidates == 0

    def test_increment_candidates(self, db) -> None:  # type: ignore[no-untyped-def]
        update_quota(db, "linkedin", candidates_delta=25)
        searches, candidates = get_quota(db, "linkedin")
        assert searches == 0
        assert candidates == 25

    def test_multiple_increments(self, db) -> None:  # type: ignore[no-untyped-def]
        update_quota(db, "linkedin", searches_delta=1, candidates_delta=10)
        update_quota(db, "linkedin", searches_delta=1, candidates_delta=15)
        searches, candidates = get_quota(db, "linkedin")
        assert searches == 2
        assert candidates == 25

    def test_different_dates_isolated(self, db) -> None:  # type: ignore[no-untyped-def]
        today = date.today()
        yesterday = today - timedelta(days=1)
        update_quota(db, "linkedin", searches_delta=3, target_date=yesterday)
        update_quota(db, "linkedin", searches_delta=1, target_date=today)
        assert get_quota(db, "linkedin", target_date=yesterday) == (3, 0)
        assert get_quota(db, "linkedin", target_date=today) == (1, 0)

    def test_different_platforms_isolated(self, db) -> None:  # type: ignore[no-untyped-def]
        update_quota(db, "linkedin", searches_delta=5)
        update_quota(db, "glassdoor", searches_delta=2)
        assert get_quota(db, "linkedin") == (5, 0)
        assert get_quota(db, "glassdoor") == (2, 0)


class TestInsertSearchRun:
    def test_insert_and_return_id(self, db) -> None:  # type: ignore[no-untyped-def]
        now = datetime.now()
        row_id = insert_search_run(
            db,
            platform="linkedin",
            keyword="Python",
            filters_json="{}",
            raw_count=50,
            filtered_count=12,
            started_at=now,
            finished_at=now,
        )
        assert row_id >= 1
        row = db.execute("SELECT * FROM search_runs WHERE id = ?", (row_id,)).fetchone()
        assert row["keyword"] == "Python"
        assert row["raw_count"] == 50
