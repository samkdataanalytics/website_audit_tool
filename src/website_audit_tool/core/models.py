"""Core domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# LLM audit trail
# ---------------------------------------------------------------------------

@dataclass
class LLMInteraction:
    """Full record of one LLM call — prompts in, raw JSON output out."""

    model: str
    max_tokens: int
    system_prompt: str
    user_prompt: str
    raw_output: str          # JSON-serialised AnalysisResult
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Structured analysis schema (used as Anthropic tool input_schema)
# ---------------------------------------------------------------------------

class InsightSections(BaseModel):
    seo_structure: str = Field(
        description=(
            "Analysis of heading hierarchy, meta tags, and on-page SEO signals. "
            "Must cite specific counts (e.g. H1 count, meta title presence)."
        )
    )
    messaging_clarity: str = Field(
        description=(
            "How clearly the page communicates its value proposition. "
            "Reference word count and meta description content."
        )
    )
    cta_usage: str = Field(
        description=(
            "Evaluation of CTA count, placement, and quality. "
            "Reference the exact CTA count extracted."
        )
    )
    content_depth: str = Field(
        description=(
            "Assessment of content length and comprehensiveness. "
            "Reference word count and heading structure."
        )
    )
    ux_concerns: str = Field(
        description=(
            "Structural or navigational UX issues. "
            "Reference link counts, image alt-text gaps, or heading issues."
        )
    )


class Recommendation(BaseModel):
    priority: int = Field(description="Priority rank — 1 is most important.")
    title: str = Field(description="Short, actionable title (10 words or fewer).")
    reasoning: str = Field(
        description="Specific reasoning tied to at least one extracted metric. Cite the number."
    )


class AnalysisResult(BaseModel):
    insights: InsightSections
    recommendations: list[Recommendation] = Field(
        description="3 to 5 recommendations ordered by priority (1 first).",
        min_length=3,
        max_length=5,
    )


# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------

@dataclass
class PageMetrics:
    """Deterministic metrics scraped from a single web page."""

    url: str
    word_count: int
    header_counts: dict[str, int]  # {"h1": 1, "h2": 3, ...}
    cta_count: int
    internal_links: list[str]
    external_links: list[str]
    images_count: int = 0
    images_missing_alt: int = 0
    meta_title: str = ""
    meta_description: str = ""

    @property
    def total_links(self) -> int:
        return len(self.internal_links) + len(self.external_links)

    @property
    def images_missing_alt_pct(self) -> float:
        if self.images_count == 0:
            return 0.0
        return round(self.images_missing_alt / self.images_count * 100, 1)


@dataclass
class AuditResult:
    """The complete output of one audit run."""

    metrics: PageMetrics
    analysis: AnalysisResult
    prompt_log_path: str
    scraped_data_path: str
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    llm_interaction: LLMInteraction | None = None
