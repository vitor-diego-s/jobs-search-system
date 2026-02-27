"""Tests for LinkedIn adapter description fetching (M9)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import SearchConfig, SearchFilters
from src.platforms.linkedin.adapter import LinkedInAdapter
from src.platforms.linkedin.selectors import DESCRIPTION_PANEL_SELECTORS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_card(*, has_id: bool = True) -> AsyncMock:
    """Create a mock card element that the parser can extract fields from."""
    card = AsyncMock()
    card.scroll_into_view_if_needed = AsyncMock()
    card.click = AsyncMock()

    async def _get_attribute(name: str) -> str | None:
        if name == "data-occludable-job-id" and has_id:
            return "12345"
        if name == "data-job-id" and has_id:
            return "12345"
        return None

    card.get_attribute = AsyncMock(side_effect=_get_attribute)

    # query_selector returns elements for title parsing
    strong_el = AsyncMock()
    strong_el.text_content = AsyncMock(return_value="Senior Python Engineer")
    strong_el.get_attribute = AsyncMock(return_value=None)

    async def _query_selector(selector: str) -> AsyncMock | None:
        if selector == "a span strong":
            return strong_el
        return None

    card.query_selector = AsyncMock(side_effect=_query_selector)

    return card


def _make_page(*, description_text: str | None = "Full job description text here") -> AsyncMock:
    """Create a mock page object."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock()

    if description_text is not None:
        desc_el = AsyncMock()
        desc_el.text_content = AsyncMock(return_value=description_text)

        async def _wait_for_selector(
            selector: str, *, timeout: int = 30000,
        ) -> AsyncMock | None:
            if selector in DESCRIPTION_PANEL_SELECTORS:
                return desc_el
            return None

        page.wait_for_selector = AsyncMock(side_effect=_wait_for_selector)
    else:
        # Simulate timeout — wait_for_selector raises
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError("Panel not found"))

    # For _find_cards and scroll_until_stable
    page.query_selector_all = AsyncMock(return_value=[])

    return page


def _config(*, fetch_description: bool = True) -> SearchConfig:
    return SearchConfig(
        keyword="Python Engineer",
        platform="linkedin",
        filters=SearchFilters(max_pages=1),
        fetch_description=fetch_description,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchDescription:
    """Tests for LinkedInAdapter._fetch_description and its integration."""

    @pytest.fixture(autouse=True)
    def _patch_sleep(self) -> "pytest.Generator[None]":  # type: ignore[type-arg]
        """Patch asyncio.sleep to avoid real delays in all tests."""
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            yield

    async def test_fetch_description_populates_snippet(self) -> None:
        """When fetch_description=True and panel renders, candidate has description."""
        page = _make_page(description_text="  We are looking for a Python engineer  ")
        card = _make_card()

        # Make _find_cards return our card
        page.query_selector_all = AsyncMock(return_value=[card])

        adapter = LinkedInAdapter(page)
        desc = await adapter._fetch_description(card)

        assert desc == "We are looking for a Python engineer"
        card.click.assert_called_once()

    async def test_fetch_description_false_skips(self) -> None:
        """When fetch_description=False, no click attempts, description stays empty."""
        page = _make_page(description_text="Should not appear")
        card = _make_card()
        page.query_selector_all = AsyncMock(return_value=[card])

        adapter = LinkedInAdapter(page)

        with patch.object(
            adapter, "_fetch_description", wraps=adapter._fetch_description,
        ) as mock_fetch:
            from src.platforms.linkedin.parser import LinkedInParser

            parser = LinkedInParser(SearchFilters(max_pages=1))
            results = await adapter._parse_with_scroll(
                parser, [card], fetch_description=False,
            )

        assert len(results) == 1
        assert results[0].description_snippet == ""
        mock_fetch.assert_not_called()

    async def test_fetch_description_timeout_returns_empty(self) -> None:
        """When panel doesn't render (timeout), candidate kept with empty description."""
        page = _make_page(description_text=None)  # triggers TimeoutError
        card = _make_card()

        adapter = LinkedInAdapter(page)
        desc = await adapter._fetch_description(card)

        assert desc == ""

    async def test_fetch_description_error_continues(self) -> None:
        """Exception during card.click() → candidate kept, no crash."""
        page = _make_page()
        card = _make_card()
        card.click = AsyncMock(side_effect=RuntimeError("Click failed"))

        adapter = LinkedInAdapter(page)
        desc = await adapter._fetch_description(card)

        assert desc == ""

    async def test_fetch_description_delay_between_cards(self) -> None:
        """Verify random_sleep is called after successful description extraction."""
        page = _make_page(description_text="Job description content")
        card = _make_card()

        adapter = LinkedInAdapter(page)

        with patch(
            "src.platforms.linkedin.adapter.random_sleep", new_callable=AsyncMock,
        ) as mock_sleep:
            mock_sleep.return_value = 1.5
            desc = await adapter._fetch_description(card)

        assert desc == "Job description content"
        mock_sleep.assert_called_once()
        min_delay, max_delay = mock_sleep.call_args[0]
        assert min_delay >= 1.0
        assert max_delay <= 2.5


class TestParseWithScrollDescription:
    """Integration of _parse_with_scroll with description fetching."""

    @pytest.fixture(autouse=True)
    def _patch_sleep(self) -> "pytest.Generator[None]":  # type: ignore[type-arg]
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            yield

    async def test_parse_with_scroll_enriches_candidate(self) -> None:
        """Full flow: scroll → parse → click → extract description."""
        page = _make_page(description_text="Detailed job description")
        card = _make_card()

        adapter = LinkedInAdapter(page)

        from src.platforms.linkedin.parser import LinkedInParser

        parser = LinkedInParser(SearchFilters(max_pages=1))

        with patch(
            "src.platforms.linkedin.adapter.random_sleep", new_callable=AsyncMock,
        ) as mock_sleep:
            mock_sleep.return_value = 1.0
            results = await adapter._parse_with_scroll(
                parser, [card], fetch_description=True,
            )

        assert len(results) == 1
        assert results[0].description_snippet == "Detailed job description"
        assert results[0].external_id == "12345"

    async def test_parse_with_scroll_no_fetch_keeps_empty(self) -> None:
        """Without fetch_description, description stays at default."""
        page = _make_page(description_text="Should not appear")
        card = _make_card()

        adapter = LinkedInAdapter(page)

        from src.platforms.linkedin.parser import LinkedInParser

        parser = LinkedInParser(SearchFilters(max_pages=1))
        results = await adapter._parse_with_scroll(
            parser, [card], fetch_description=False,
        )

        assert len(results) == 1
        assert results[0].description_snippet == ""
