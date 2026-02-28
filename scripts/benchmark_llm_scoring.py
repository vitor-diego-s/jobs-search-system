#!/usr/bin/env python3
"""Benchmark LLM scoring providers against the same candidate set.

Loads candidates from DB (or a JSON fixture), scores them with two providers
(Gemini 2.0 Flash and Anthropic Opus 4.6 by default), and prints a comparison
table with agreement metrics.

Usage:
    python scripts/benchmark_llm_scoring.py
    python scripts/benchmark_llm_scoring.py --db data/candidates.db
    python scripts/benchmark_llm_scoring.py --limit 20
    python scripts/benchmark_llm_scoring.py --profile config/profile.yaml
"""

import argparse
import logging
import sqlite3
import statistics
import sys
from pathlib import Path

# Ensure project root is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ScoringConfig
from src.core.schemas import JobCandidate, ScoredCandidate
from src.pipeline.llm_scorer import score_candidate_llm
from src.profile.llm import get_provider
from src.profile.schema import ProfileData

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def _load_candidates_from_db(db_path: str, limit: int) -> list[JobCandidate]:
    """Load candidates with non-empty descriptions from SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT external_id, platform, title, company, location, url,
               is_easy_apply, workplace_type, posted_time, description_snippet,
               score, found_at
        FROM candidates
        WHERE description_snippet != ''
        ORDER BY score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()

    candidates = []
    for row in rows:
        from datetime import datetime

        candidates.append(
            JobCandidate(
                external_id=row["external_id"],
                platform=row["platform"],
                title=row["title"],
                company=row["company"],
                location=row["location"],
                url=row["url"],
                is_easy_apply=bool(row["is_easy_apply"]),
                workplace_type=row["workplace_type"],
                posted_time=row["posted_time"],
                description_snippet=row["description_snippet"],
                found_at=datetime.fromisoformat(row["found_at"]),
            )
        )

    return candidates


def _score_with_provider(
    candidates: list[JobCandidate],
    rule_scores: dict[str, float],
    profile: ProfileData,
    provider_id: str,
    model: str | None,
) -> dict[str, tuple[float | None, str]]:
    """Score all candidates with a provider. Returns {external_id: (llm_score, reasoning)}."""
    provider = get_provider(provider_id)
    config = ScoringConfig(
        llm_enabled=True,
        llm_provider=provider_id,
        llm_model=model,
        rule_weight=0.0,
        llm_weight=1.0,
    )
    results: dict[str, tuple[float | None, str]] = {}

    for c in candidates:
        rule_score = rule_scores.get(c.external_id, 0.0)
        scored = ScoredCandidate(candidate=c, score=rule_score)
        try:
            result = score_candidate_llm(scored, profile, config, provider)
            results[c.external_id] = (result.llm_score, result.llm_reasoning)
        except Exception as e:
            print(f"  [ERROR] {c.title[:40]}: {e}")
            results[c.external_id] = (None, "")

    return results


def _print_table(
    candidates: list[JobCandidate],
    rule_scores: dict[str, float],
    gemini_scores: dict[str, tuple[float | None, str]],
    opus_scores: dict[str, tuple[float | None, str]],
) -> None:
    """Print formatted comparison table."""
    header = f"{'Title':<45} {'Company':<20} {'Rule':>5} {'Gemini':>7} {'Opus':>7}"
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    for c in candidates:
        rule = rule_scores.get(c.external_id, 0.0)
        gem, gem_r = gemini_scores.get(c.external_id, (None, ""))
        op, op_r = opus_scores.get(c.external_id, (None, ""))

        title = c.title[:44]
        company = c.company[:19]
        gem_str = f"{gem:.0f}" if gem is not None else "ERR"
        op_str = f"{op:.0f}" if op is not None else "ERR"

        print(f"{title:<45} {company:<20} {rule:>5.1f} {gem_str:>7} {op_str:>7}")
        # Print reasoning truncated
        if gem_r:
            print(f"  Gemini: {gem_r[:100]}")
        if op_r:
            print(f"  Opus:   {op_r[:100]}")

    print("=" * len(header))


def _compute_agreement(
    candidates: list[JobCandidate],
    gemini_scores: dict[str, tuple[float | None, str]],
    opus_scores: dict[str, tuple[float | None, str]],
) -> None:
    """Compute and print agreement metrics between providers."""
    pairs: list[tuple[float, float]] = []
    for c in candidates:
        g, _ = gemini_scores.get(c.external_id, (None, ""))
        o, _ = opus_scores.get(c.external_id, (None, ""))
        if g is not None and o is not None:
            pairs.append((g, o))

    if not pairs:
        print("\nNo comparable scores to compute agreement metrics.")
        return

    diffs = [abs(g - o) for g, o in pairs]
    mad = statistics.mean(diffs)

    # Pearson correlation (manual, no numpy)
    gem_vals = [p[0] for p in pairs]
    opus_vals = [p[1] for p in pairs]
    n = len(pairs)
    if n > 1:
        gem_mean = statistics.mean(gem_vals)
        opus_mean = statistics.mean(opus_vals)
        numerator = sum((g - gem_mean) * (o - opus_mean) for g, o in pairs)
        gem_std = statistics.stdev(gem_vals)
        opus_std = statistics.stdev(opus_vals)
        corr = (
            numerator / ((n - 1) * gem_std * opus_std)
            if gem_std > 0 and opus_std > 0
            else 1.0
        )
    else:
        corr = float("nan")

    print(f"\nAgreement metrics (n={len(pairs)} scored pairs):")
    print(f"  Mean absolute difference: {mad:.1f} points")
    print(f"  Pearson correlation:      {corr:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LLM scoring providers")
    parser.add_argument("--db", default="data/candidates.db", help="SQLite DB path")
    parser.add_argument("--profile", default="config/profile.yaml", help="Profile YAML path")
    parser.add_argument("--limit", type=int, default=10, help="Max candidates to score")
    parser.add_argument(
        "--gemini-model", default=None, help="Gemini model override (default: gemini-2.0-flash)"
    )
    parser.add_argument(
        "--opus-model",
        default="claude-opus-4-6",
        help="Anthropic model (default: claude-opus-4-6)",
    )
    parser.add_argument(
        "--skip-opus", action="store_true", help="Skip Anthropic Opus scoring (saves cost)"
    )
    args = parser.parse_args()

    # Load profile
    print(f"Loading profile from {args.profile}...")
    profile = ProfileData.from_yaml(args.profile)
    print(f"  Profile: {profile.name or 'unnamed'}, seniority: {profile.seniority}")

    # Load candidates
    print(f"\nLoading candidates from {args.db} (limit={args.limit})...")
    if not Path(args.db).exists():
        print(f"ERROR: DB not found: {args.db}")
        sys.exit(1)

    candidates = _load_candidates_from_db(args.db, args.limit)
    if not candidates:
        print("No candidates with descriptions found. Run with fetch_description=true first.")
        sys.exit(0)
    print(f"  Loaded {len(candidates)} candidates with descriptions")

    # Rule scores (use 50.0 as placeholder since we don't re-run rule scorer here)
    rule_scores = {c.external_id: 50.0 for c in candidates}

    # Score with Gemini
    print(f"\nScoring with Gemini ({args.gemini_model or 'gemini-2.0-flash'})...")
    gemini_results = _score_with_provider(
        candidates, rule_scores, profile, "gemini", args.gemini_model
    )

    # Score with Opus
    if args.skip_opus:
        opus_results = {c.external_id: (None, "(skipped)") for c in candidates}
    else:
        print(f"\nScoring with Anthropic ({args.opus_model})...")
        opus_results = _score_with_provider(
            candidates, rule_scores, profile, "anthropic", args.opus_model
        )

    # Print table
    _print_table(candidates, rule_scores, gemini_results, opus_results)

    # Agreement metrics
    if not args.skip_opus:
        _compute_agreement(candidates, gemini_results, opus_results)

    print("\nDone.")


if __name__ == "__main__":
    main()
