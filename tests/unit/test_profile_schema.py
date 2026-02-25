"""Tests for ProfileData schema."""

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from src.profile.schema import ProfileData


class TestProfileData:
    def test_valid_profile(self) -> None:
        p = ProfileData(
            name="Jane Doe",
            search_keywords=["Senior Python Engineer"],
            seniority="senior",
            scoring_keywords=["Python", "FastAPI"],
            exclude_keywords=["Junior"],
        )
        assert p.name == "Jane Doe"
        assert p.seniority == "senior"
        assert len(p.search_keywords) == 1

    def test_missing_search_keywords_raises(self) -> None:
        with pytest.raises(ValidationError, match="search_keywords must not be empty"):
            ProfileData(search_keywords=[])

    def test_invalid_seniority_raises(self) -> None:
        with pytest.raises(ValidationError, match="seniority must be one of"):
            ProfileData(search_keywords=["Python"], seniority="wizard")

    def test_seniority_normalized_lowercase(self) -> None:
        p = ProfileData(search_keywords=["Python"], seniority="Senior")
        assert p.seniority == "senior"

    def test_defaults(self) -> None:
        p = ProfileData(search_keywords=["Python"])
        assert p.name == ""
        assert p.seniority == "mid"
        assert p.scoring_keywords == []
        assert p.exclude_keywords == []
        assert p.years_of_experience is None
        assert p.preferred_workplace == []
        assert p.preferred_geo_ids == []


class TestProfileYamlRoundtrip:
    def test_roundtrip(self, tmp_path: Path) -> None:
        original = ProfileData(
            name="Jane Doe",
            search_keywords=["Senior Python Engineer", "Staff Backend"],
            seniority="senior",
            scoring_keywords=["Python", "Django"],
            exclude_keywords=["Junior"],
            years_of_experience=8,
            preferred_workplace=["remote"],
        )
        yaml_path = tmp_path / "profile.yaml"
        original.to_yaml(yaml_path)

        loaded = ProfileData.from_yaml(yaml_path)
        assert loaded.name == original.name
        assert loaded.search_keywords == original.search_keywords
        assert loaded.seniority == original.seniority
        assert loaded.scoring_keywords == original.scoring_keywords
        assert loaded.years_of_experience == 8

    def test_from_yaml_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            ProfileData.from_yaml("/nonexistent/profile.yaml")

    def test_from_yaml_manual(self, tmp_path: Path) -> None:
        yaml_content = dedent("""\
            name: "Test User"
            search_keywords:
              - "Python Developer"
            seniority: "mid"
            scoring_keywords:
              - "Python"
        """)
        path = tmp_path / "profile.yaml"
        path.write_text(yaml_content)

        p = ProfileData.from_yaml(path)
        assert p.name == "Test User"
        assert p.search_keywords == ["Python Developer"]
