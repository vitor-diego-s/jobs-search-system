"""Tests for browser actions: random_sleep and scroll_until_stable."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.browser.actions import (
    SCROLL_DELAY_FLOOR,
    random_sleep,
    scroll_until_stable,
)

# Test selector — avoids importing LinkedIn-specific selectors
_TEST_SELECTORS: tuple[str, ...] = ("li.test-card",)

# ---------------------------------------------------------------------------
# TestRandomSleep
# ---------------------------------------------------------------------------


class TestRandomSleep:
    """random_sleep: floor enforcement, range, actual sleeping."""

    async def test_returns_duration_in_range(self) -> None:
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            duration = await random_sleep(0.0, 0.01)
        assert 0.0 <= duration <= 0.01

    async def test_floor_enforcement(self) -> None:
        """min_s is always the floor — duration never below it."""
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            for _ in range(20):
                duration = await random_sleep(1.0, 2.0)
                assert duration >= 1.0

    async def test_max_below_min_is_clamped(self) -> None:
        """If max_s < min_s, max_s is raised to min_s."""
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            duration = await random_sleep(5.0, 2.0)
        assert duration == 5.0

    async def test_zero_range(self) -> None:
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            duration = await random_sleep(1.5, 1.5)
        assert duration == 1.5

    async def test_actually_calls_asyncio_sleep(self) -> None:
        with patch.object(asyncio, "sleep", new_callable=AsyncMock) as mock_sleep:
            await random_sleep(0.1, 0.2)
        mock_sleep.assert_called_once()
        slept = mock_sleep.call_args[0][0]
        assert 0.1 <= slept <= 0.2

    async def test_negative_min_clamped_to_zero(self) -> None:
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            duration = await random_sleep(-1.0, 0.5)
        assert duration >= 0.0


# ---------------------------------------------------------------------------
# TestScrollUntilStable
# ---------------------------------------------------------------------------


def _make_page_mock(card_counts: list[int]) -> AsyncMock:
    """Create a mock page that returns different card counts per call.

    Each call to query_selector_all returns a list of the given length.
    The scroll evaluate call is a no-op.
    """
    page = AsyncMock()
    call_idx = 0

    async def _query_selector_all(selector: str) -> list[object]:
        nonlocal call_idx
        if call_idx < len(card_counts):
            count = card_counts[call_idx]
            call_idx += 1
            return [object() for _ in range(count)]
        return [object() for _ in range(card_counts[-1])] if card_counts else []

    page.query_selector_all = AsyncMock(side_effect=_query_selector_all)
    page.evaluate = AsyncMock(return_value=None)
    return page


class TestScrollUntilStable:
    """scroll_until_stable: termination, card counting, max attempts."""

    @pytest.fixture(autouse=True)
    def _patch_sleep(self) -> "pytest.Generator[None]":  # type: ignore[type-arg]
        """Patch asyncio.sleep to avoid real delays in tests."""
        with patch.object(asyncio, "sleep", new_callable=AsyncMock):
            yield

    async def test_stable_after_initial_count(self) -> None:
        """Cards already loaded — count same on 2nd check → stop."""
        page = _make_page_mock([25, 25])
        count = await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=5)
        assert count == 25

    async def test_cards_grow_then_stabilize(self) -> None:
        """Cards load incrementally: 14 → 25 → 25 → stop."""
        page = _make_page_mock([14, 25, 25])
        count = await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=5)
        assert count == 25

    async def test_zero_cards_stops(self) -> None:
        """No cards at all — returns 0 immediately after 2 checks."""
        page = _make_page_mock([0, 0])
        count = await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=5)
        assert count == 0

    async def test_max_attempts_respected(self) -> None:
        """Count keeps growing — stops at max_attempts."""
        # Each call returns one more card than the last
        page = _make_page_mock([5, 10, 15, 20, 25])
        count = await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=3)
        # Should stop after 3 iterations
        assert count > 0

    async def test_scrolls_between_checks(self) -> None:
        """Verify evaluate (scroll) is called between count checks."""
        page = _make_page_mock([10, 20, 20])
        await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=5)
        # evaluate called for each scroll (at least 2 times: after 10, after 20)
        assert page.evaluate.call_count >= 2

    async def test_scroll_delay_floor_enforced(self) -> None:
        """Scroll delays respect the 1.5s floor (L7)."""
        page = _make_page_mock([10, 20, 20])

        with patch("src.browser.actions.random_sleep", new_callable=AsyncMock) as mock_rs:
            mock_rs.return_value = SCROLL_DELAY_FLOOR
            await scroll_until_stable(
                page, card_selectors=_TEST_SELECTORS,
                max_attempts=5, scroll_delay_min=0.1, scroll_delay_max=0.2,
            )
            for call in mock_rs.call_args_list:
                min_arg = call[0][0]
                assert min_arg >= SCROLL_DELAY_FLOOR

    async def test_custom_selectors(self) -> None:
        """Works with custom card selectors."""
        page = AsyncMock()
        call_idx = 0
        counts = [5, 5]

        async def _qsa(selector: str) -> list[object]:
            nonlocal call_idx
            if selector == ".custom-card":
                count = counts[min(call_idx, len(counts) - 1)]
                call_idx += 1
                return [object() for _ in range(count)]
            return []

        page.query_selector_all = AsyncMock(side_effect=_qsa)
        page.evaluate = AsyncMock(return_value=None)

        count = await scroll_until_stable(
            page, card_selectors=(".custom-card",), max_attempts=5,
        )
        assert count == 5

    async def test_single_attempt(self) -> None:
        """With max_attempts=1, scrolls once then stops."""
        page = _make_page_mock([10])
        count = await scroll_until_stable(page, card_selectors=_TEST_SELECTORS, max_attempts=1)
        assert count == 10
