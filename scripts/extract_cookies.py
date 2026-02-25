"""Extract LinkedIn cookies via patchright for authenticated searches.

Usage:
    .venv/bin/python scripts/extract_cookies.py

Opens a Chromium window. Log in to LinkedIn manually, then press Enter
in the terminal. Cookies are saved to config/linkedin_cookies.json.
"""

import json
from pathlib import Path

from patchright.sync_api import sync_playwright

OUTPUT_PATH = Path("config/linkedin_cookies.json")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")

        input("\n>>> Log in to LinkedIn, then press Enter here to save cookies...")

        cookies = context.cookies()
        OUTPUT_PATH.write_text(json.dumps(cookies, indent=2))
        print(f"Saved {len(cookies)} cookies to {OUTPUT_PATH}")

        browser.close()


if __name__ == "__main__":
    main()
