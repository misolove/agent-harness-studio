"""Hybrid orchestrator — tries scraper phases in order, returns first success."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from .base import BaseScraper
from .browser_scraper import BrowserScraper
from .firecrawl_scraper import FirecrawlScraper
from .jina_scraper import JinaScraper
from .models import PhaseAttempt, PhaseName, PhaseStatus, ScrapRequest, ScrapResult
from .tls_scraper import TlsScraper

logger = logging.getLogger(__name__)

# Default pipeline order (skip platform-specific phase — not yet implemented).
DEFAULT_PHASE_ORDER: list[PhaseName] = [
    PhaseName.FIRECRAWL,
    PhaseName.JINA,
    PhaseName.TLS,
    PhaseName.BROWSER,
]


class HybridScraper:
    """Orchestrates multiple scraping phases.

    Phases are executed sequentially.  The first phase that returns a
    successful result wins; subsequent phases are skipped.

    Usage::

        scraper = HybridScraper()
        result = await scraper.scrape(ScrapRequest(url="https://example.com"))
        print(result.phase_used)  # e.g. "firecrawl"
    """

    def __init__(
        self,
        phase_order: Optional[Sequence[PhaseName]] = None,
    ) -> None:
        self.phase_order = list(phase_order) if phase_order else DEFAULT_PHASE_ORDER

        # Instantiate all phase scrapers.
        self._scrapers: dict[PhaseName, BaseScraper] = {
            PhaseName.FIRECRAWL: FirecrawlScraper(),
            PhaseName.JINA: JinaScraper(),
            PhaseName.TLS: TlsScraper(),
            PhaseName.BROWSER: BrowserScraper(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(self, request: ScrapRequest | str) -> ScrapResult:
        """Run the hybrid pipeline for *request.url*."""
        if isinstance(request, str):
            request = ScrapRequest(url=request)
            
        all_attempts: list[PhaseAttempt] = []
        phases_to_run = request.phases or self.phase_order

        last_result: Optional[ScrapResult] = None

        for phase_name in phases_to_run:
            scraper = self._scrapers.get(phase_name)
            if scraper is None:
                logger.warning("[hybrid] no scraper registered for phase %s — skipping", phase_name)
                all_attempts.append(
                    PhaseAttempt(
                        phase=phase_name,
                        status=PhaseStatus.SKIPPED,
                        error_message="No scraper registered for this phase",
                    )
                )
                continue

            logger.info("[hybrid] trying phase %s for %s", phase_name, request.url)

            try:
                result = await scraper.scrape(request)
            except Exception as exc:
                logger.exception("[hybrid] unexpected error in phase %s", phase_name)
                all_attempts.append(
                    PhaseAttempt(
                        phase=phase_name,
                        status=PhaseStatus.ERROR,
                        error_message=str(exc)[:500],
                    )
                )
                last_result = ScrapResult(
                    status=PhaseStatus.ERROR,
                    url=request.url,
                    phase_used=phase_name,
                    attempts=all_attempts,
                )
                continue

            # Merge attempts from the phase into our master list.
            all_attempts.extend(result.attempts)

            if result.succeeded:
                logger.info(
                    "[hybrid] phase %s succeeded for %s (%d chars)",
                    phase_name,
                    request.url,
                    len(result.markdown or ""),
                )
                result.attempts = all_attempts
                return result

            # Phase failed — keep going.
            last_result = result
            logger.info("[hybrid] phase %s failed, continuing...", phase_name)

        # All phases exhausted — return the last failure result.
        if last_result is not None:
            last_result.attempts = all_attempts
            return last_result

        # Edge case: no phases ran at all.
        return ScrapResult(
            status=PhaseStatus.ERROR,
            url=request.url,
            attempts=all_attempts,
        )
