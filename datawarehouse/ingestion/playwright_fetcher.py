"""
Browser-rendered page fetcher using Playwright.

Handles JavaScript-rendered SPA pages, anti-bot challenges, and
dynamic content that simple HTTP requests cannot access.

Usage::

    from datawarehouse.ingestion import PlaywrightFetcher

    async with PlaywrightFetcher() as fetcher:
        html = await fetcher.fetch("https://example.com/spa-page")
"""

from __future__ import annotations

import asyncio
import logging
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from playwright.async_api import async_playwright  # type: ignore
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "playwright", "--quiet"]
    )
    print(
        "\n[SETUP] Playwright installed. Now run this manually:\n"
        "  playwright install chromium\n"
        "This downloads a browser binary (~150 MB) one time.\n"
    )
    # Don't auto-install Chromium — it's ~150MB and may fail in constrained envs.
    # Import will fail, but the user gets a clear instruction.

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        logger.warning(
            "Playwright installed but Chromium browser not yet downloaded. "
            "Run: playwright install chromium"
        )

logger = logging.getLogger("DataWarehouse.Ingestion")


class PlaywrightFetcher:
    """Headless Chromium fetcher for JavaScript-rendered content.

    Args:
        headless: Run browser in headless mode.
        timeout: Navigation timeout in milliseconds.
        user_agent: Custom User-Agent string.
        proxy: Optional proxy URL (e.g., ``"http://1.2.3.4:8080"``).
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> None:
        self._headless = headless
        self._timeout = timeout
        self._user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        self._proxy = proxy
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch the browser."""
        self._playwright = await async_playwright().start()
        launch_args: Dict[str, Any] = {
            "headless": self._headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if self._proxy:
            launch_args["proxy"] = {"server": self._proxy}

        self._browser = await self._playwright.chromium.launch(**launch_args)
        self._context = await self._browser.new_context(
            user_agent=self._user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        logger.info("Playwright browser launched (headless=%s)", self._headless)

    async def close(self) -> None:
        """Close the browser and clean up."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("Playwright browser closed")

    # ------------------------------------------------------------------
    # Fetchers
    # ------------------------------------------------------------------

    async def fetch(self, url: str, wait_for: str = "networkidle",
                    screenshot: bool = False) -> Dict[str, Any]:
        """Fetch a page with full JS rendering.

        Args:
            url: Target URL.
            wait_for: When to consider the page loaded
                      (``"networkidle"``, ``"load"``, ``"domcontentloaded"``).
            screenshot: If True, capture a screenshot (base64 PNG).

        Returns:
            Dict with ``url``, ``html``, ``title``, ``status``, ``screenshot`` (optional).
        """
        if not self._context:
            raise RuntimeError("Browser not started. Call start() or use async with.")

        page = await self._context.new_page()
        try:
            logger.debug("Fetching with Playwright: %s", url)
            resp = await page.goto(url, wait_until=wait_for, timeout=self._timeout)
            html = await page.content()
            title = await page.title()
            status = resp.status if resp else 0

            result: Dict[str, Any] = {
                "url": url,
                "html": html,
                "title": title,
                "status": status,
            }

            if screenshot:
                result["screenshot"] = await page.screenshot(
                    type="png", full_page=False,
                )

            return result

        except Exception as exc:
            logger.error("Playwright fetch failed for %s: %s", url, exc)
            return {"url": url, "html": "", "title": "", "status": 0, "error": str(exc)}
        finally:
            await page.close()

    async def fetch_data_links(self, url: str) -> List[str]:
        """Fetch a page and extract links to data files (CSV, JSON, Parquet).

        Args:
            url: Target URL.

        Returns:
            List of absolute URLs pointing to data files.
        """
        result = await self.fetch(url, wait_for="networkidle")
        html = result.get("html", "")
        if not html:
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(href.lower().endswith(ext) for ext in
                   (".csv", ".json", ".xml", ".parquet", ".zip", ".gz")):
                # Resolve relative URLs
                from urllib.parse import urljoin
                links.append(urljoin(url, href))

        logger.info("Found %d data links on %s", len(links), url)
        return links
