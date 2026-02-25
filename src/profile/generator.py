"""Generate settings.yaml from ProfileData."""

from pathlib import Path
from typing import Any

import yaml

from src.profile.schema import ProfileData

# Seniority → experience_level filter mapping
_SENIORITY_MAP: dict[str, list[str]] = {
    "junior": ["entry", "associate"],
    "mid": ["mid", "senior"],
    "senior": ["senior", "director"],
    "staff": ["senior", "director"],
    "principal": ["senior", "director", "executive"],
    "director": ["director", "executive"],
}


def generate_settings_dict(profile: ProfileData, **overrides: Any) -> dict[str, Any]:
    """Transform a ProfileData into a Settings-compatible dict.

    Args:
        profile: Extracted profile data.
        **overrides: Override any top-level key in the output dict.

    Returns:
        Dict that can be passed to Settings.model_validate().
    """
    experience_levels = _SENIORITY_MAP.get(profile.seniority, ["mid", "senior"])

    searches: list[dict[str, Any]] = []
    for keyword in profile.search_keywords:
        entry: dict[str, Any] = {
            "keyword": keyword,
            "platform": "linkedin",
            "filters": {
                "workplace_type": profile.preferred_workplace or ["remote"],
                "experience_level": experience_levels,
                "easy_apply_only": True,
                "max_pages": 3,
            },
            "exclude_keywords": profile.exclude_keywords,
            "require_keywords": [],
            "scoring_keywords": profile.scoring_keywords,
            "fetch_description": False,
        }
        if profile.preferred_geo_ids:
            entry["filters"]["geo_id"] = profile.preferred_geo_ids[0]
        searches.append(entry)

    settings: dict[str, Any] = {
        "database": {"path": "data/candidates.db"},
        "quotas": {
            "linkedin": {
                "max_searches_per_day": max(len(searches), 3),
                "max_candidates_per_day": 200,
            },
        },
        "browser": {
            "cookies_path": "config/linkedin_cookies.json",
            "timeout_ms": 30000,
        },
        "searches": searches,
        "scoring": {
            "title_match_bonus": 20,
            "seniority_match_bonus": 15,
            "easy_apply_bonus": 10,
            "remote_bonus": 10,
            "recency_weight": 0.3,
        },
    }

    settings.update(overrides)
    return settings


def write_settings_yaml(settings_dict: dict[str, Any], path: str | Path) -> None:
    """Write a settings dict to a YAML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(settings_dict, default_flow_style=False, sort_keys=False))
