"""Filter chain for candidate matching.

Filter order (L9):
  1. ExcludeKeywordsFilter  — fast, title-only, case-insensitive
  2. PositiveKeywordsFilter — optional, title OR snippet
  3. DeduplicationFilter    — in-memory within run, by (platform, external_id)
  4. AlreadySeenFilter      — DB lookup, persistent cross-run, TTL-aware
"""

import logging
import sqlite3
from collections.abc import Callable

from src.core.db import is_candidate_seen
from src.core.schemas import JobCandidate

logger = logging.getLogger(__name__)

# A filter is a callable that takes candidates and returns a subset.
Filter = Callable[[list[JobCandidate]], list[JobCandidate]]


class ExcludeKeywordsFilter:
    """Remove candidates whose title contains any excluded keyword (case-insensitive)."""

    def __init__(self, exclude_keywords: list[str]) -> None:
        self._keywords = [kw.lower().strip() for kw in exclude_keywords if kw.strip()]

    def __call__(self, candidates: list[JobCandidate]) -> list[JobCandidate]:
        if not self._keywords:
            return candidates
        result = [c for c in candidates if not self._title_matches(c.title)]
        excluded = len(candidates) - len(result)
        if excluded:
            logger.debug("ExcludeKeywordsFilter: removed %d candidates", excluded)
        return result

    def _title_matches(self, title: str) -> bool:
        title_lower = title.lower()
        return any(kw in title_lower for kw in self._keywords)


class PositiveKeywordsFilter:
    """Keep only candidates whose title OR snippet contains at least one required keyword.

    If require_keywords is empty, the filter is a no-op (passes all candidates through).
    """

    def __init__(self, require_keywords: list[str]) -> None:
        self._keywords = [kw.lower().strip() for kw in require_keywords if kw.strip()]

    def __call__(self, candidates: list[JobCandidate]) -> list[JobCandidate]:
        if not self._keywords:
            return candidates
        result = [c for c in candidates if self._matches(c)]
        excluded = len(candidates) - len(result)
        if excluded:
            logger.debug("PositiveKeywordsFilter: removed %d candidates", excluded)
        return result

    def _matches(self, candidate: JobCandidate) -> bool:
        text = f"{candidate.title} {candidate.description_snippet}".lower()
        return any(kw in text for kw in self._keywords)


class DeduplicationFilter:
    """Remove duplicates by (platform, external_id) within a single run.

    Stateful: tracks seen IDs across calls within the same filter instance.
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def __call__(self, candidates: list[JobCandidate]) -> list[JobCandidate]:
        result: list[JobCandidate] = []
        for c in candidates:
            key = (c.platform, c.external_id)
            if key not in self._seen:
                self._seen.add(key)
                result.append(c)
        deduped = len(candidates) - len(result)
        if deduped:
            logger.debug("DeduplicationFilter: removed %d duplicates", deduped)
        return result


class AlreadySeenFilter:
    """Remove candidates already stored in the DB within the TTL window (L10)."""

    def __init__(self, conn: sqlite3.Connection, ttl_days: int = 30) -> None:
        self._conn = conn
        self._ttl_days = ttl_days

    def __call__(self, candidates: list[JobCandidate]) -> list[JobCandidate]:
        result = [
            c for c in candidates
            if not is_candidate_seen(self._conn, c.external_id, c.platform, self._ttl_days)
        ]
        seen = len(candidates) - len(result)
        if seen:
            logger.debug("AlreadySeenFilter: removed %d already-seen candidates", seen)
        return result


def run_filter_chain(
    candidates: list[JobCandidate],
    filters: list[Filter],
) -> list[JobCandidate]:
    """Apply filters in order, returning the surviving candidates."""
    result = candidates
    for f in filters:
        result = f(result)
    return result
