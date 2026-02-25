"""Claude API-based resume analysis to extract ProfileData."""

import json
import logging
import os
import re

from src.profile.schema import ProfileData

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a resume analyzer. Extract structured professional data "
    "from the resume text provided.\n\n"
    "Return ONLY a JSON object (no markdown, no explanation) with these fields:\n"
    '- name (string): the candidate\'s full name\n'
    "- search_keywords (list[str]): 3-8 job search queries the person would use\n"
    '- seniority (string): one of "junior", "mid", "senior", "staff", '
    '"principal", "director"\n'
    "- scoring_keywords (list[str]): 5-15 technical skills and technologies\n"
    "- exclude_keywords (list[str]): 3-8 keywords for jobs to exclude\n"
    "- years_of_experience (int or null): total years of professional experience\n"
    "- preferred_workplace (list[str]): workplace preferences if mentioned. "
    "Empty list if not stated.\n"
    "- preferred_geo_ids (list[int]): LinkedIn geo IDs if specific locations "
    "mentioned. Empty list if not stated.\n\n"
    "Infer seniority from years of experience and titles held. "
    "For exclude_keywords, include technologies and roles that don't match "
    "the candidate's profile."
)


def analyze_resume(resume_text: str, model: str = "claude-sonnet-4-20250514") -> ProfileData:
    """Analyze resume text using Claude API and return a ProfileData.

    Args:
        resume_text: Plain text extracted from a resume PDF.
        model: Claude model to use for analysis.

    Returns:
        ProfileData with extracted fields.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set or response is malformed.
        ImportError: If anthropic SDK is not installed.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        msg = "ANTHROPIC_API_KEY environment variable is required"
        raise ValueError(msg)

    try:
        import anthropic
    except ImportError:
        msg = (
            "anthropic is required for LLM analysis. "
            "Install with: pip install 'jobs-search-engine[profile]'"
        )
        raise ImportError(msg) from None

    client = anthropic.Anthropic(api_key=api_key)

    logger.info("Sending resume to Claude API (%s)...", model)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": resume_text}],
    )

    raw_text = message.content[0].text
    return _parse_response(raw_text)


def _parse_response(raw_text: str) -> ProfileData:
    """Parse Claude's response text into ProfileData.

    Handles markdown-wrapped JSON (```json ... ```) and plain JSON.
    """
    # Strip markdown code fencing if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        msg = f"Failed to parse LLM response as JSON: {e}"
        raise ValueError(msg) from e

    return ProfileData.model_validate(data)
