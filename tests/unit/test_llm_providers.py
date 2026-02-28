"""Tests for LLM provider adapter pattern and registry."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.profile.llm import available_providers, get_provider, parse_response
from src.profile.llm.base import LLMProvider

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_sample_response() -> str:
    return (FIXTURES_DIR / "sample_llm_response.json").read_text()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestProviderRegistry:
    def test_get_anthropic(self) -> None:
        provider = get_provider("anthropic")
        assert isinstance(provider, LLMProvider)
        assert provider.provider_id == "anthropic"

    def test_get_openai(self) -> None:
        provider = get_provider("openai")
        assert isinstance(provider, LLMProvider)
        assert provider.provider_id == "openai"

    def test_get_gemini(self) -> None:
        provider = get_provider("gemini")
        assert isinstance(provider, LLMProvider)
        assert provider.provider_id == "gemini"

    def test_get_ollama(self) -> None:
        provider = get_provider("ollama")
        assert isinstance(provider, LLMProvider)
        assert provider.provider_id == "ollama"

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM provider 'nope'"):
            get_provider("nope")

    def test_available_providers_sorted(self) -> None:
        providers = available_providers()
        assert providers == ["anthropic", "gemini", "ollama", "openai"]


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------
class TestAnthropicProvider:
    def test_provider_id(self) -> None:
        provider = get_provider("anthropic")
        assert provider.provider_id == "anthropic"
        assert provider.default_model == "claude-sonnet-4-20250514"
        assert provider.env_var == "ANTHROPIC_API_KEY"

    def test_missing_api_key(self) -> None:
        provider = get_provider("anthropic")
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
        ):
            provider.complete("resume text")

    def test_missing_sdk(self) -> None:
        provider = get_provider("anthropic")
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"anthropic": None}),
            pytest.raises(ImportError, match="anthropic is required"),
        ):
            provider.complete("resume text")


# ---------------------------------------------------------------------------
# OpenAI provider tests
# ---------------------------------------------------------------------------
class TestOpenAIProvider:
    def test_provider_id(self) -> None:
        provider = get_provider("openai")
        assert provider.provider_id == "openai"
        assert provider.default_model == "gpt-4o-mini"
        assert provider.env_var == "OPENAI_API_KEY"

    def test_missing_api_key(self) -> None:
        provider = get_provider("openai")
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="OPENAI_API_KEY"),
        ):
            provider.complete("resume text")

    def test_missing_sdk(self) -> None:
        provider = get_provider("openai")
        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"openai": None}),
            pytest.raises(ImportError, match="openai is required"),
        ):
            provider.complete("resume text")


# ---------------------------------------------------------------------------
# Gemini provider tests
# ---------------------------------------------------------------------------
class TestGeminiProvider:
    def test_provider_id(self) -> None:
        provider = get_provider("gemini")
        assert provider.provider_id == "gemini"
        assert provider.default_model == "gemini-2.0-flash"
        assert provider.env_var == "GOOGLE_API_KEY"

    def test_missing_api_key(self) -> None:
        provider = get_provider("gemini")
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="GOOGLE_API_KEY"),
        ):
            provider.complete("resume text")

    def test_missing_sdk(self) -> None:
        provider = get_provider("gemini")
        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"google.generativeai": None, "google": None}),
            pytest.raises(ImportError, match="google-generativeai is required"),
        ):
            provider.complete("resume text")


# ---------------------------------------------------------------------------
# Ollama provider tests
# ---------------------------------------------------------------------------
class TestOllamaProvider:
    def test_provider_id(self) -> None:
        provider = get_provider("ollama")
        assert provider.provider_id == "ollama"
        assert provider.default_model == "llama3"
        assert provider.env_var is None

    def test_missing_sdk(self) -> None:
        provider = get_provider("ollama")
        with (
            patch.dict("sys.modules", {"openai": None}),
            pytest.raises(ImportError, match="openai is required"),
        ):
            provider.complete("resume text")


# ---------------------------------------------------------------------------
# system kwarg tests (M10)
# ---------------------------------------------------------------------------
class TestCompleteSystemKwarg:
    """Verify each provider respects the system= kwarg (M10 extension)."""

    def test_anthropic_uses_custom_system(self) -> None:
        provider = get_provider("anthropic")
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="ok")]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}),
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        ):
            provider.complete("text", system="custom system prompt")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "custom system prompt"

    def test_anthropic_falls_back_to_system_prompt(self) -> None:
        from src.profile.llm.base import SYSTEM_PROMPT

        provider = get_provider("anthropic")
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="ok")]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}),
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        ):
            provider.complete("text")  # no system kwarg

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == SYSTEM_PROMPT

    def test_gemini_uses_custom_system(self) -> None:
        provider = get_provider("gemini")
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value.text = "ok"
        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model_instance

        # Patch only google.generativeai — sys.modules lookup returns mock_genai directly
        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "key"}),
            patch.dict("sys.modules", {"google.generativeai": mock_genai}),
        ):
            provider.complete("text", system="custom system prompt")

        mock_genai.GenerativeModel.assert_called_once()
        call_kwargs = mock_genai.GenerativeModel.call_args.kwargs
        assert call_kwargs["system_instruction"] == "custom system prompt"

    def test_openai_uses_custom_system(self) -> None:
        provider = get_provider("openai")
        mock_openai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "ok"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "key"}),
            patch.dict("sys.modules", {"openai": mock_openai}),
        ):
            provider.complete("text", system="custom system prompt")

        messages = mock_openai.OpenAI.return_value.chat.completions.create.call_args.kwargs[
            "messages"
        ]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == "custom system prompt"

    def test_ollama_uses_custom_system(self) -> None:
        provider = get_provider("ollama")
        mock_openai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "ok"
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict("sys.modules", {"openai": mock_openai}):
            provider.complete("text", system="custom system prompt")

        messages = mock_openai.OpenAI.return_value.chat.completions.create.call_args.kwargs[
            "messages"
        ]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == "custom system prompt"


# ---------------------------------------------------------------------------
# analyze_resume with provider tests
# ---------------------------------------------------------------------------
class TestAnalyzeResumeWithProvider:
    def test_mock_provider_roundtrip(self) -> None:
        """A mock provider returning valid JSON produces correct ProfileData."""
        from src.profile.llm_analyzer import analyze_resume

        sample = _load_sample_response()

        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.complete.return_value = sample
        mock_provider.provider_id = "mock"

        with patch("src.profile.llm_analyzer.get_provider", return_value=mock_provider):
            profile = analyze_resume("resume text", provider="mock")

        assert profile.name == "Jane Doe"
        assert profile.seniority == "senior"
        mock_provider.complete.assert_called_once_with("resume text", model=None)

    def test_default_provider_is_anthropic(self) -> None:
        """When no provider is specified, anthropic is used by default."""
        from src.profile.llm_analyzer import analyze_resume

        sample = _load_sample_response()

        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.complete.return_value = sample
        mock_provider.provider_id = "anthropic"

        with patch("src.profile.llm_analyzer.get_provider", return_value=mock_provider) as mock_get:
            analyze_resume("resume text")

        mock_get.assert_called_once_with("anthropic")


# ---------------------------------------------------------------------------
# Shared parse_response tests (re-exported)
# ---------------------------------------------------------------------------
class TestParseResponseShared:
    def test_parse_valid_json(self) -> None:
        raw = _load_sample_response()
        profile = parse_response(raw)
        assert profile.name == "Jane Doe"

    def test_parse_malformed_json(self) -> None:
        with pytest.raises(ValueError, match="Failed to parse LLM response"):
            parse_response("not json {{{")

    def test_backward_compat_alias(self) -> None:
        """The _parse_response alias still works for existing tests."""
        from src.profile.llm_analyzer import _parse_response

        raw = _load_sample_response()
        profile = _parse_response(raw)
        assert profile.name == "Jane Doe"
