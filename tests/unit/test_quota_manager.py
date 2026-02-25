"""Tests for QuotaManager: gate enforcement, recording, daily reset."""

import sqlite3
from datetime import date, timedelta

import pytest

from src.core.config import QuotaPlatformConfig
from src.core.db import init_db, update_quota
from src.pipeline.quota_manager import QuotaManager


@pytest.fixture
def db(tmp_path: pytest.TempPathFactory) -> sqlite3.Connection:  # type: ignore[type-arg]
    return init_db(tmp_path / "test.db")


def _qm(db: sqlite3.Connection, **kwargs: int) -> QuotaManager:
    """Create a QuotaManager with a single linkedin platform config."""
    config = QuotaPlatformConfig(
        max_searches_per_day=kwargs.get("max_searches", 2),
        max_candidates_per_day=kwargs.get("max_candidates", 150),
    )
    return QuotaManager(db, {"linkedin": config})


# ---------------------------------------------------------------------------
# can_search
# ---------------------------------------------------------------------------


class TestCanSearch:
    def test_allowed_when_empty(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_searches=2)
        assert qm.can_search("linkedin") is True

    def test_allowed_after_one_search(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_searches=2)
        qm.record_search("linkedin")
        assert qm.can_search("linkedin") is True

    def test_blocked_at_limit(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_searches=2)
        qm.record_search("linkedin")
        qm.record_search("linkedin")
        assert qm.can_search("linkedin") is False

    def test_unknown_platform_allowed(self, db: sqlite3.Connection) -> None:
        """Platform with no quota config is always allowed."""
        qm = _qm(db)
        assert qm.can_search("glassdoor") is True

    def test_different_platforms_isolated(self, db: sqlite3.Connection) -> None:
        config = {
            "linkedin": QuotaPlatformConfig(max_searches_per_day=1),
            "glassdoor": QuotaPlatformConfig(max_searches_per_day=1),
        }
        qm = QuotaManager(db, config)
        qm.record_search("linkedin")
        assert qm.can_search("linkedin") is False
        assert qm.can_search("glassdoor") is True


# ---------------------------------------------------------------------------
# remaining_candidates
# ---------------------------------------------------------------------------


class TestRemainingCandidates:
    def test_full_remaining_when_empty(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_candidates=150)
        assert qm.remaining_candidates("linkedin") == 150

    def test_decreases_after_recording(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_candidates=150)
        qm.record_candidates("linkedin", 50)
        assert qm.remaining_candidates("linkedin") == 100

    def test_zero_when_at_limit(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_candidates=100)
        qm.record_candidates("linkedin", 100)
        assert qm.remaining_candidates("linkedin") == 0

    def test_never_negative(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_candidates=50)
        qm.record_candidates("linkedin", 999)
        assert qm.remaining_candidates("linkedin") == 0

    def test_unknown_platform_large_remaining(self, db: sqlite3.Connection) -> None:
        qm = _qm(db)
        assert qm.remaining_candidates("glassdoor") == 999_999


# ---------------------------------------------------------------------------
# record_search / record_candidates
# ---------------------------------------------------------------------------


class TestRecording:
    def test_record_search_increments(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_searches=5)
        qm.record_search("linkedin")
        qm.record_search("linkedin")
        # 3rd search should still be allowed (limit is 5)
        assert qm.can_search("linkedin") is True

    def test_record_candidates_increments(self, db: sqlite3.Connection) -> None:
        qm = _qm(db, max_candidates=100)
        qm.record_candidates("linkedin", 30)
        qm.record_candidates("linkedin", 40)
        assert qm.remaining_candidates("linkedin") == 30


# ---------------------------------------------------------------------------
# Daily reset (date rollover)
# ---------------------------------------------------------------------------


class TestDailyReset:
    def test_yesterday_quota_does_not_affect_today(self, db: sqlite3.Connection) -> None:
        """Quota from yesterday doesn't block today's searches."""
        yesterday = date.today() - timedelta(days=1)
        # Seed yesterday's quota at the limit
        update_quota(db, "linkedin", searches_delta=2, target_date=yesterday)
        update_quota(db, "linkedin", candidates_delta=150, target_date=yesterday)

        qm = _qm(db, max_searches=2, max_candidates=150)
        # Today should be fresh
        assert qm.can_search("linkedin") is True
        assert qm.remaining_candidates("linkedin") == 150

    def test_today_quota_blocks_correctly(self, db: sqlite3.Connection) -> None:
        """After filling today's quota, gate blocks."""
        qm = _qm(db, max_searches=1)
        qm.record_search("linkedin")
        assert qm.can_search("linkedin") is False
