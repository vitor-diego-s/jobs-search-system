"""Reusable browser actions: scroll and sleep.

Design rules:
  L6  — Incremental scroll, not single jump. Max 5 attempts.
  L7  — All delays randomized. Floor values enforced in code.
  §8  — No fixed asyncio.sleep() anywhere except via random_sleep().
"""

import asyncio
import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

MAX_SCROLL_ATTEMPTS = 5

# Floor values (L7) — code enforces these regardless of caller args.
SCROLL_DELAY_FLOOR = 1.5
PAGE_DELAY_FLOOR = 3.0
KEYWORD_DELAY_FLOOR = 5.0


async def random_sleep(min_s: float, max_s: float) -> float:
    """Sleep for a random duration between min_s and max_s seconds.

    Floor enforcement: min_s is always respected as the absolute minimum.
    If max_s < min_s, max_s is raised to min_s.

    Returns the actual sleep duration (useful for testing).
    """
    floor = max(min_s, 0.0)
    ceiling = max(max_s, floor)
    duration = random.uniform(floor, ceiling)
    await asyncio.sleep(duration)
    return duration


async def scroll_until_stable(
    page: Any,
    *,
    card_selectors: tuple[str, ...],
    max_attempts: int = MAX_SCROLL_ATTEMPTS,
    scroll_delay_min: float = 1.5,
    scroll_delay_max: float = 3.0,
) -> int:
    """Scroll page incrementally until the card count stabilizes (L6).

    Args:
        page: Browser page object (patchright Page or mock).
        card_selectors: Tuple of CSS selectors to try (fallback order).
        max_attempts: Max scroll iterations before giving up.
        scroll_delay_min: Minimum delay between scrolls (floor: 1.5s).
        scroll_delay_max: Maximum delay between scrolls.

    Returns:
        Final card count found on the page.
    """
    # Enforce floor (L7)
    scroll_delay_min = max(scroll_delay_min, SCROLL_DELAY_FLOOR)
    scroll_delay_max = max(scroll_delay_max, scroll_delay_min)

    previous_count = 0

    for attempt in range(max_attempts):
        current_count = await _count_cards(page, card_selectors)
        logger.debug(
            "Scroll attempt %d/%d: %d cards (prev: %d)",
            attempt + 1, max_attempts, current_count, previous_count,
        )

        if current_count == previous_count and attempt > 0:
            logger.debug("Card count stable at %d — stopping scroll", current_count)
            break

        previous_count = current_count
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await random_sleep(scroll_delay_min, scroll_delay_max)

    return previous_count


async def _count_cards(page: Any, selectors: tuple[str, ...]) -> int:
    """Count cards using the first matching selector."""
    for selector in selectors:
        cards = await page.query_selector_all(selector)
        if cards:
            return len(cards)
    return 0
