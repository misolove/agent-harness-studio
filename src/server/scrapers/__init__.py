"""Hybrid web scraping module for Agent Harness Studio.

Exports the main :class:`HybridScraper` orchestrator plus data models for
convenience.

Quick-start::

    from server.scrapers import HybridScraper, ScrapRequest

    scraper = HybridScraper()
    result = await scraper.scrape(ScrapRequest(url="https://example.com"))
    print(result.phase_used, result.title, result.markdown[:200])
"""

from .base import BaseScraper
from .browser_scraper import BrowserScraper
from .firecrawl_scraper import FirecrawlScraper
from .hybrid import HybridScraper
from .jina_scraper import JinaScraper
from .models import (
    PhaseAttempt,
    PhaseName,
    PhaseStatus,
    ScrapRequest,
    ScrapResult,
)
from .tls_scraper import TlsScraper

__all__ = [
    # Main entry point
    "HybridScraper",
    # Individual phases
    "BaseScraper",
    "FirecrawlScraper",
    "JinaScraper",
    "TlsScraper",
    "BrowserScraper",
    # Models
    "ScrapRequest",
    "ScrapResult",
    "PhaseAttempt",
    "PhaseName",
    "PhaseStatus",
]
