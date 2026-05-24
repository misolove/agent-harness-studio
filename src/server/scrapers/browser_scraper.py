"""Phase 4 — Playwright headless browser (last resort for JS-heavy sites)."""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseScraper
from .models import PhaseName, PhaseStatus, ScrapRequest, ScrapResult

logger = logging.getLogger(__name__)


class BrowserScraper(BaseScraper):
    """Scrapes using Playwright headless Chromium.

    Waits for ``networkidle`` to ensure JS-driven content has loaded, then
    extracts ``document.body.innerText`` as the textual content.
    """

    phase_name = PhaseName.BROWSER
    default_timeout = 30  # browser phases need more time

    async def _do_scrape(
        self,
        request: ScrapRequest,
        timeout: int,
    ) -> ScrapResult:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            try:
                await page.goto(
                    request.url,
                    wait_until="networkidle",
                    timeout=timeout * 1000,  # ms
                )
            except Exception as exc:
                # networkidle can time out on very slow pages — fall back to domcontentloaded.
                logger.warning(
                    "[browser] networkidle timeout for %s, falling back to domcontentloaded: %s",
                    request.url,
                    exc,
                )
                await page.goto(
                    request.url,
                    wait_until="domcontentloaded",
                    timeout=timeout * 1000,
                )

            title = await page.title()

            # Extract visible text content.
            text_content = await page.evaluate("document.body.innerText")

            # Optionally extract raw HTML.
            raw_html = None
            if request.include_raw_html:
                raw_html = await page.content()

            await browser.close()

        if not text_content or len(text_content.strip()) < 50:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                title=title,
                phase_used=self.phase_name,
            )

        # The innerText is already plain text. Treat it as markdown (it won't
        # have rich formatting but is usable for LLM ingestion).
        markdown = text_content.strip()

        return ScrapResult(
            status=PhaseStatus.SUCCESS,
            url=page.url if hasattr(page, "url") else request.url,
            title=title,
            markdown=markdown,
            raw_html=raw_html,
            metadata={"scraper": "playwright"},
            source="browser",
            phase_used=self.phase_name,
        )
