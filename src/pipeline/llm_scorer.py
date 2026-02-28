"""LLM-assisted relevance scoring for job candidates (M10)."""

import json
import logging
import re

from src.core.config import ScoringConfig
from src.core.schemas import JobCandidate, ScoredCandidate
from src.profile.llm import get_provider
from src.profile.llm.base import LLMProvider
from src.profile.schema import ProfileData

logger = logging.getLogger(__name__)

_SCORING_SYSTEM_PROMPT = (
    "You are a senior recruiter evaluating job-candidate fit.\n\n"
    "Given a candidate profile and a job listing, score how well the job matches "
    "the candidate on a 0-100 scale using this rubric:\n"
    "  90-100: Perfect fit — role, skills, seniority, and workplace all align\n"
    "  70-89:  Strong fit — minor gaps in 1-2 areas\n"
    "  50-69:  Moderate fit — some relevant experience but notable mismatches\n"
    "  30-49:  Weak fit — partial skill overlap but significant mismatches\n"
    "  0-29:   Poor fit — fundamentally misaligned role, stack, or seniority\n\n"
    "Evaluation criteria (in priority order):\n"
    "  1. Role alignment — does the job title/description match target roles?\n"
    "  2. Skills overlap — does the job require the candidate's core skills?\n"
    "  3. Seniority match — is the seniority level appropriate?\n"
    "  4. Workplace preference — remote/hybrid/onsite match?\n"
    "  5. Description relevance — any flags (stack mismatch, niche domain)?\n\n"
    'Return ONLY a JSON object (no markdown, no explanation):\n'
    '{"score": <integer 0-100>, "reasoning": "<1-2 sentence explanation>"}'
)


def _build_user_prompt(candidate: JobCandidate, profile: ProfileData) -> str:
    """Assemble the user prompt from profile and job data."""
    years = (
        str(profile.years_of_experience)
        if profile.years_of_experience is not None
        else "not specified"
    )
    workplace = (
        ", ".join(profile.preferred_workplace)
        if profile.preferred_workplace
        else "no preference"
    )
    skills = (
        ", ".join(profile.scoring_keywords) if profile.scoring_keywords else "not specified"
    )

    profile_section = (
        "CANDIDATE PROFILE\n"
        f"Name: {profile.name or 'not provided'}\n"
        f"Target roles: {', '.join(profile.search_keywords)}\n"
        f"Seniority: {profile.seniority}\n"
        f"Core skills: {skills}\n"
        f"Years of experience: {years}\n"
        f"Workplace preference: {workplace}\n"
    )

    job_section = (
        "JOB LISTING\n"
        f"Title: {candidate.title}\n"
        f"Company: {candidate.company or 'not provided'}\n"
        f"Location: {candidate.location or 'not provided'}\n"
        f"Workplace type: {candidate.workplace_type or 'not specified'}\n"
        f"Posted: {candidate.posted_time or 'not specified'}\n"
        f"Easy Apply: {'yes' if candidate.is_easy_apply else 'no'}\n"
    )

    if candidate.description_snippet:
        job_section += f"Description:\n{candidate.description_snippet}\n"

    return f"{profile_section}\n{job_section}"


def _parse_llm_score(raw_text: str) -> tuple[float, str]:
    """Parse LLM JSON response into (score, reasoning).

    Handles markdown-wrapped JSON. Clamps score to 0-100.
    Raises ValueError on malformed response.
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        msg = f"Failed to parse LLM score response as JSON: {e}"
        raise ValueError(msg) from e

    if "score" not in data:
        msg = "LLM response missing 'score' field"
        raise ValueError(msg)

    raw_score = float(data["score"])
    score = max(0.0, min(100.0, raw_score))
    reasoning = str(data.get("reasoning", ""))

    return score, reasoning


def score_candidate_llm(
    scored: ScoredCandidate,
    profile: ProfileData,
    config: ScoringConfig,
    provider: LLMProvider,
) -> ScoredCandidate:
    """Score a single candidate using LLM, blending with rule-based score.

    Skips candidates without description_snippet (returns original).
    On any LLM error, logs warning and returns the original scored candidate.
    """
    candidate = scored.candidate

    if not candidate.description_snippet:
        return scored

    try:
        prompt = _build_user_prompt(candidate, profile)
        raw = provider.complete(
            prompt, model=config.llm_model, system=_SCORING_SYSTEM_PROMPT
        )
        llm_score, reasoning = _parse_llm_score(raw)
    except Exception:
        logger.warning(
            "LLM scoring failed for '%s' (%s) — keeping rule-based score",
            candidate.title,
            candidate.external_id,
            exc_info=True,
        )
        return scored

    blended = round(config.rule_weight * scored.score + config.llm_weight * llm_score, 2)
    return ScoredCandidate(
        candidate=candidate,
        score=blended,
        llm_score=llm_score,
        llm_reasoning=reasoning,
    )


def score_candidates_llm(
    scored_list: list[ScoredCandidate],
    profile: ProfileData,
    config: ScoringConfig,
) -> list[ScoredCandidate]:
    """Apply LLM scoring to a batch of candidates.

    Returns the list unchanged if llm_enabled is False.
    Re-sorts by blended score descending after scoring.
    """
    if not config.llm_enabled:
        return scored_list

    provider = get_provider(config.llm_provider)
    result = [score_candidate_llm(s, profile, config, provider) for s in scored_list]
    return sorted(result, key=lambda s: s.score, reverse=True)
