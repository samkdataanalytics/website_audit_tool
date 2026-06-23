"""Use case: orchestrates scraping → LLM analysis → log persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from website_audit_tool.adapters.llm_client import AnthropicClient
from website_audit_tool.adapters.scraper import PageScraper
from website_audit_tool.core.models import (
    AnalysisResult,
    AuditResult,
    LLMInteraction,
    PageMetrics,
)

logger = logging.getLogger(__name__)

_LOGS_DIR = Path(__file__).parents[3] / "logs"


class AuditPageUseCase:
    """Scrape a URL, analyse it with an LLM, and persist the prompt log."""

    def __init__(self, scraper: PageScraper, llm_client: AnthropicClient) -> None:
        self._scraper = scraper
        self._llm_client = llm_client

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

        log_path = self._save_prompt_log(url, metrics, analysis, interaction)

        return AuditResult(
            metrics=metrics,
            analysis=analysis,
            prompt_log_path=str(log_path),
            llm_interaction=interaction,
        )

    # ------------------------------------------------------------------

    def _save_prompt_log(
        self,
        url: str,
        metrics: PageMetrics,
        analysis: AnalysisResult,
        interaction: LLMInteraction,
    ) -> Path:
        _LOGS_DIR.mkdir(exist_ok=True)
        domain = urlparse(url).netloc.replace(".", "_")
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        log_file = _LOGS_DIR / f"{timestamp}_{domain}.json"

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
                "thinking": interaction.thinking,
                "raw_output": interaction.raw_output,
            },
        }
        log_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Prompt log saved to %s", log_file)
        return log_file
