"""Tests for Claude API-based resume analyzer."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.profile.llm_analyzer import _parse_response, analyze_resume

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_sample_response() -> str:
    return (FIXTURES_DIR / "sample_llm_response.json").read_text()


class TestParseResponse:
    def test_plain_json(self) -> None:
        raw = _load_sample_response()
        profile = _parse_response(raw)
        assert profile.name == "Jane Doe"
        assert "Senior Python Engineer" in profile.search_keywords
        assert profile.seniority == "senior"

    def test_markdown_wrapped_json(self) -> None:
        raw = "```json\n" + _load_sample_response() + "\n```"
        profile = _parse_response(raw)
        assert profile.name == "Jane Doe"

    def test_markdown_no_language_hint(self) -> None:
        raw = "```\n" + _load_sample_response() + "\n```"
        profile = _parse_response(raw)
        assert profile.name == "Jane Doe"

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ValueError, match="Failed to parse LLM response"):
            _parse_response("this is not json {{{")

    def test_missing_required_field_raises(self) -> None:
        data = json.loads(_load_sample_response())
        del data["search_keywords"]
        with pytest.raises(ValueError):
            _parse_response(json.dumps(data))


class TestAnalyzeResume:
    def test_missing_api_key(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="ANTHROPIC_API_KEY"),
        ):
            analyze_resume("resume text")

    def test_missing_anthropic_sdk(self) -> None:
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"anthropic": None}),
            pytest.raises(ImportError, match="anthropic is required"),
        ):
            analyze_resume("resume text")

    def test_successful_analysis(self) -> None:
        sample = _load_sample_response()

        mock_content = MagicMock()
        mock_content.text = sample

        mock_message = MagicMock()
        mock_message.content = [mock_content]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        ):
            profile = analyze_resume("Jane Doe, Senior Python Engineer, 8 years...")

        assert profile.name == "Jane Doe"
        assert profile.seniority == "senior"
        mock_client.messages.create.assert_called_once()
