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
    subparsers = parser.add_subparsers(dest="command")

    # --- search subcommand (default) ---
    search_parser = subparsers.add_parser("search", help="Run job searches")
    search_parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to settings YAML file (default: config/settings.yaml)",
    )
    search_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without launching a browser",
    )
    search_parser.add_argument(
        "--export",
        choices=["json"],
        help="Export results to format (json)",
    )
    search_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    # --- extract-profile subcommand ---
    extract_parser = subparsers.add_parser(
        "extract-profile",
        help="Extract profile data from a resume PDF using Claude API",
    )
    extract_parser.add_argument(
        "--resume",
        required=True,
        help="Path to resume PDF file",
    )
    extract_parser.add_argument(
        "--output",
        default="config/profile.yaml",
        help="Output path for profile YAML (default: config/profile.yaml)",
    )
    extract_parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "openai", "gemini", "ollama"],
        help="LLM provider for resume analysis (default: anthropic)",
    )
    extract_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    # --- generate-config subcommand ---
    generate_parser = subparsers.add_parser(
        "generate-config",
        help="Generate settings.yaml from a profile.yaml",
    )
    generate_parser.add_argument(
        "--profile",
        default="config/profile.yaml",
        help="Path to profile YAML (default: config/profile.yaml)",
    )
    generate_parser.add_argument(
        "--output",
        default="config/settings.yaml",
        help="Output path for settings YAML (default: config/settings.yaml)",
    )
    generate_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    # --- backward compat: top-level flags for search ---
    parser.add_argument("--config", default="config/settings.yaml", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--export", choices=["json"], help=argparse.SUPPRESS)
    parser.add_argument("--verbose", "-v", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    # Default to search when no subcommand given
    if args.command is None:
        args.command = "search"

    return args


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


def cmd_extract_profile(args: argparse.Namespace) -> None:
    """Handle extract-profile subcommand."""
    from src.profile.extractor import extract_text_from_pdf
    from src.profile.llm_analyzer import analyze_resume

    print(f"Extracting text from {args.resume}...")
    text = extract_text_from_pdf(args.resume)
    print(f"Extracted {len(text)} characters from PDF.")

    print(f"Analyzing resume with {args.provider} provider...")
    profile = analyze_resume(text, provider=args.provider)
    profile.to_yaml(args.output)
    print(f"Profile written to {args.output}")
    print(f"  Name: {profile.name}")
    print(f"  Seniority: {profile.seniority}")
    print(f"  Search keywords: {profile.search_keywords}")
    print(f"  Scoring keywords: {profile.scoring_keywords}")
    print("Review the profile and then run: python main.py generate-config")


def cmd_generate_config(args: argparse.Namespace) -> None:
    """Handle generate-config subcommand."""
    from src.profile.generator import generate_settings_dict, write_settings_yaml
    from src.profile.schema import ProfileData

    print(f"Loading profile from {args.profile}...")
    profile = ProfileData.from_yaml(args.profile)

    settings_dict = generate_settings_dict(profile)
    write_settings_yaml(settings_dict, args.output)
    print(f"Settings written to {args.output}")
    print(f"  {len(settings_dict['searches'])} search entries generated")
    print("Review the settings and then run: python main.py search")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    setup_logging(args.verbose)

    if args.command == "extract-profile":
        try:
            cmd_extract_profile(args)
        except (FileNotFoundError, ImportError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "generate-config":
        try:
            cmd_generate_config(args)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # search (default)
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
