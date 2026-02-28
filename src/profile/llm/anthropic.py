"""Anthropic Claude LLM provider."""

import logging
import os

from src.profile.llm.base import SYSTEM_PROMPT, LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic Claude API."""

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    @property
    def env_var(self) -> str:
        return "ANTHROPIC_API_KEY"

    def complete(
        self,
        resume_text: str,
        model: str | None = None,
        *,
        system: str | None = None,
    ) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            msg = "ANTHROPIC_API_KEY environment variable is required"
            raise ValueError(msg)

        try:
            import anthropic
        except ImportError:
            msg = (
                "anthropic is required for LLM analysis. "
                "Install with: pip install 'jobs-search-engine[anthropic]'"
            )
            raise ImportError(msg) from None

        client = anthropic.Anthropic(api_key=api_key)
        use_model = model or self.default_model
        use_system = system if system is not None else SYSTEM_PROMPT

        logger.info("Sending resume to Anthropic API (%s)...", use_model)
        message = client.messages.create(
            model=use_model,
            max_tokens=1024,
            system=use_system,
            messages=[{"role": "user", "content": resume_text}],
        )

        return message.content[0].text  # type: ignore[union-attr]
