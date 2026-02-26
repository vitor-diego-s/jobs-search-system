"""Resume analysis facade — delegates to pluggable LLM providers.

Backward-compatible: existing code that calls ``analyze_resume(text)``
continues to work (defaults to Anthropic). The ``_parse_response`` name
is re-exported so existing tests don't break.
"""

import logging

from src.profile.llm import get_provider, parse_response
from src.profile.schema import ProfileData

logger = logging.getLogger(__name__)

# Backward-compat alias used by tests/unit/test_llm_analyzer.py
_parse_response = parse_response


def analyze_resume(
    resume_text: str,
    model: str | None = None,
    provider: str = "anthropic",
) -> ProfileData:
    """Analyze resume text using an LLM provider and return a ProfileData.

    Args:
        resume_text: Plain text extracted from a resume PDF.
        model: Override the provider's default model. None uses the default.
        provider: LLM provider name (anthropic, openai, gemini, ollama).

    Returns:
        ProfileData with extracted fields.

    Raises:
        ValueError: If credentials are missing or response is malformed.
        ImportError: If the provider's SDK is not installed.
    """
    llm = get_provider(provider)
    logger.info("Using LLM provider: %s", llm.provider_id)
    raw_text = llm.complete(resume_text, model=model)
    return parse_response(raw_text)
