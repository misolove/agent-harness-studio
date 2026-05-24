# Web Content Extraction Comparison: Firecrawl vs. Insane-Search

This document evaluates the current Firecrawl integration against the proposed "Insane-Search" phased approach for the Agent Harness Studio Web Context feature.

## Feature Overview

Agent Harness Studio requires a reliable way to turn public URLs into clean Markdown context for AI agents. Currently, this is handled via a single `/api/web/scrape` endpoint using the Firecrawl SDK.

---

## Comparison Matrix

| Feature | Firecrawl (Current) | Insane-Search (Phased) |
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

**Verdict: Hybrid Strategy (Primary + Fallback)**

I recommend implementing **both** approaches in a tiered strategy to provide the best user experience:

1.  **Primary: Firecrawl (if key available)**: If the user has provided a `FIRECRAWL_API_KEY`, use it as the default. It provides the highest quality and offloads compute/proxy management to the service.
2.  **Fallback/Default: Insane-Search**: For users without an API key, or if Firecrawl fails (rate limits/unsupported pages), trigger the Insane-Search pipeline.

### Why this approach?
- **Zero-Config Onboarding**: Users can scrape web content immediately after installing Agent Harness Studio without signing up for external services.
- **Privacy & Resilience**: Power users can prefer local extraction to keep data within their network.
- **Cost Efficiency**: Reduces reliance on paid tokens for simple pages that Phase 1 (Jina/Curl) can handle.

---

## Integration Plan (Backend)

### 1. Refactor `src/server/app.py`
Move the scraping logic into a dedicated module `src/server/services/web_context.py`.

```python
# Proposed Structure
class WebScraper:
    def scrape(self, url: str):
        if self.has_firecrawl_key():
            try:
                return self.firecrawl_scrape(url)
            except Exception:
                pass # Fallback to insane-search
        
        return self.insane_search_scrape(url)
```

### 2. Dependency Management
- Add `curl_cffi` and `playwright` to `pyproject.toml` or `requirements.txt`.
- Add a setup script to run `playwright install chromium` on first use or during installation.

### 3. UI Updates
- Indicate in the Web Context panel which "Phase" or "Provider" was used to extract the content.
- Provide a toggle in settings to "Prefer Local Extraction (Insane-Search)" vs "Prefer Cloud (Firecrawl)".
