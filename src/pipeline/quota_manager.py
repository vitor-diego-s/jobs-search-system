"""Quota manager: daily gate enforcement for searches and candidates.

Quota state lives in SQLite (L11: gate before search, not just before apply).
Auto-resets when date changes — no explicit reset needed.
"""

import logging
import sqlite3

from src.core.config import QuotaPlatformConfig
from src.core.db import get_quota, update_quota

logger = logging.getLogger(__name__)


class QuotaManager:
    """Enforces daily search and candidate limits per platform.

    Usage::

        qm = QuotaManager(conn, {"linkedin": QuotaPlatformConfig(...)})
        if qm.can_search("linkedin"):
            ...  # do search
            qm.record_search("linkedin")
            qm.record_candidates("linkedin", count=25)
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        quotas: dict[str, QuotaPlatformConfig],
    ) -> None:
        self._conn = conn
        self._quotas = quotas

    def can_search(self, platform: str) -> bool:
        """Return True if the platform has not exceeded its daily search limit."""
        config = self._quotas.get(platform)
        if config is None:
            logger.debug("No quota config for '%s' - allowing search", platform)
            return True
        searches_run, _ = get_quota(self._conn, platform)
        allowed = searches_run < config.max_searches_per_day
        if not allowed:
            logger.info(
                "Quota reached for '%s': %d/%d searches today",
                platform, searches_run, config.max_searches_per_day,
            )
        return allowed

    def remaining_candidates(self, platform: str) -> int:
        """Return how many more candidates can be stored today for this platform."""
        config = self._quotas.get(platform)
        if config is None:
            return 999_999  # No limit configured
        _, candidates_found = get_quota(self._conn, platform)
        return max(0, config.max_candidates_per_day - candidates_found)

    def record_search(self, platform: str) -> None:
        """Increment the search counter for today."""
        update_quota(self._conn, platform, searches_delta=1)
        logger.debug("Recorded search for '%s'", platform)

    def record_candidates(self, platform: str, count: int) -> None:
        """Increment the candidate counter for today."""
        update_quota(self._conn, platform, candidates_delta=count)
        logger.debug("Recorded %d candidates for '%s'", count, platform)
