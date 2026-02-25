"""Rule-based relevance scoring for job candidates.

Score range: 0-100 (clamped). Individual bonuses from ScoringConfig.
Recency adds a time-decay bonus based on posted_time text heuristics.
"""

import logging
import re

from src.core.config import ScoringConfig
from src.core.schemas import JobCandidate, ScoredCandidate

logger = logging.getLogger(__name__)

SENIORITY_KEYWORDS = ("senior", "staff", "principal", "lead", "director", "head", "vp")

# Maps posted_time text patterns to approximate days-ago.
_RECENCY_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"(\d+)\s*hour", re.IGNORECASE), 0.0),
    (re.compile(r"(\d+)\s*minute", re.IGNORECASE), 0.0),
    (re.compile(r"(\d+)\s*day", re.IGNORECASE), 1.0),
    (re.compile(r"(\d+)\s*week", re.IGNORECASE), 7.0),
    (re.compile(r"(\d+)\s*month", re.IGNORECASE), 30.0),
]


def score_candidate(
    candidate: JobCandidate,
    config: ScoringConfig,
    require_keywords: list[str] | None = None,
    scoring_keywords: list[str] | None = None,
) -> ScoredCandidate:
    """Score a single candidate using rule-based bonuses.

    Args:
        candidate: The job candidate to score.
        config: Scoring weights from settings.
        require_keywords: Optional keywords; each hit adds title_match_bonus.
        scoring_keywords: Optional keywords for score boost only (no hard filter).

    Returns:
        ScoredCandidate wrapping the original candidate with a score 0-100.
    """
    score = 0.0

    # Title keyword match bonus (require_keywords + scoring_keywords)
    all_keywords = list(require_keywords or []) + list(scoring_keywords or [])
    if all_keywords:
        title_lower = candidate.title.lower()
        for kw in all_keywords:
            if kw.lower().strip() in title_lower:
                score += config.title_match_bonus

    # Seniority match bonus
    title_lower = candidate.title.lower()
    if any(kw in title_lower for kw in SENIORITY_KEYWORDS):
        score += config.seniority_match_bonus

    # Easy apply bonus
    if candidate.is_easy_apply:
        score += config.easy_apply_bonus

    # Remote bonus
    if candidate.workplace_type.lower() in ("remote",):
        score += config.remote_bonus

    # Recency bonus (weighted by recency_weight)
    recency_bonus = _recency_score(candidate.posted_time, config.recency_weight)
    score += recency_bonus

    # Clamp to 0-100
    score = max(0.0, min(100.0, score))

    return ScoredCandidate(candidate=candidate, score=score)


def score_candidates(
    candidates: list[JobCandidate],
    config: ScoringConfig,
    require_keywords: list[str] | None = None,
    scoring_keywords: list[str] | None = None,
) -> list[ScoredCandidate]:
    """Score a batch of candidates, returning ScoredCandidate list sorted by score desc."""
    scored = [score_candidate(c, config, require_keywords, scoring_keywords) for c in candidates]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def _recency_score(posted_time: str, weight: float) -> float:
    """Estimate a recency bonus from posted_time text.

    Newer posts get higher bonuses. Max bonus = 10 * weight.
    """
    if not posted_time:
        return 0.0

    days_ago = _estimate_days_ago(posted_time)
    if days_ago is None:
        return 0.0

    # Decay: 10 points for today, decreasing to ~0 at 30+ days
    max_bonus = 10.0
    if days_ago <= 0:
        return max_bonus * weight
    decay = max(0.0, max_bonus - (days_ago / 3.0))
    return decay * weight


def _estimate_days_ago(posted_time: str) -> float | None:
    """Parse posted_time text into approximate days ago."""
    for pattern, multiplier in _RECENCY_PATTERNS:
        match = pattern.search(posted_time)
        if match:
            value = float(match.group(1))
            return value * multiplier
    return None
