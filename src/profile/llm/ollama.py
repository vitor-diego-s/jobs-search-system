"""Ollama local LLM provider (OpenAI-compatible API)."""

import logging

from src.profile.llm.base import SYSTEM_PROMPT, LLMProvider

logger = logging.getLogger(__name__)

_OLLAMA_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(LLMProvider):
    """LLM provider using a local Ollama instance via OpenAI-compatible API."""

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return "llama3"

    @property
    def env_var(self) -> None:
        return None

    def complete(self, resume_text: str, model: str | None = None) -> str:
        try:
            import openai
        except ImportError:
            msg = (
                "openai is required for Ollama (OpenAI-compatible API). "
                "Install with: pip install 'jobs-search-engine[openai]'"
            )
            raise ImportError(msg) from None

        client = openai.OpenAI(base_url=_OLLAMA_BASE_URL, api_key="ollama")
        use_model = model or self.default_model

        logger.info("Sending resume to Ollama (%s)...", use_model)
        response = client.chat.completions.create(
            model=use_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": resume_text},
            ],
        )

        return response.choices[0].message.content  # type: ignore[no-any-return]
