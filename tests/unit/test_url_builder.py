"""Tests for LinkedIn URL builder and pagination helpers."""

from urllib.parse import parse_qs, urlparse

import pytest

from src.core.config import SearchFilters
from src.platforms.linkedin.searcher import (
    EXPERIENCE_LEVEL_MAP,
    RESULTS_PER_PAGE,
    WORKPLACE_TYPE_MAP,
    build_job_url,
    build_url,
    should_stop_pagination,
)


def _parse(url: str) -> dict[str, list[str]]:
    """Parse URL and return query params as dict."""
    return parse_qs(urlparse(url).query)


# ---------------------------------------------------------------------------
# TestBuildUrl
# ---------------------------------------------------------------------------


class TestBuildUrl:
    """URL builder: keyword encoding, params, pagination."""

    def test_keyword_encoded(self) -> None:
        url = build_url("Senior Python Engineer", SearchFilters())
        params = _parse(url)
        assert params["keywords"] == ["Senior Python Engineer"]

    def test_keyword_special_chars(self) -> None:
        url = build_url("C++ Developer", SearchFilters())
        assert "C%2B%2B" in url

    def test_sort_by_dd(self) -> None:
        params = _parse(build_url("test", SearchFilters()))
        assert params["sortBy"] == ["DD"]

    def test_base_url(self) -> None:
        url = build_url("test", SearchFilters())
        assert url.startswith("https://www.linkedin.com/jobs/search/?")

    def test_geo_id_present(self) -> None:
        filters = SearchFilters(geo_id=92000000)
        params = _parse(build_url("test", filters))
        assert params["geoId"] == ["92000000"]

    def test_geo_id_absent(self) -> None:
        params = _parse(build_url("test", SearchFilters()))
        assert "geoId" not in params

    def test_easy_apply_true(self) -> None:
        filters = SearchFilters(easy_apply_only=True)
        params = _parse(build_url("test", filters))
        assert params["f_AL"] == ["true"]

    def test_easy_apply_false(self) -> None:
        params = _parse(build_url("test", SearchFilters()))
        assert "f_AL" not in params

    def test_workplace_remote(self) -> None:
        filters = SearchFilters(workplace_type=["remote"])
        params = _parse(build_url("test", filters))
        assert params["f_WT"] == ["2"]

    def test_workplace_multiple(self) -> None:
        filters = SearchFilters(workplace_type=["remote", "hybrid"])
        params = _parse(build_url("test", filters))
        assert params["f_WT"] == ["2,3"]

    def test_workplace_on_site_alias(self) -> None:
        filters = SearchFilters(workplace_type=["on-site"])
        params = _parse(build_url("test", filters))
        assert params["f_WT"] == ["1"]

    def test_experience_senior(self) -> None:
        filters = SearchFilters(experience_level=["senior"])
        params = _parse(build_url("test", filters))
        assert params["f_E"] == ["4"]

    def test_experience_multiple(self) -> None:
        filters = SearchFilters(experience_level=["senior", "director"])
        params = _parse(build_url("test", filters))
        assert params["f_E"] == ["4,5"]

    def test_page_zero_no_start(self) -> None:
        params = _parse(build_url("test", SearchFilters(), page=0))
        assert "start" not in params

    def test_page_one_start_25(self) -> None:
        params = _parse(build_url("test", SearchFilters(), page=1))
        assert params["start"] == ["25"]

    def test_page_two_start_50(self) -> None:
        params = _parse(build_url("test", SearchFilters(), page=2))
        assert params["start"] == ["50"]

    def test_page_three_start_75(self) -> None:
        params = _parse(build_url("test", SearchFilters(), page=3))
        assert params["start"] == ["75"]

    def test_full_example(self) -> None:
        """Matches the settings.yaml 'Senior Python Engineer' search."""
        filters = SearchFilters(
            geo_id=92000000,
            workplace_type=["remote"],
            experience_level=["senior", "director"],
            easy_apply_only=True,
        )
        url = build_url("Senior Python Engineer", filters, page=0)
        params = _parse(url)
        assert params["keywords"] == ["Senior Python Engineer"]
        assert params["geoId"] == ["92000000"]
        assert params["f_AL"] == ["true"]
        assert params["f_WT"] == ["2"]
        assert params["f_E"] == ["4,5"]
        assert params["sortBy"] == ["DD"]
        assert "start" not in params

    def test_unknown_workplace_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        filters = SearchFilters(workplace_type=["mars-office"])
        url = build_url("test", filters)
        params = _parse(url)
        assert "f_WT" not in params
        assert "Unknown workplace_type" in caplog.text

    def test_unknown_experience_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        filters = SearchFilters(experience_level=["cto"])
        url = build_url("test", filters)
        params = _parse(url)
        assert "f_E" not in params
        assert "Unknown experience_level" in caplog.text

    def test_mixed_known_unknown_experience(self, caplog: pytest.LogCaptureFixture) -> None:
        filters = SearchFilters(experience_level=["senior", "cto"])
        params = _parse(build_url("test", filters))
        assert params["f_E"] == ["4"]
        assert "Unknown experience_level" in caplog.text


# ---------------------------------------------------------------------------
# TestShouldStopPagination
# ---------------------------------------------------------------------------


class TestShouldStopPagination:
    """Pagination stop logic (L8: 25 per page)."""

    def test_zero_cards_stops(self) -> None:
        assert should_stop_pagination(0, page=0) is True

    def test_fewer_than_25_stops(self) -> None:
        assert should_stop_pagination(14, page=1) is True

    def test_exactly_25_continues(self) -> None:
        assert should_stop_pagination(25, page=0) is False

    def test_more_than_25_continues(self) -> None:
        assert should_stop_pagination(30, page=0) is False


# ---------------------------------------------------------------------------
# TestBuildJobUrl
# ---------------------------------------------------------------------------


class TestBuildJobUrl:
    """Canonical job URL builder."""

    def test_canonical_form(self) -> None:
        assert build_job_url("123456") == "https://www.linkedin.com/jobs/view/123456/"

    def test_string_id(self) -> None:
        url = build_job_url("999999999")
        assert "/jobs/view/999999999/" in url


# ---------------------------------------------------------------------------
# TestMappingConstants
# ---------------------------------------------------------------------------


class TestMappingConstants:
    """Verify all expected values are present in mapping dicts."""

    def test_workplace_remote(self) -> None:
        assert WORKPLACE_TYPE_MAP["remote"] == "2"

    def test_workplace_hybrid(self) -> None:
        assert WORKPLACE_TYPE_MAP["hybrid"] == "3"

    def test_workplace_onsite(self) -> None:
        assert WORKPLACE_TYPE_MAP["onsite"] == "1"

    def test_workplace_on_site_alias(self) -> None:
        assert WORKPLACE_TYPE_MAP["on-site"] == "1"

    def test_experience_internship(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["internship"] == "1"

    def test_experience_entry(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["entry"] == "2"

    def test_experience_associate(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["associate"] == "3"

    def test_experience_mid_senior(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["mid-senior"] == "4"

    def test_experience_senior_alias(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["senior"] == "4"

    def test_experience_director(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["director"] == "5"

    def test_experience_executive(self) -> None:
        assert EXPERIENCE_LEVEL_MAP["executive"] == "6"

    def test_results_per_page(self) -> None:
        assert RESULTS_PER_PAGE == 25
