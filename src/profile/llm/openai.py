"""OpenAI LLM provider."""

import logging
import os

from src.profile.llm.base import SYSTEM_PROMPT, LLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI API."""

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return "gpt-4o-mini"

    @property
    def env_var(self) -> str:
        return "OPENAI_API_KEY"

    def complete(
        self,
        resume_text: str,
        model: str | None = None,
        *,
        system: str | None = None,
    ) -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            msg = "OPENAI_API_KEY environment variable is required"
            raise ValueError(msg)

        try:
            import openai
        except ImportError:
            msg = (
                "openai is required for LLM analysis. "
                "Install with: pip install 'jobs-search-engine[openai]'"
            )
            raise ImportError(msg) from None

        client = openai.OpenAI(api_key=api_key)
        use_model = model or self.default_model
        use_system = system if system is not None else SYSTEM_PROMPT

        logger.info("Sending resume to OpenAI API (%s)...", use_model)
        response = client.chat.completions.create(
            model=use_model,
            messages=[
                {"role": "system", "content": use_system},
                {"role": "user", "content": resume_text},
            ],
        )

        return response.choices[0].message.content  # type: ignore[no-any-return]
