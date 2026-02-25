"""Browser session management using patchright.

Hard rules (ARCHITECTURE.md §8):
  - headless=False always (no config override)
  - Single browser context per run
  - Cookie auth only (no login flow)
  - patchright, not vanilla playwright
"""

import json
import logging
from pathlib import Path
from types import TracebackType
from typing import Any

from patchright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.core.config import BrowserConfig

logger = logging.getLogger(__name__)


class BrowserSession:
    """Async context manager that owns one patchright browser + context + page.

    Usage::

        async with BrowserSession(config) as session:
            page = session.page
            await page.goto("https://...")
    """

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        """The single page for this session. Raises if not entered."""
        if self._page is None:
            msg = "BrowserSession not entered — use 'async with'"
            raise RuntimeError(msg)
        return self._page

    async def __aenter__(self) -> "BrowserSession":
        pw = await async_playwright().start()
        self._playwright = pw

        # headless=False is non-negotiable (anti-detection)
        self._browser = await pw.chromium.launch(headless=False)

        cookies = _load_cookies(self._config.cookies_path)
        self._context = await self._browser.new_context()
        if cookies:
            await self._context.add_cookies(cookies)
            logger.info("Loaded %d cookies from %s", len(cookies), self._config.cookies_path)
        else:
            logger.warning("No cookies loaded — session will be unauthenticated")

        self._context.set_default_timeout(self._config.timeout_ms)
        self._page = await self._context.new_page()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()


def _load_cookies(path: str) -> list[Any]:
    """Load cookies from a JSON file. Returns empty list on any failure."""
    cookie_path = Path(path)
    if not cookie_path.exists():
        logger.debug("Cookie file not found: %s", path)
        return []
    try:
        data = json.loads(cookie_path.read_text())
        if isinstance(data, list):
            return data
        logger.warning("Cookie file is not a JSON array: %s", path)
        return []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load cookies from %s: %s", path, e)
        return []
