"""Phase 2 — Jina Reader (free, no API key required)."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .base import BaseScraper
from .models import PhaseName, PhaseStatus, ScrapRequest, ScrapResult

logger = logging.getLogger(__name__)

_JINA_READER_BASE = "https://r.jina.ai/"


class JinaScraper(BaseScraper):
    """Scrapes via the Jina Reader public endpoint.

    ``GET https://r.jina.ai/{url}`` returns clean Markdown of the page.
    No API key is needed but rate-limits apply for free usage.
    """

    phase_name = PhaseName.JINA

    async def _do_scrape(
        self,
        request: ScrapRequest,
        timeout: int,
    ) -> ScrapResult:
        target_url = f"{_JINA_READER_BASE}{request.url}"

        headers = {
            "Accept": "text/markdown",
            "X-Return-Format": "markdown",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(target_url)

        if resp.status_code != 200:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                metadata={"http_status": resp.status_code},
                phase_used=self.phase_name,
            )

        markdown = resp.text
        if not markdown or len(markdown.strip()) < 50:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                phase_used=self.phase_name,
            )

        # Jina sometimes returns a title in the X-Title header.
        title = resp.headers.get("X-Title")

        return ScrapResult(
            status=PhaseStatus.SUCCESS,
            url=request.url,
            title=title,
            markdown=markdown,
            metadata={"http_status": resp.status_code},
            source="jina",
            phase_used=self.phase_name,
        )
