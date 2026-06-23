"""Use case: orchestrates scraping → LLM analysis → log persistence."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from website_audit_tool.adapters.github_storage import GitHubStorage
from website_audit_tool.adapters.llm_client import AnthropicClient
from website_audit_tool.adapters.scraper import PageScraper
from website_audit_tool.core.models import (
    AnalysisResult,
    AuditResult,
    LLMInteraction,
    PageMetrics,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parents[3]
_DATA_ROOT = _PROJECT_ROOT if os.access(_PROJECT_ROOT, os.W_OK) else Path(tempfile.gettempdir())
_LOGS_DIR = _DATA_ROOT / "logs"
_SCRAPED_DIR = _DATA_ROOT / "scraped"


class AuditPageUseCase:
    """Scrape a URL, analyse it with an LLM, and persist the prompt log."""

    def __init__(
        self,
        scraper: PageScraper,
        llm_client: AnthropicClient,
        github_storage: GitHubStorage | None = None,
    ) -> None:
        self._scraper = scraper
        self._llm_client = llm_client
        self._github = github_storage

    def execute(self, url: str) -> AuditResult:
        """Run a full audit for *url*.

        Returns:
            AuditResult with scraped metrics, structured analysis, and log path.

        Raises:
            ScraperError: if the page cannot be fetched or parsed.
            anthropic.APIError: on LLM failure.
        """
        logger.info("Scraping %s", url)
        metrics = self._scraper.scrape(url)

        logger.info("Analysing metrics with LLM")
        analysis, interaction = self._llm_client.analyze(metrics)

        scraped_path = self._save_scraped_data(url, metrics)
        log_path = self._save_prompt_log(url, metrics, analysis, interaction)

        return AuditResult(
            metrics=metrics,
            analysis=analysis,
            scraped_data_path=scraped_path,
            prompt_log_path=log_path,
            llm_interaction=interaction,
        )

    # ------------------------------------------------------------------

    def _save_scraped_data(self, url: str, metrics: PageMetrics) -> str:
        domain = urlparse(url).netloc.replace(".", "_")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}_{domain}.json"

        payload = dataclasses.asdict(metrics)
        payload["scraped_at"] = timestamp
        content = json.dumps(payload, indent=2)

        if self._github:
            try:
                return self._github.save(
                    path=f"scraped/{filename}",
                    content=content,
                    message=f"scraped: {url} at {timestamp}",
                )
            except Exception as exc:
                logger.error("GitHub storage failed for scraped data: %s", exc)

        path = _SCRAPED_DIR / filename
        _SCRAPED_DIR.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Scraped data saved to %s", path)
        return str(path)

    def _save_prompt_log(
        self,
        url: str,
        metrics: PageMetrics,
        analysis: AnalysisResult,
        interaction: LLMInteraction,
    ) -> str:
        domain = urlparse(url).netloc.replace(".", "_")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}_{domain}.json"

        payload = {
            "url": url,
            "scraped_at": timestamp,
            "metrics": {
                "word_count": metrics.word_count,
                "header_counts": metrics.header_counts,
                "cta_count": metrics.cta_count,
                "internal_links_count": len(metrics.internal_links),
                "external_links_count": len(metrics.external_links),
                "images_count": metrics.images_count,
                "images_missing_alt": metrics.images_missing_alt,
                "images_missing_alt_pct": metrics.images_missing_alt_pct,
                "meta_title": metrics.meta_title,
                "meta_description": metrics.meta_description,
            },
            "analysis": {
                "insights": analysis.insights.model_dump(),
                "recommendations": [r.model_dump() for r in analysis.recommendations],
            },
            "llm": {
                "model": interaction.model,
                "input_tokens": interaction.input_tokens,
                "output_tokens": interaction.output_tokens,
                "system_prompt": interaction.system_prompt,
                "user_prompt": interaction.user_prompt,
                "raw_output": interaction.raw_output,
            },
        }
        content = json.dumps(payload, indent=2)

        if self._github:
            try:
                return self._github.save(
                    path=f"logs/{filename}",
                    content=content,
                    message=f"audit log: {url} at {timestamp}",
                )
            except Exception as exc:
                logger.error("GitHub storage failed for prompt log: %s", exc)

        path = _LOGS_DIR / filename
        _LOGS_DIR.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Prompt log saved to %s", path)
        return str(path)
