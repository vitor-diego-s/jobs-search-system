"""Tests for LinkedIn DOM parser."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import SearchFilters
from src.platforms.linkedin.parser import LinkedInParser


def _make_mock_card(
    *,
    job_id: str = "111111",
    job_id_attr: str = "data-occludable-job-id",
    title: str = "Senior Python Engineer",
    href: str = "https://www.linkedin.com/jobs/view/111111/?trackingId=abc",
    company: str = "Acme Corp",
    location: str = "Remote — Worldwide",
    posted_time: str | None = "2026-02-20",
    posted_text: str = "3 days ago",
) -> AsyncMock:
    """Build a mock card element satisfying the ElementLike protocol."""
    # Title link element
    title_link = AsyncMock()
    title_link.text_content.return_value = title
    title_link.get_attribute.return_value = href

    # Company element
    company_el = AsyncMock()
    company_el.text_content.return_value = company

    # Location element
    location_el = AsyncMock()
    location_el.text_content.return_value = location

    # Posted time element
    time_el = AsyncMock()
    time_el.get_attribute.return_value = posted_time
    time_el.text_content.return_value = posted_text

    # Card element — route query_selector calls
    card = AsyncMock()

    title_keywords = ("/jobs/view/", "job-card-list__title", "job-card-container__link")
    company_keywords = ("primary-description", "lockup__subtitle", "company-name")
    location_keywords = ("metadata-item", "lockup__caption", "metadata-wrapper")
    time_keywords = ("time", "listed-time", "footer-item")

    async def _query_selector(selector: str) -> AsyncMock | None:
        if any(k in selector for k in title_keywords):
            return title_link
        if any(k in selector for k in company_keywords):
            return company_el
        if any(k in selector for k in location_keywords):
            return location_el
        if any(k in selector for k in time_keywords):
            return time_el
        return None

    card.query_selector = AsyncMock(side_effect=_query_selector)

    async def _get_attribute(name: str) -> str | None:
        if name == job_id_attr:
            return job_id
        return None

    card.get_attribute = AsyncMock(side_effect=_get_attribute)

    return card


def _default_filters(**kwargs: object) -> SearchFilters:
    """SearchFilters with easy_apply_only=True and remote by default."""
    defaults: dict[str, object] = {
        "easy_apply_only": True,
        "workplace_type": ["remote"],
    }
    defaults.update(kwargs)
    return SearchFilters(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestLinkedInParserParseCard
# ---------------------------------------------------------------------------


class TestLinkedInParserParseCard:
    """Single card parsing."""

    @pytest.fixture
    def parser(self) -> LinkedInParser:
        return LinkedInParser(_default_filters())

    async def test_full_card(self, parser: LinkedInParser) -> None:
        card = _make_mock_card()
        result = await parser.parse_card(card)
        assert result is not None
        assert result.external_id == "111111"
        assert result.platform == "linkedin"
        assert result.title == "Senior Python Engineer"
        assert result.company == "Acme Corp"
        assert result.location == "Remote — Worldwide"
        assert result.posted_time == "2026-02-20"

    async def test_title_newline_stripped(self, parser: LinkedInParser) -> None:
        """L5: title with \\n duplicate → only first line kept."""
        card = _make_mock_card(title="Backend Developer\nBackend Developer")
        result = await parser.parse_card(card)
        assert result is not None
        assert result.title == "Backend Developer"
        assert "\n" not in result.title

    async def test_missing_company_returns_empty(self, parser: LinkedInParser) -> None:
        """L12: missing company → "" not crash."""
        card = _make_mock_card()
        # Override: all company selectors return None
        original_side_effect = card.query_selector.side_effect

        company_kw = ("primary-description", "lockup__subtitle", "company-name")

        async def _no_company(selector: str) -> AsyncMock | None:
            if any(k in selector for k in company_kw):
                return None
            return await original_side_effect(selector)

        card.query_selector = AsyncMock(side_effect=_no_company)
        result = await parser.parse_card(card)
        assert result is not None
        assert result.company == ""

    async def test_no_job_id_returns_none(self, parser: LinkedInParser) -> None:
        """Card without external_id is skipped."""
        card = _make_mock_card()
        card.get_attribute = AsyncMock(return_value=None)
        result = await parser.parse_card(card)
        assert result is None

    async def test_easy_apply_from_config(self, parser: LinkedInParser) -> None:
        """L2: is_easy_apply comes from config, not DOM."""
        card = _make_mock_card()
        result = await parser.parse_card(card)
        assert result is not None
        assert result.is_easy_apply is True

    async def test_easy_apply_false_from_config(self) -> None:
        parser = LinkedInParser(SearchFilters(easy_apply_only=False))
        card = _make_mock_card()
        result = await parser.parse_card(card)
        assert result is not None
        assert result.is_easy_apply is False

    async def test_workplace_type_from_config(self, parser: LinkedInParser) -> None:
        """Workplace type derived from single filter value."""
        card = _make_mock_card()
        result = await parser.parse_card(card)
        assert result is not None
        assert result.workplace_type == "remote"

    async def test_url_tracking_params_stripped(self, parser: LinkedInParser) -> None:
        card = _make_mock_card(
            href="https://www.linkedin.com/jobs/view/111111/?trackingId=abc&refId=xyz"
        )
        result = await parser.parse_card(card)
        assert result is not None
        assert "trackingId" not in result.url
        assert "refId" not in result.url
        assert result.url == "https://www.linkedin.com/jobs/view/111111/"

    async def test_relative_url_gets_domain(self, parser: LinkedInParser) -> None:
        card = _make_mock_card(href="/jobs/view/111111/?trackingId=abc")
        result = await parser.parse_card(card)
        assert result is not None
        assert result.url.startswith("https://www.linkedin.com/")
        assert "trackingId" not in result.url

    async def test_fallback_job_id_attr(self) -> None:
        """Falls back to data-job-id when data-occludable-job-id is missing."""
        parser = LinkedInParser(_default_filters())
        card = _make_mock_card(job_id="222222", job_id_attr="data-job-id")
        result = await parser.parse_card(card)
        assert result is not None
        assert result.external_id == "222222"

    async def test_posted_time_falls_back_to_text(self, parser: LinkedInParser) -> None:
        """When time element has no datetime attr, use text_content."""
        card = _make_mock_card(posted_time=None, posted_text="1 week ago")
        result = await parser.parse_card(card)
        assert result is not None
        assert result.posted_time == "1 week ago"


# ---------------------------------------------------------------------------
# TestLinkedInParserParseCards
# ---------------------------------------------------------------------------


class TestLinkedInParserParseCards:
    """Multiple card parsing."""

    @pytest.fixture
    def parser(self) -> LinkedInParser:
        return LinkedInParser(_default_filters())

    async def test_multiple_cards(self, parser: LinkedInParser) -> None:
        cards = [
            _make_mock_card(job_id="111111"),
            _make_mock_card(job_id="222222"),
        ]
        results = await parser.parse_cards(cards)
        assert len(results) == 2
        assert results[0].external_id == "111111"
        assert results[1].external_id == "222222"

    async def test_skips_bad_cards(self, parser: LinkedInParser) -> None:
        good = _make_mock_card(job_id="111111")
        bad = _make_mock_card()
        bad.get_attribute = AsyncMock(return_value=None)  # No job ID
        results = await parser.parse_cards([good, bad])
        assert len(results) == 1
        assert results[0].external_id == "111111"

    async def test_exception_in_card_doesnt_crash(self, parser: LinkedInParser) -> None:
        """L12: one card throwing doesn't break the batch."""
        good = _make_mock_card(job_id="111111")
        broken = AsyncMock()
        broken.get_attribute = AsyncMock(side_effect=RuntimeError("DOM exploded"))
        results = await parser.parse_cards([good, broken])
        assert len(results) == 1

    async def test_empty_cards_list(self, parser: LinkedInParser) -> None:
        results = await parser.parse_cards([])
        assert results == []


# ---------------------------------------------------------------------------
# TestResolveWorkplaceType
# ---------------------------------------------------------------------------


class TestResolveWorkplaceType:
    """Workplace type resolution from filter values."""

    def test_single_type(self) -> None:
        parser = LinkedInParser(SearchFilters(workplace_type=["remote"]))
        assert parser._workplace_type == "remote"

    def test_multiple_types_returns_empty(self) -> None:
        parser = LinkedInParser(SearchFilters(workplace_type=["remote", "hybrid"]))
        assert parser._workplace_type == ""

    def test_empty_returns_empty(self) -> None:
        parser = LinkedInParser(SearchFilters())
        assert parser._workplace_type == ""
