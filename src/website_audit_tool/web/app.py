"""FastAPI web application for the Website Audit Tool."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from website_audit_tool.adapters.llm_client import AnthropicClient
from website_audit_tool.adapters.scraper import PageScraper, ScraperError
from website_audit_tool.use_cases.audit_page import AuditPageUseCase

load_dotenv()

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Website Audit Tool", docs_url=None, redoc_url=None)

_api_key = os.getenv("ANTHROPIC_API_KEY", "")
_llm: AnthropicClient | None = AnthropicClient(api_key=_api_key) if _api_key else None


class AuditRequest(BaseModel):
    url: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/scrape")
def scrape(body: AuditRequest) -> dict[str, object]:
    scraper = PageScraper()
    try:
        metrics = scraper.scrape(body.url)
    except ScraperError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"url": metrics.url, "metrics": _metrics_dict(metrics)}


@app.post("/analyse")
def analyse(body: AuditRequest) -> dict[str, object]:
    if not _llm:
        raise HTTPException(status_code=503, detail="LLM not configured — set ANTHROPIC_API_KEY.")
    scraper = PageScraper()
    use_case = AuditPageUseCase(scraper=scraper, llm_client=_llm)
    try:
        result = use_case.execute(body.url)
    except ScraperError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.warning("LLM analysis failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI analysis failed — try again later.")
    return {
        "analysis": result.analysis.model_dump(),
        "scraped_data_path": result.scraped_data_path,
        "prompt_log_path": result.prompt_log_path,
    }


@app.post("/audit")
def audit(body: AuditRequest) -> dict[str, object]:
    scraper = PageScraper()

    if _llm:
        use_case = AuditPageUseCase(scraper=scraper, llm_client=_llm)
        try:
            result = use_case.execute(body.url)
        except ScraperError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:
            logger.warning("LLM analysis failed, returning metrics only: %s", exc)
            # Fall through to metrics-only path
            try:
                metrics = scraper.scrape(body.url)
            except ScraperError as scrape_exc:
                raise HTTPException(status_code=422, detail=str(scrape_exc))
            return _metrics_response(metrics)

        return {
            "url": result.metrics.url,
            "metrics": _metrics_dict(result.metrics),
            "analysis": result.analysis.model_dump(),
            "prompt_log_path": result.prompt_log_path,
        }

    # No API key — scrape only
    try:
        metrics = scraper.scrape(body.url)
    except ScraperError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _metrics_response(metrics)


def _metrics_dict(metrics: object) -> dict[str, object]:
    from website_audit_tool.core.models import PageMetrics
    assert isinstance(metrics, PageMetrics)
    return {
        "word_count": metrics.word_count,
        "header_counts": metrics.header_counts,
        "cta_count": metrics.cta_count,
        "internal_links": len(metrics.internal_links),
        "external_links": len(metrics.external_links),
        "images_count": metrics.images_count,
        "images_missing_alt": metrics.images_missing_alt,
        "images_missing_alt_pct": metrics.images_missing_alt_pct,
        "meta_title": metrics.meta_title,
        "meta_description": metrics.meta_description,
    }


def _metrics_response(metrics: object) -> dict[str, object]:
    from website_audit_tool.core.models import PageMetrics
    assert isinstance(metrics, PageMetrics)
    return {
        "url": metrics.url,
        "metrics": _metrics_dict(metrics),
        "analysis": None,
        "prompt_log_path": None,
    }


def start() -> None:
    import uvicorn
    uvicorn.run("website_audit_tool.web.app:app", host="0.0.0.0", port=8000, reload=False)
