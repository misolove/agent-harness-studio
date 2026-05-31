from fastapi import APIRouter, Body

from scrapers import HybridScraper, ScrapRequest, PhaseStatus

router = APIRouter()


@router.post("/api/web/scrape")
async def web_scrape(url: str = Body(..., embed=True)):
    if not url:
        return {"status": "error", "message": "URL is required"}

    try:
        scraper = HybridScraper()
        result = await scraper.scrape(ScrapRequest(url=url))

        response = result.model_dump()

        if result.status == PhaseStatus.SUCCESS:
            response["status"] = "ok"
            response["source"] = result.phase_used
        else:
            response["status"] = "error"
            response["message"] = "All scraping phases failed."

        return response
    except Exception as e:
        return {
            "status": "error",
            "message": f"Hybrid pipeline crash: {str(e)}",
            "url": url,
            "source": "hybrid",
        }
