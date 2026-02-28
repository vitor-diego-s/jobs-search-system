"""Google Gemini LLM provider (google-genai SDK)."""

import logging
import os

from src.profile.llm.base import SYSTEM_PROMPT, LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """LLM provider using the Google Gemini API (google-genai SDK)."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return "gemini-2.5-flash"

    @property
    def env_var(self) -> str:
        return "GOOGLE_API_KEY"

    def complete(
        self,
        resume_text: str,
        model: str | None = None,
        *,
        system: str | None = None,
    ) -> str:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            msg = "GOOGLE_API_KEY environment variable is required"
            raise ValueError(msg)

        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            msg = (
                "google-genai is required for LLM analysis. "
                "Install with: pip install 'jobs-search-engine[gemini]'"
            )
            raise ImportError(msg) from None

        use_model = model or self.default_model
        use_system = system if system is not None else SYSTEM_PROMPT

        logger.info("Sending to Gemini API (%s)...", use_model)
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=use_model,
            contents=resume_text,
            config=genai_types.GenerateContentConfig(
                system_instruction=use_system,
            ),
        )

        return response.text  # type: ignore[no-any-return]
