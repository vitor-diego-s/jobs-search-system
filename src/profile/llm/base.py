"""Abstract base class for LLM providers and shared logic."""

import json
import re
from abc import ABC, abstractmethod

from src.profile.schema import ProfileData

SYSTEM_PROMPT = (
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


def parse_response(raw_text: str) -> ProfileData:
    """Parse an LLM response text into ProfileData.

    Handles markdown-wrapped JSON (```json ... ```) and plain JSON.
    """
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        msg = f"Failed to parse LLM response as JSON: {e}"
        raise ValueError(msg) from e

    return ProfileData.model_validate(data)


class LLMProvider(ABC):
    """Base class that every LLM provider must implement."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'anthropic')."""

    @abstractmethod
    def complete(
        self,
        resume_text: str,
        model: str | None = None,
        *,
        system: str | None = None,
    ) -> str:
        """Send resume text to the LLM and return raw response text.

        Args:
            resume_text: Plain text extracted from a resume PDF.
            model: Override the provider's default model. None uses default.
            system: Override the system prompt. None falls back to SYSTEM_PROMPT.

        Returns:
            Raw text response from the LLM (expected to be JSON).
        """

    @property
    @abstractmethod
    def default_model(self) -> str:
        """The default model ID used when no override is specified."""

    @property
    @abstractmethod
    def env_var(self) -> str | None:
        """Environment variable name for the API key, or None if not needed."""
