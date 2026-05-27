# Web Content Extraction Comparison: Firecrawl vs. Insane-Search

This document records the original Firecrawl vs. "Insane-Search" decision and the current hybrid implementation for the Agent Harness Studio Web Context feature.

> Implementation update (2026-05-27): the hybrid strategy below has been implemented under `src/server/scrapers/`. `/api/web/scrape` now orchestrates Firecrawl → Jina → TLS/curl_cffi → Browser/Playwright-style fallback and returns pipeline phase details for the UI.

## Feature Overview

Agent Harness Studio requires a reliable way to turn public URLs into clean Markdown context for AI agents. The current `/api/web/scrape` endpoint uses a hybrid pipeline rather than Firecrawl alone.

---

## Comparison Matrix

| Feature | Firecrawl Phase | Local Fallback Phases |
|:---|:---|:---|
| **Primary Method** | Cloud API (SaaS) | Local / Distributed Probes |
| **Authentication** | Required (`FIRECRAWL_API_KEY`) | None (except premium targets) |
| **JS Rendering** | Server-side (Cloud) | Phase 3 (Local Playwright) |
| **Markdown Quality** | Excellent (Refined by Firecrawl) | High (Phase 1/2 via Jina/Probes) |
| **Blocking Resistance** | High (Proxies included) | Extreme (TLS Impersonation + Phased) |
| **Latency** | Medium (Network trip to API) | Variable (Fast Phase 0/1, Slow Phase 3) |
| **Complexity** | Very Low (Simple SDK) | High (Requires dependency management) |
| **Cost** | Paid (Tier-based) | Free (Infrastructure/Compute cost only) |

---

## Deep Dive: Insane-Search Phased Escalation

The "Insane-Search" approach follows a 4-phase adaptive loop to ensure maximum success rate while minimizing resource consumption:

1.  **Phase 0: Cache Lookup**: Check public caches or previously stored context.
2.  **Phase 1: Lightweight Probes**: Use Jina Reader API or standard `curl` with varying User-Agents.
3.  **Phase 2: Identity Spoofing**: Use `curl_cffi` for TLS fingerprint impersonation to bypass Cloudflare and basic anti-bot measures.
4.  **Phase 3: Full Browser**: Execute Playwright/Chromium for pages requiring complex JS execution or interaction.

---

## Recommendation

**Verdict: Hybrid Strategy (Primary + Fallback) — Implemented**

The implemented approach uses **both** paths in a tiered strategy:

1.  **Primary: Firecrawl (if key available)**: If the user has provided a `FIRECRAWL_API_KEY`, use it as the default. It provides the highest quality and offloads compute/proxy management to the service.
2.  **Fallback/Default: Insane-Search**: For users without an API key, or if Firecrawl fails (rate limits/unsupported pages), trigger the Insane-Search pipeline.

### Why this approach?
- **Zero-Config Onboarding**: Users can scrape web content immediately after installing Agent Harness Studio without signing up for external services.
- **Privacy & Resilience**: Power users can prefer local extraction to keep data within their network.
- **Cost Efficiency**: Reduces reliance on paid tokens for simple pages that Phase 1 (Jina/Curl) can handle.

---

## Integration Status (Backend)

### 1. Scraper modules
The scraping logic lives in dedicated modules:

```
src/server/scrapers/hybrid.py
src/server/scrapers/firecrawl_scraper.py
src/server/scrapers/jina_scraper.py
src/server/scrapers/tls_scraper.py
src/server/scrapers/browser_scraper.py
```

### 2. Dependency Management
- `curl_cffi` is used by the TLS phase when available.
- Browser fallback requires local browser support; if missing, the earlier phases still work.

### 3. UI Updates
- The Web Context panel renders pipeline phase/provider output through `ScrapingPipeline.jsx`.
- A future settings toggle can still expose provider preference, but the default path is already automatic fallback.
