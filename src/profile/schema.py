"""ProfileData model for config/profile.yaml."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

ALLOWED_SENIORITY = {"junior", "mid", "senior", "staff", "principal", "director"}


class ProfileData(BaseModel):
    """Structured profile extracted from a resume."""

    name: str = ""
    search_keywords: list[str]
    seniority: str = "mid"
    scoring_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    years_of_experience: int | None = None
    preferred_workplace: list[str] = Field(default_factory=list)
    preferred_geo_ids: list[int] = Field(default_factory=list)

    @field_validator("search_keywords")
    @classmethod
    def search_keywords_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            msg = "search_keywords must not be empty"
            raise ValueError(msg)
        return v

    @field_validator("seniority")
    @classmethod
    def seniority_in_allowed(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ALLOWED_SENIORITY:
            msg = f"seniority must be one of {sorted(ALLOWED_SENIORITY)}, got '{v}'"
            raise ValueError(msg)
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProfileData":
        """Load profile from a YAML file."""
        path = Path(path)
        if not path.exists():
            msg = f"Profile file not found: {path}"
            raise FileNotFoundError(msg)
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(raw)

    def to_yaml(self, path: str | Path) -> None:
        """Write profile to a YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump()
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
