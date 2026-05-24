"""Phase 1 — Firecrawl (primary scraper, requires API key)."""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import BaseScraper
from .models import PhaseName, PhaseStatus, ScrapRequest, ScrapResult

logger = logging.getLogger(__name__)


class FirecrawlScraper(BaseScraper):
    """Wraps the ``firecrawl-py`` SDK.

    Expects the ``FIRECRAWL_API_KEY`` environment variable to be set.
    Supports Firecrawl SDK v1/v2 response shapes.
    """

    phase_name = PhaseName.FIRECRAWL

    async def _do_scrape(
        self,
        request: ScrapRequest,
        timeout: int,
    ) -> ScrapResult:
        try:
            from firecrawl import FirecrawlApp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "firecrawl-py is not installed. Run: pip install firecrawl-py"
            ) from exc

        api_key = os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise RuntimeError("FIRECRAWL_API_KEY environment variable is not set")

        app = FirecrawlApp(api_key=api_key)

        # firecrawl-py's scrape/scrape_url methods are synchronous, so we run
        # them in a thread to keep FastAPI's event loop responsive.
        import asyncio

        def _scrape_sync() -> Any:
            # Firecrawl SDK v2: scrape(url, formats=[...])
            scrape = getattr(app, "scrape", None)
            if scrape is not None:
                return scrape(
                    request.url,
                    formats=["markdown", "html"],
                    timeout=timeout * 1000,
                )

            # Older SDK fallback: scrape_url(url, formats=[...])
            scrape_url = getattr(app, "scrape_url")
            return scrape_url(request.url, formats=["markdown", "html"])

        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _scrape_sync),
            timeout=timeout + 5,
        )

        result_data: dict[str, Any] = {}
        if hasattr(result, "model_dump"):
            result_data = result.model_dump()
        elif hasattr(result, "dict"):
            result_data = result.dict()
        elif isinstance(result, dict):
            result_data = result
        else:
            result_data = {"raw": str(result)}

        data_block = result_data.get("data") if isinstance(result_data.get("data"), dict) else {}
        markdown = result_data.get("markdown") or data_block.get("markdown") or ""
        html = result_data.get("html") or data_block.get("html") or ""
        metadata = result_data.get("metadata") or data_block.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        title = metadata.get("title") or metadata.get("ogTitle") or result_data.get("title")

        if not markdown:
            return ScrapResult(
                status=PhaseStatus.FAILURE,
                url=request.url,
                title=title,
                metadata=metadata,
                phase_used=self.phase_name,
            )

        return ScrapResult(
            status=PhaseStatus.SUCCESS,
            url=request.url,
            title=title,
            markdown=markdown,
            raw_html=html if request.include_raw_html else None,
            metadata=metadata,
            source="firecrawl",
            phase_used=self.phase_name,
        )
