"""Tests for browser session: cookie loading and configuration."""

import json
from pathlib import Path

import pytest

from src.browser.session import _load_cookies
from src.core.config import BrowserConfig

# ---------------------------------------------------------------------------
# TestLoadCookies
# ---------------------------------------------------------------------------


class TestLoadCookies:
    """Cookie file loading — various success and failure paths."""

    def test_valid_cookie_file(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {"name": "li_at", "value": "abc123", "domain": ".linkedin.com", "path": "/"},
        ]
        cookie_file.write_text(json.dumps(cookies))
        result = _load_cookies(str(cookie_file))
        assert len(result) == 1
        assert result[0]["name"] == "li_at"

    def test_missing_file_returns_empty(self) -> None:
        result = _load_cookies("/nonexistent/path/cookies.json")
        assert result == []

    def test_empty_array_returns_empty(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("[]")
        result = _load_cookies(str(cookie_file))
        assert result == []

    def test_not_array_returns_empty(self, tmp_path: Path) -> None:
        """JSON object (not array) → logged warning, empty list."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text('{"key": "value"}')
        result = _load_cookies(str(cookie_file))
        assert result == []

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("not-json{{{")
        result = _load_cookies(str(cookie_file))
        assert result == []

    def test_multiple_cookies(self, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.json"
        cookies = [
            {"name": "li_at", "value": "v1", "domain": ".linkedin.com", "path": "/"},
            {"name": "JSESSIONID", "value": "v2", "domain": ".linkedin.com", "path": "/"},
        ]
        cookie_file.write_text(json.dumps(cookies))
        result = _load_cookies(str(cookie_file))
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestBrowserConfig
# ---------------------------------------------------------------------------


class TestBrowserSessionConfig:
    """BrowserConfig integration with session."""

    def test_default_config(self) -> None:
        config = BrowserConfig()
        assert config.cookies_path == "config/linkedin_cookies.json"
        assert config.timeout_ms == 30000

    def test_custom_config(self) -> None:
        config = BrowserConfig(cookies_path="/tmp/my_cookies.json", timeout_ms=60000)
        assert config.cookies_path == "/tmp/my_cookies.json"
        assert config.timeout_ms == 60000

    def test_timeout_minimum(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 1000"):
            BrowserConfig(timeout_ms=500)
