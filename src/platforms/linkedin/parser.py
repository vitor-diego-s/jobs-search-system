"""LinkedIn DOM parser — converts card elements into JobCandidate objects.

Design rules (from lessons-applied):
  L2  — is_easy_apply comes from SearchFilters, never DOM.
  L4  — Every selector lookup uses a fallback tuple.
  L5  — Titles are split on '\\n' and first line taken.
  L12 — Missing company (or any optional field) returns "" (never crashes).
"""

import logging
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse, urlunparse

from src.core.config import SearchFilters
from src.core.schemas import JobCandidate
from src.platforms.linkedin.selectors import (
    COMPANY_SELECTORS,
    JOB_ID_ATTR,
    JOB_ID_ATTR_FALLBACK,
    LOCATION_SELECTORS,
    POSTED_TIME_SELECTORS,
    TITLE_LINK_SELECTORS,
)

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://www.linkedin.com"


@runtime_checkable
class ElementLike(Protocol):
    """Minimal element interface so tests can use AsyncMock instead of patchright."""

    async def query_selector(self, selector: str) -> "ElementLike | None": ...
    async def get_attribute(self, name: str) -> str | None: ...
    async def text_content(self) -> str | None: ...


class LinkedInParser:
    """Parses LinkedIn search-result card elements into JobCandidate objects."""

    def __init__(self, filters: SearchFilters) -> None:
        self._is_easy_apply = filters.easy_apply_only
        self._workplace_type = self._resolve_workplace_type(filters.workplace_type)

    async def parse_cards(self, cards: list[ElementLike]) -> list[JobCandidate]:
        """Parse multiple cards, skipping any that fail (L12)."""
        results: list[JobCandidate] = []
        for card in cards:
            try:
                candidate = await self.parse_card(card)
                if candidate is not None:
                    results.append(candidate)
            except Exception:
                logger.debug("Failed to parse card, skipping", exc_info=True)
        return results

    async def parse_card(self, card: ElementLike) -> JobCandidate | None:
        """Parse a single card element into a JobCandidate.

        Returns None if external_id cannot be extracted (required field).
        """
        external_id = await self._parse_external_id(card)
        if external_id is None:
            logger.debug("Card missing external_id — skipping")
            return None

        title_link = await self._find_first(card, TITLE_LINK_SELECTORS)
        title = await self._parse_title(card, title_link)
        url = await self._parse_url(title_link, external_id)
        company = await self._parse_text_fallback(card, COMPANY_SELECTORS)
        location = await self._parse_text_fallback(card, LOCATION_SELECTORS)
        posted_time = await self._parse_posted_time(card)

        return JobCandidate(
            external_id=external_id,
            platform="linkedin",
            title=title,
            company=company,
            location=location,
            url=url,
            is_easy_apply=self._is_easy_apply,
            workplace_type=self._workplace_type,
            posted_time=posted_time,
        )

    # --- Private helpers ---

    async def _parse_external_id(self, card: ElementLike) -> str | None:
        """Extract job ID from card attributes (primary then fallback)."""
        try:
            job_id = await card.get_attribute(JOB_ID_ATTR)
            if job_id and job_id.strip():
                return job_id.strip()
            job_id = await card.get_attribute(JOB_ID_ATTR_FALLBACK)
            if job_id and job_id.strip():
                return job_id.strip()
        except Exception:
            logger.debug("Error extracting external_id", exc_info=True)
        return None

    async def _parse_title(
        self, card: ElementLike, title_link: ElementLike | None,
    ) -> str:
        """Extract title text from <strong> inside title link, or aria-label.

        LinkedIn wraps the clean title in <strong> inside the <a> link.
        The <a>'s full text_content has leading \\n and duplicated text (L5),
        so we prefer <strong> text or aria-label as reliable sources.
        """
        try:
            # Priority 1: <strong> inside card (clean, no duplication)
            strong = await card.query_selector("a span strong")
            if strong is not None:
                text = await strong.text_content()
                if text and text.strip():
                    return text.strip()

            # Priority 2: aria-label on title link (may include "with verification")
            if title_link is not None:
                aria = await title_link.get_attribute("aria-label")
                if aria and aria.strip():
                    label = aria.strip()
                    # Strip LinkedIn's "with verification" suffix
                    suffix = " with verification"
                    if label.endswith(suffix):
                        label = label[: -len(suffix)]
                    return label

            # Priority 3: text_content with strip-then-split (fallback)
            if title_link is not None:
                raw = await title_link.text_content()
                if raw:
                    return raw.strip().split("\n")[0].strip()

            return ""
        except Exception:
            logger.debug("Error parsing title", exc_info=True)
            return ""

    async def _parse_url(self, title_link: ElementLike | None, job_id: str) -> str:
        """Extract and clean URL from title link href.

        Strips tracking query params. Falls back to canonical URL from job_id.
        """
        try:
            if title_link is None:
                return f"{LINKEDIN_BASE}/jobs/view/{job_id}/"
            href = await title_link.get_attribute("href")
            if not href:
                return f"{LINKEDIN_BASE}/jobs/view/{job_id}/"
            return self._clean_url(href)
        except Exception:
            logger.debug("Error parsing URL", exc_info=True)
            return f"{LINKEDIN_BASE}/jobs/view/{job_id}/"

    async def _parse_text_fallback(self, card: ElementLike, selectors: tuple[str, ...]) -> str:
        """Try selectors in order, return first non-empty text or "" (L12)."""
        try:
            el = await self._find_first(card, selectors)
            if el is None:
                return ""
            text = await el.text_content()
            return text.strip() if text else ""
        except Exception:
            logger.debug("Error parsing text with fallback selectors", exc_info=True)
            return ""

    async def _parse_posted_time(self, card: ElementLike) -> str:
        """Extract posted time, preferring datetime attribute on <time> elements."""
        try:
            el = await self._find_first(card, POSTED_TIME_SELECTORS)
            if el is None:
                return ""
            # <time> elements often have a datetime attribute
            dt_attr = await el.get_attribute("datetime")
            if dt_attr and dt_attr.strip():
                return dt_attr.strip()
            text = await el.text_content()
            return text.strip() if text else ""
        except Exception:
            logger.debug("Error parsing posted_time", exc_info=True)
            return ""

    async def _find_first(
        self, parent: ElementLike, selectors: tuple[str, ...]
    ) -> ElementLike | None:
        """Return the first element matching any selector in order."""
        for selector in selectors:
            try:
                el = await parent.query_selector(selector)
                if el is not None:
                    return el
            except Exception:
                logger.debug("Selector '%s' raised, trying next", selector, exc_info=True)
        return None

    @staticmethod
    def _clean_url(href: str) -> str:
        """Strip tracking params and prepend domain if relative."""
        if href.startswith("/"):
            href = f"{LINKEDIN_BASE}{href}"
        parsed = urlparse(href)
        # Keep only scheme, netloc, path — drop query and fragment
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    @staticmethod
    def _resolve_workplace_type(values: list[str]) -> str:
        """Return workplace type if there is exactly one value, else ""."""
        if len(values) == 1:
            return values[0].lower().strip()
        return ""
