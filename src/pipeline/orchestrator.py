"""Orchestrator: wires quota, adapter, filter chain, scorer, and DB write.

Data flow (ARCHITECTURE.md section 5):
  1. Quota gate (L11: before search)
  2. Adapter search → raw candidates
  3. Filter chain → filtered candidates
  4. Scorer → scored candidates
  5. DB upsert
  6. Record quota
"""

import json
import logging
import sqlite3
from datetime import datetime

from src.core.config import SearchConfig, Settings
from src.core.db import insert_search_run, upsert_candidate
from src.core.schemas import ScoredCandidate
from src.pipeline.matcher import (
    AlreadySeenFilter,
    DeduplicationFilter,
    ExcludeKeywordsFilter,
    Filter,
    PositiveKeywordsFilter,
    run_filter_chain,
)
from src.pipeline.quota_manager import QuotaManager
from src.pipeline.scorer import score_candidates
from src.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)


class SearchResult:
    """Summary of a single keyword search execution."""

    def __init__(
        self,
        keyword: str,
        platform: str,
        raw_count: int,
        filtered_count: int,
        new_count: int,
        scored: list[ScoredCandidate],
    ) -> None:
        self.keyword = keyword
        self.platform = platform
        self.raw_count = raw_count
        self.filtered_count = filtered_count
        self.new_count = new_count
        self.scored = scored


async def run_search(
    search_config: SearchConfig,
    adapter: PlatformAdapter,
    conn: sqlite3.Connection,
    quota_manager: QuotaManager,
    settings: Settings,
    dedup_filter: DeduplicationFilter,
) -> SearchResult | None:
    """Execute a single keyword search through the full pipeline.

    Returns SearchResult on success, None if quota blocked.
    """
    platform = search_config.platform
    keyword = search_config.keyword

    # Step 1: Quota gate (L11)
    if not quota_manager.can_search(platform):
        logger.info("Quota exhausted for '%s' — skipping '%s'", platform, keyword)
        return None

    started_at = datetime.now()

    # Step 2: Adapter search
    logger.info("Searching '%s' on %s", keyword, platform)
    raw_candidates = await adapter.search(search_config)
    logger.info("Raw candidates: %d", len(raw_candidates))

    # Step 3: Filter chain
    filters = _build_filters(search_config, conn, dedup_filter)
    filtered = run_filter_chain(raw_candidates, filters)
    logger.info("After filtering: %d", len(filtered))

    # Step 4: Score
    scored = score_candidates(
        filtered,
        settings.scoring,
        require_keywords=search_config.require_keywords or None,
        scoring_keywords=search_config.scoring_keywords or None,
    )

    # Step 5: DB upsert
    new_count = 0
    for s in scored:
        if upsert_candidate(conn, s):
            new_count += 1

    # Step 6: Record quota
    quota_manager.record_search(platform)
    quota_manager.record_candidates(platform, new_count)

    finished_at = datetime.now()

    # Record search run
    insert_search_run(
        conn,
        platform=platform,
        keyword=keyword,
        filters_json=search_config.filters.model_dump_json(),
        raw_count=len(raw_candidates),
        filtered_count=len(filtered),
        started_at=started_at,
        finished_at=finished_at,
    )

    logger.info(
        "Search '%s': %d raw, %d filtered, %d new",
        keyword, len(raw_candidates), len(filtered), new_count,
    )

    return SearchResult(
        keyword=keyword,
        platform=platform,
        raw_count=len(raw_candidates),
        filtered_count=len(filtered),
        new_count=new_count,
        scored=scored,
    )


async def run_all_searches(
    settings: Settings,
    adapter: PlatformAdapter,
    conn: sqlite3.Connection,
) -> list[SearchResult]:
    """Run all configured searches through the pipeline.

    Returns list of SearchResult (one per keyword that executed).
    """
    quota_manager = QuotaManager(conn, settings.quotas)
    dedup_filter = DeduplicationFilter()
    results: list[SearchResult] = []

    for search_config in settings.searches:
        result = await run_search(
            search_config, adapter, conn, quota_manager, settings, dedup_filter,
        )
        if result is not None:
            results.append(result)

    return results


def export_results_json(results: list[SearchResult]) -> str:
    """Export search results as a JSON string."""
    data = []
    for r in results:
        for s in r.scored:
            c = s.candidate
            data.append({
                "keyword": r.keyword,
                "external_id": c.external_id,
                "platform": c.platform,
                "title": c.title,
                "company": c.company,
                "location": c.location,
                "url": c.url,
                "is_easy_apply": c.is_easy_apply,
                "workplace_type": c.workplace_type,
                "posted_time": c.posted_time,
                "description_snippet": c.description_snippet,
                "score": s.score,
            })
    return json.dumps(data, indent=2)


def _build_filters(
    config: SearchConfig,
    conn: sqlite3.Connection,
    dedup_filter: DeduplicationFilter,
) -> list[Filter]:
    """Build the filter chain for a search config (L9 order)."""
    filters: list[Filter] = [
        ExcludeKeywordsFilter(config.exclude_keywords),
        PositiveKeywordsFilter(config.require_keywords),
        dedup_filter,
        AlreadySeenFilter(conn),
    ]
    return filters
