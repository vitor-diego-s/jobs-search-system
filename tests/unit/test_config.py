"""Tests for configuration models and YAML loading."""

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from src.core.config import (
    BrowserConfig,
    DatabaseConfig,
    QuotaPlatformConfig,
    ScoringConfig,
    SearchConfig,
    SearchFilters,
    Settings,
)


class TestSearchFilters:
    def test_defaults(self) -> None:
        f = SearchFilters()
        assert f.max_pages == 3
        assert f.workplace_type == []
        assert f.easy_apply_only is False

    def test_max_pages_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SearchFilters(max_pages=0)
        with pytest.raises(ValidationError):
            SearchFilters(max_pages=11)


class TestSearchConfig:
    def test_keyword_required(self) -> None:
        with pytest.raises(ValidationError):
            SearchConfig(keyword="")

    def test_keyword_stripped(self) -> None:
        sc = SearchConfig(keyword="  Python Engineer  ")
        assert sc.keyword == "Python Engineer"

    def test_defaults(self) -> None:
        sc = SearchConfig(keyword="Python")
        assert sc.platform == "linkedin"
        assert sc.fetch_description is False
        assert sc.exclude_keywords == []


class TestQuotaPlatformConfig:
    def test_defaults(self) -> None:
        q = QuotaPlatformConfig()
        assert q.max_searches_per_day == 5
        assert q.max_candidates_per_day == 200

    def test_min_one(self) -> None:
        with pytest.raises(ValidationError):
            QuotaPlatformConfig(max_searches_per_day=0)


class TestBrowserConfig:
    def test_defaults(self) -> None:
        b = BrowserConfig()
        assert b.timeout_ms == 30000

    def test_timeout_min(self) -> None:
        with pytest.raises(ValidationError):
            BrowserConfig(timeout_ms=500)


class TestScoringConfig:
    def test_defaults(self) -> None:
        s = ScoringConfig()
        assert s.title_match_bonus == 20.0
        assert s.recency_weight == 0.3

    def test_recency_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ScoringConfig(recency_weight=1.5)


class TestDatabaseConfig:
    def test_default_path(self) -> None:
        d = DatabaseConfig()
        assert d.path == "data/candidates.db"


class TestSettings:
    def test_load_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = dedent("""\
            database:
              path: data/test.db
            quotas:
              linkedin:
                max_searches_per_day: 3
                max_candidates_per_day: 100
            browser:
              cookies_path: config/cookies.json
              timeout_ms: 15000
            searches:
              - keyword: "Python Engineer"
                platform: linkedin
                filters:
                  geo_id: 92000000
                  workplace_type: [remote]
                  easy_apply_only: true
                  max_pages: 2
                exclude_keywords:
                  - Junior
            scoring:
              title_match_bonus: 25
        """)
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml_content)

        settings = Settings.from_yaml(config_file)

        assert settings.database.path == "data/test.db"
        assert len(settings.searches) == 1
        assert settings.searches[0].keyword == "Python Engineer"
        assert settings.searches[0].filters.easy_apply_only is True
        assert settings.quotas["linkedin"].max_searches_per_day == 3
        assert settings.scoring.title_match_bonus == 25.0

    def test_no_searches_raises(self, tmp_path: Path) -> None:
        yaml_content = dedent("""\
            database:
              path: data/test.db
            searches: []
        """)
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml_content)

        with pytest.raises(ValidationError, match="at least one search"):
            Settings.from_yaml(config_file)

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            Settings.from_yaml("/nonexistent/path.yaml")

    def test_invalid_keyword_raises(self, tmp_path: Path) -> None:
        yaml_content = dedent("""\
            searches:
              - keyword: "   "
                platform: linkedin
        """)
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml_content)

        with pytest.raises(ValidationError, match="keyword must not be empty"):
            Settings.from_yaml(config_file)

    def test_load_example_settings(self) -> None:
        """The shipped example config/settings.yaml must be valid."""
        settings = Settings.from_yaml("config/settings.yaml")
        assert len(settings.searches) == 2
        assert settings.searches[0].keyword == "Senior Python Engineer"
