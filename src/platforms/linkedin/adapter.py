"""LinkedIn platform adapter — wires URL builder, parser, and browser page."""

import logging
from typing import Any

from src.browser.actions import random_sleep, scroll_until_stable
from src.core.config import SearchConfig
from src.core.schemas import JobCandidate
from src.platforms.base import PlatformAdapter
from src.platforms.linkedin.parser import LinkedInParser
from src.platforms.linkedin.searcher import build_url, should_stop_pagination
from src.platforms.linkedin.selectors import CARD_SELECTORS, DESCRIPTION_PANEL_SELECTORS

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
            candidates = await self._parse_with_scroll(
                parser, cards, fetch_description=config.fetch_description,
            )
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

    async def _parse_with_scroll(
        self,
        parser: LinkedInParser,
        cards: list[Any],
        *,
        fetch_description: bool = False,
    ) -> list[JobCandidate]:
        """Scroll each card into view before parsing to defeat occlusion.

        LinkedIn strips inner HTML from off-screen cards (virtual DOM).
        scrollIntoView restores the content so the parser can extract fields.
        A brief wait after scrolling gives the browser time to render.

        If fetch_description is True, clicks each card to open the side panel
        and extracts the full job description text.
        """
        results: list[JobCandidate] = []
        for card in cards:
            try:
                await card.scroll_into_view_if_needed()
                await self._page.wait_for_timeout(150)
                candidate = await parser.parse_card(card)
                if candidate is not None:
                    if fetch_description:
                        desc = await self._fetch_description(card)
                        if desc:
                            candidate = candidate.model_copy(
                                update={"description_snippet": desc},
                            )
                    results.append(candidate)
            except Exception:
                logger.debug("Failed to scroll/parse card, skipping", exc_info=True)
        return results

    async def _fetch_description(self, card: Any) -> str:
        """Click a card and extract the job description from the side panel.

        Returns the full description text, or "" on any failure (L12).
        Adds a random delay after extraction for anti-detection.
        """
        try:
            await card.click()
            # Wait for the description panel to appear
            for selector in DESCRIPTION_PANEL_SELECTORS:
                try:
                    el = await self._page.wait_for_selector(selector, timeout=5000)
                    if el is not None:
                        text = await el.text_content()
                        if text and text.strip():
                            # Normalize whitespace: collapse runs of whitespace
                            desc = " ".join(text.split())
                            await random_sleep(1.0, 2.5)
                            return desc
                except Exception:
                    continue
        except Exception:
            logger.debug("Failed to fetch description for card", exc_info=True)
        return ""

    async def _find_cards(self) -> list[Any]:
        """Find job cards using fallback selectors."""
        for selector in CARD_SELECTORS:
            cards = await self._page.query_selector_all(selector)
            if cards:
                logger.debug("Found %d cards with selector '%s'", len(cards), selector)
                return cards  # type: ignore[no-any-return]
        logger.warning("No cards found with any selector")
        return []
