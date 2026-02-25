"""Tests for core schemas: JobCandidate, ScoredCandidate, SearchRunResult."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.schemas import JobCandidate, ScoredCandidate, SearchRunResult


def _make_candidate(**overrides: object) -> JobCandidate:
    defaults: dict[str, object] = {
        "external_id": "123",
        "platform": "linkedin",
        "title": "Senior Python Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "url": "https://linkedin.com/jobs/view/123",
        "is_easy_apply": True,
        "workplace_type": "remote",
        "posted_time": "2 days ago",
    }
    defaults.update(overrides)
    return JobCandidate(**defaults)  # type: ignore[arg-type]


class TestJobCandidate:
    def test_create_with_required_fields(self) -> None:
        c = JobCandidate(
            external_id="456",
            platform="linkedin",
            title="Engineer",
            url="https://example.com/456",
        )
        assert c.external_id == "456"
        assert c.company == ""
        assert c.description_snippet == ""

    def test_defaults(self) -> None:
        c = _make_candidate()
        assert c.description_snippet == ""
        assert isinstance(c.found_at, datetime)

    def test_frozen_model(self) -> None:
        c = _make_candidate()
        with pytest.raises(ValidationError):
            c.title = "New Title"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = _make_candidate(found_at=datetime(2026, 1, 1))
        b = _make_candidate(found_at=datetime(2026, 1, 1))
        assert a == b

    def test_different_candidates_not_equal(self) -> None:
        a = _make_candidate(external_id="1")
        b = _make_candidate(external_id="2")
        assert a != b


class TestScoredCandidate:
    def test_create(self) -> None:
        c = _make_candidate()
        sc = ScoredCandidate(candidate=c, score=75.0)
        assert sc.score == 75.0
        assert sc.candidate.title == "Senior Python Engineer"

    def test_default_score(self) -> None:
        sc = ScoredCandidate(candidate=_make_candidate())
        assert sc.score == 0.0

    def test_score_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ScoredCandidate(candidate=_make_candidate(), score=101.0)

    def test_score_negative(self) -> None:
        with pytest.raises(ValidationError):
            ScoredCandidate(candidate=_make_candidate(), score=-1.0)

    def test_frozen(self) -> None:
        sc = ScoredCandidate(candidate=_make_candidate(), score=50.0)
        with pytest.raises(ValidationError):
            sc.score = 99.0  # type: ignore[misc]


class TestSearchRunResult:
    def test_create(self) -> None:
        now = datetime.now()
        r = SearchRunResult(
            platform="linkedin",
            keyword="Python",
            raw_count=50,
            filtered_count=12,
            started_at=now,
            finished_at=now,
        )
        assert r.raw_count == 50
        assert r.filtered_count == 12
