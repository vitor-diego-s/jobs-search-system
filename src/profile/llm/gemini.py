"""Google Gemini LLM provider."""

import logging
import os

from src.profile.llm.base import SYSTEM_PROMPT, LLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """LLM provider using the Google Gemini API."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return "gemini-2.0-flash"

    @property
    def env_var(self) -> str:
        return "GOOGLE_API_KEY"

    def complete(self, resume_text: str, model: str | None = None) -> str:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            msg = "GOOGLE_API_KEY environment variable is required"
            raise ValueError(msg)

        try:
            import google.generativeai as genai
        except ImportError:
            msg = (
                "google-generativeai is required for LLM analysis. "
                "Install with: pip install 'jobs-search-engine[gemini]'"
            )
            raise ImportError(msg) from None

        genai.configure(api_key=api_key)
        use_model = model or self.default_model

        logger.info("Sending resume to Gemini API (%s)...", use_model)
        gen_model = genai.GenerativeModel(
            model_name=use_model,
            system_instruction=SYSTEM_PROMPT,
        )
        response = gen_model.generate_content(resume_text)

        return response.text  # type: ignore[no-any-return]
