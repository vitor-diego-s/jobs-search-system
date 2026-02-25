"""CLI entry point for the jobs search engine."""

import argparse
import asyncio
import logging
import sys

from src.browser.session import BrowserSession
from src.core.config import Settings
from src.core.db import init_db
from src.pipeline.orchestrator import export_results_json, run_all_searches
from src.pipeline.quota_manager import QuotaManager
from src.platforms.linkedin.adapter import LinkedInAdapter


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jobs search engine - search multiple platforms and store candidates",
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings YAML file (default: config/settings.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without launching a browser",
    )
    parser.add_argument(
        "--export",
        choices=["json"],
        help="Export results to format (json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return parser.parse_args(argv)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def dry_run(settings: Settings) -> None:
    """Print what would happen without actually searching."""
    conn = init_db(settings.database.path)
    quota_manager = QuotaManager(conn, settings.quotas)

    print(f"[DRY RUN] {len(settings.searches)} searches configured")

    for search in settings.searches:
        platform = search.platform
        can = quota_manager.can_search(platform)
        remaining = quota_manager.remaining_candidates(platform)
        status = "OK" if can else "BLOCKED"
        print(f"[DRY RUN] '{search.keyword}' on {platform}: quota {status}")
        if can:
            print(f"  Filters: {search.filters.model_dump()}")
            print(f"  Exclude: {search.exclude_keywords}")
            print(f"  Max pages: {search.filters.max_pages}")
            print(f"  Remaining candidate slots: {remaining}")

    print("[DRY RUN] Would write 0 candidates (no browser in dry-run)")
    conn.close()


async def run(settings: Settings, export_format: str | None) -> None:
    """Run the full search pipeline with a real browser."""
    conn = init_db(settings.database.path)

    async with BrowserSession(settings.browser) as session:
        adapter = LinkedInAdapter(session.page)
        results = await run_all_searches(settings, adapter, conn)

    # Print summary
    total_raw = sum(r.raw_count for r in results)
    total_filtered = sum(r.filtered_count for r in results)
    total_new = sum(r.new_count for r in results)

    print(f"\nSearch complete: {total_raw} raw, {total_filtered} filtered, "
          f"{total_new} new candidates written to DB.")

    for r in results:
        print(f"  '{r.keyword}': {r.raw_count} raw, {r.filtered_count} filtered, "
              f"{r.new_count} new")

    # Export if requested
    if export_format == "json" and results:
        output = export_results_json(results)
        print(f"\n{output}")

    conn.close()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging(args.verbose)

    try:
        settings = Settings.from_yaml(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        dry_run(settings)
    else:
        asyncio.run(run(settings, args.export))


if __name__ == "__main__":
    main()
