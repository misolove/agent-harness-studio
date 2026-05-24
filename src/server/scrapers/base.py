"""Abstract base scraper interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from .models import PhaseAttempt, PhaseName, PhaseStatus, ScrapRequest, ScrapResult

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """All scraper phases implement this interface.

    Subclasses must:
    * Set ``phase_name`` to their :class:`PhaseName` value.
    * Implement :meth:`_do_scrape` with phase-specific logic.
    * Call ``super().scrape(...)`` — the base class handles timing, attempt
      logging, and error wrapping.
    """

    phase_name: PhaseName = PhaseName.FIRECRAWL  # override in subclass
    default_timeout: int = 15  # seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(
        self,
        request: ScrapRequest,
        timeout: Optional[int] = None,
    ) -> ScrapResult:
        """Run this phase and return a :class:`ScrapResult`.

        The base class measures wall-clock time and catches all exceptions so
        callers never need to wrap calls in try/except.
        """
        attempt = PhaseAttempt(phase=self.phase_name, status=PhaseStatus.SKIPPED)
        started = datetime.now(timezone.utc)

        effective_timeout = timeout or request.timeout or self.default_timeout

        try:
            result = await self._do_scrape(request, timeout=effective_timeout)
            # If the subclass didn't set phase_used, fill it in.
            if result.phase_used is None:
                result.phase_used = self.phase_name
            attempt.status = PhaseStatus.SUCCESS if result.succeeded else PhaseStatus.FAILURE

        except Exception as exc:
            logger.exception("[%s] error scraping %s", self.phase_name, request.url)
            result = ScrapResult(
                status=PhaseStatus.ERROR,
                url=request.url,
                phase_used=self.phase_name,
            )
            attempt.status = PhaseStatus.ERROR
            attempt.error_message = str(exc)[:500]

        finished = datetime.now(timezone.utc)
        attempt.started_at = started
        attempt.finished_at = finished
        attempt.duration_ms = int((finished - started).total_seconds() * 1000)

        # Attach this attempt to the result's attempt log.
        result.attempts.append(attempt)
        return result

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_scrape(
        self,
        request: ScrapRequest,
        timeout: int,
    ) -> ScrapResult:
        """Perform the actual scraping.  Raise on any unrecoverable error."""
        ...  # pragma: no cover
