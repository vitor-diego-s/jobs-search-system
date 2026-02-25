"""Configuration models and YAML loader for the jobs search engine."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class SearchFilters(BaseModel):
    """Platform-specific search filters."""

    geo_id: int | None = None
    workplace_type: list[str] = Field(default_factory=list)
    experience_level: list[str] = Field(default_factory=list)
    easy_apply_only: bool = False
    max_pages: int = Field(default=3, ge=1, le=10)


class SearchConfig(BaseModel):
    """A single search entry."""

    keyword: str
    platform: str = "linkedin"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    exclude_keywords: list[str] = Field(default_factory=list)
    require_keywords: list[str] = Field(default_factory=list)
    fetch_description: bool = False

    @field_validator("keyword")
    @classmethod
    def keyword_not_empty(cls, v: str) -> str:
        if not v.strip():
            msg = "keyword must not be empty"
            raise ValueError(msg)
        return v.strip()


class QuotaPlatformConfig(BaseModel):
    """Quota limits for a single platform."""

    max_searches_per_day: int = Field(default=5, ge=1)
    max_candidates_per_day: int = Field(default=200, ge=1)


class BrowserConfig(BaseModel):
    """Browser session configuration."""

    cookies_path: str = "config/linkedin_cookies.json"
    timeout_ms: int = Field(default=30000, ge=1000)


class ScoringConfig(BaseModel):
    """Weights for rule-based relevance scoring."""

    title_match_bonus: float = 20.0
    seniority_match_bonus: float = 15.0
    easy_apply_bonus: float = 10.0
    remote_bonus: float = 10.0
    recency_weight: float = Field(default=0.3, ge=0.0, le=1.0)


class DatabaseConfig(BaseModel):
    """Database configuration."""

    path: str = "data/candidates.db"


class Settings(BaseModel):
    """Top-level settings loaded from YAML."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    quotas: dict[str, QuotaPlatformConfig] = Field(default_factory=dict)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    searches: list[SearchConfig] = Field(default_factory=list)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

    @field_validator("searches")
    @classmethod
    def at_least_one_search(cls, v: list[SearchConfig]) -> list[SearchConfig]:
        if not v:
            msg = "at least one search must be configured"
            raise ValueError(msg)
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load settings from a YAML file."""
        path = Path(path)
        if not path.exists():
            msg = f"Config file not found: {path}"
            raise FileNotFoundError(msg)
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(raw)
