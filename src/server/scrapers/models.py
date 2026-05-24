"""Pydantic models for the hybrid scraping pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class PhaseName(str, Enum):
    """Names of each scraping phase, in execution order."""

    PLATFORM = "platform"
    FIRECRAWL = "firecrawl"
    JINA = "jina"
    TLS = "tls"
    BROWSER = "browser"


class PhaseStatus(str, Enum):
    """Result status for a single phase attempt."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ScrapRequest(BaseModel):
    """Inbound request to the hybrid scraper."""

    url: str = Field(..., description="Target URL to scrape")
    timeout: int = Field(
        default=15,
        ge=5,
        le=120,
        description="Per-phase timeout in seconds (browser phase uses 2×)",
    )
    phases: Optional[list[PhaseName]] = Field(
        default=None,
        description="Explicit phase order. None → use default pipeline.",
    )
    include_raw_html: bool = Field(
        default=False,
        description="Whether to include the raw HTML in the result.",
    )


class PhaseAttempt(BaseModel):
    """Record of a single phase attempt within a pipeline run."""

    phase: PhaseName
    status: PhaseStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class ScrapResult(BaseModel):
    """Unified result returned by every scraper phase."""

    status: PhaseStatus = PhaseStatus.SUCCESS
    url: str
    title: Optional[str] = None
    markdown: Optional[str] = None
    raw_html: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    phase_used: Optional[PhaseName] = None
    attempts: list[PhaseAttempt] = Field(default_factory=list)

    class Config:
        use_enum_values = True

    # Convenience -----------------------------------------------------------------

    @property
    def succeeded(self) -> bool:
        return self.status == PhaseStatus.SUCCESS and bool(self.markdown)
