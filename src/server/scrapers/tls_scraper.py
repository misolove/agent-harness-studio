"""Phase 3 — TLS Impersonation via curl_cffi.

Uses a Chrome TLS fingerprint to bypass basic WAF / Cloudflare challenges
that block standard httpx / requests clients.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseScraper
from .models import PhaseName, PhaseStatus, ScrapRequest, ScrapResult

logger = logging.getLogger(__name__)


class TlsScraper(BaseScraper):
    """Scrapes using ``curl_cffi`` with Chrome TLS impersonation.

    This bypasses many TLS-fingerprint–based blocks (Cloudflare, etc.)
    without needing a full headless browser.
    """

    phase_name = PhaseName.TLS

    # A set of common browser-like headers to accompany the TLS fingerprint.
    _DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    async def _do_scrape(
        self,
        request: ScrapRequest,
        timeout: int,
    ) -> ScrapResult:
        try:
            from curl_cffi.requests import AsyncSession  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "curl_cffi is not installed. Run: pip install curl_cffi"
            ) from exc

        import asyncio
        import re

        async with AsyncSession(impersonate="chrome") as session:
            resp = await session.get(
                request.url,
                headers=self._DEFAULT_HEADERS,
                timeout=timeout,
                allow_redirects=True,
            )

        if resp.status_code != 200:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                metadata={"http_status": resp.status_code},
                phase_used=self.phase_name,
            )

        html = resp.text
        if not html or len(html.strip()) < 100:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                phase_used=self.phase_name,
            )

        # Extract <title> from HTML.
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else None

        # Convert HTML to a rough markdown-like representation.
        # For a production pipeline you'd swap this for html2text / markdownify.
        try:
            from markdownify import markdownify as md  # type: ignore[import-untyped]

            markdown = md(html)
        except ImportError:
            # Fallback: strip tags naively.
            clean = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
            clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.IGNORECASE | re.DOTALL)
            clean = re.sub(r"<[^>]+>", "\n", clean)
            clean = re.sub(r"\n{3,}", "\n\n", clean)
            markdown = clean.strip()

        return ScrapResult(
            status=PhaseStatus.SUCCESS,
            url=str(resp.url),
            title=title,
            markdown=markdown,
            raw_html=html if request.include_raw_html else None,
            metadata={
                "http_status": resp.status_code,
                "content_type": resp.headers.get("Content-Type", ""),
            },
            source="tls_impersonation",
            phase_used=self.phase_name,
        )
