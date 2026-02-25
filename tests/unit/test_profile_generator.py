"""Tests for profile-to-settings generator."""

from pathlib import Path

from src.core.config import Settings
from src.profile.generator import generate_settings_dict, write_settings_yaml
from src.profile.schema import ProfileData


def _profile(**overrides: object) -> ProfileData:
    defaults = {
        "name": "Jane Doe",
        "search_keywords": ["Senior Python Engineer", "Staff Backend Engineer"],
        "seniority": "senior",
        "scoring_keywords": ["Python", "FastAPI"],
        "exclude_keywords": ["Junior", "PHP"],
        "years_of_experience": 8,
        "preferred_workplace": ["remote"],
    }
    defaults.update(overrides)
    return ProfileData(**defaults)  # type: ignore[arg-type]


class TestGenerateSettingsDict:
    def test_roundtrip_validation(self) -> None:
        """Generated dict must pass Settings.model_validate."""
        profile = _profile()
        settings_dict = generate_settings_dict(profile)
        settings = Settings.model_validate(settings_dict)
        assert len(settings.searches) == 2

    def test_seniority_mapping_senior(self) -> None:
        profile = _profile(seniority="senior")
        settings_dict = generate_settings_dict(profile)
        exp = settings_dict["searches"][0]["filters"]["experience_level"]
        assert "senior" in exp
        assert "director" in exp

    def test_seniority_mapping_junior(self) -> None:
        profile = _profile(seniority="junior")
        settings_dict = generate_settings_dict(profile)
        exp = settings_dict["searches"][0]["filters"]["experience_level"]
        assert "entry" in exp
        assert "associate" in exp

    def test_scoring_keywords_propagated(self) -> None:
        profile = _profile(scoring_keywords=["Python", "Django", "K8s"])
        settings_dict = generate_settings_dict(profile)
        for search in settings_dict["searches"]:
            assert search["scoring_keywords"] == ["Python", "Django", "K8s"]

    def test_require_keywords_default_empty(self) -> None:
        profile = _profile()
        settings_dict = generate_settings_dict(profile)
        for search in settings_dict["searches"]:
            assert search["require_keywords"] == []

    def test_geo_id_set_when_provided(self) -> None:
        profile = _profile(preferred_geo_ids=[92000000])
        settings_dict = generate_settings_dict(profile)
        assert settings_dict["searches"][0]["filters"]["geo_id"] == 92000000

    def test_overrides_applied(self) -> None:
        profile = _profile()
        settings_dict = generate_settings_dict(
            profile,
            scoring={"title_match_bonus": 50},
        )
        assert settings_dict["scoring"]["title_match_bonus"] == 50


class TestWriteSettingsYaml:
    def test_produces_loadable_yaml(self, tmp_path: Path) -> None:
        profile = _profile()
        settings_dict = generate_settings_dict(profile)
        output = tmp_path / "settings.yaml"
        write_settings_yaml(settings_dict, output)

        # Must be loadable by Settings.from_yaml
        settings = Settings.from_yaml(output)
        assert len(settings.searches) == 2
        assert settings.searches[0].keyword == "Senior Python Engineer"
