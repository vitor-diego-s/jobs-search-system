"""LinkedIn platform adapter — wires URL builder, parser, and browser page."""

import logging
from typing import Any

from src.browser.actions import random_sleep, scroll_until_stable
from src.core.config import SearchConfig
from src.core.schemas import JobCandidate
from src.platforms.base import PlatformAdapter
from src.platforms.linkedin.parser import LinkedInParser
from src.platforms.linkedin.searcher import build_url, should_stop_pagination
from src.platforms.linkedin.selectors import CARD_SELECTORS

logger = logging.getLogger(__name__)


class LinkedInAdapter(PlatformAdapter):
    """LinkedIn search adapter.

    Requires a browser page object (patchright Page) injected via constructor.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    @property
    def platform_id(self) -> str:
        return "linkedin"

    async def search(self, config: SearchConfig) -> list[JobCandidate]:
        """Search LinkedIn for jobs matching the given config."""
        parser = LinkedInParser(config.filters)
        all_candidates: list[JobCandidate] = []

        for page_num in range(config.filters.max_pages):
            url = build_url(config.keyword, config.filters, page_num)
            logger.info("Navigating to page %d: %s", page_num, url)

            await self._page.goto(url)
            await scroll_until_stable(self._page, card_selectors=CARD_SELECTORS)

            cards = await self._find_cards()
            candidates = await parser.parse_cards(cards)
            all_candidates.extend(candidates)

            logger.info(
                "Page %d: found %d cards, parsed %d candidates",
                page_num, len(cards), len(candidates),
            )

            if should_stop_pagination(len(cards), page_num):
                logger.info("Stopping pagination: %d cards < 25", len(cards))
                break

            # Delay between pages (L7: 3-7s)
            if page_num < config.filters.max_pages - 1:
                await random_sleep(3.0, 7.0)

        return all_candidates

    async def _find_cards(self) -> list[Any]:
        """Find job cards using fallback selectors."""
        for selector in CARD_SELECTORS:
            cards = await self._page.query_selector_all(selector)
            if cards:
                logger.debug("Found %d cards with selector '%s'", len(cards), selector)
                return cards  # type: ignore[no-any-return]
        logger.warning("No cards found with any selector")
        return []
