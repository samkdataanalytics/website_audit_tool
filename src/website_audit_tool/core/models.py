"""Core domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

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

class InsightSection(BaseModel):
    analysis: str = Field(
        description=(
            "Detailed analysis text. You MUST reference the exact numerical values from the "
            "extracted metrics (e.g. 'The page has 1 H1 tag' or 'Word count of 420 is below "
            "the 500–900 benchmark for a service page'). "
            "Never write advice that could apply to any page."
        )
    )
    score: int = Field(
        description=(
            "Score 0–100 for this category. "
            "0–39 = poor (critical issues present), "
            "40–69 = fair (significant room for improvement), "
            "70–89 = good (minor issues only), "
            "90–100 = excellent."
        ),
        ge=0,
        le=100,
    )


class InsightSections(BaseModel):
    seo_structure: InsightSection = Field(
        description=(
            "Analysis of heading hierarchy, meta tags, and on-page SEO signals. "
            "Must cite specific counts (e.g. H1 count, meta title presence)."
        )
    )
    messaging_clarity: InsightSection = Field(
        description=(
            "How clearly the page communicates its value proposition. "
            "Reference word count and meta description content."
        )
    )
    cta_usage: InsightSection = Field(
        description=(
            "Evaluation of CTA count, placement, and quality. "
            "Reference the exact CTA count extracted."
        )
    )
    content_depth: InsightSection = Field(
        description=(
            "Assessment of content length and comprehensiveness. "
            "Reference word count and heading structure."
        )
    )
    ux_concerns: InsightSection = Field(
        description=(
            "Structural or navigational UX issues. "
            "Reference link counts, image alt-text gaps, or heading issues."
        )
    )


class Severity(str, Enum):
    critical = "critical"
    warning = "warning"
    suggestion = "suggestion"


class Recommendation(BaseModel):
    priority: int = Field(description="Priority rank — 1 is most important.")
    severity: Severity = Field(
        description=(
            "critical = blocking issue directly harming SEO or conversions; "
            "warning = significant issue worth addressing soon; "
            "suggestion = improvement that would be beneficial but is not urgent."
        )
    )
    title: str = Field(
        description=(
            "Short, actionable title (10 words or fewer). "
            "Make it specific to this page's issue, not a generic best practice."
        )
    )
    reasoning: str = Field(
        description=(
            "The justification for this recommendation. "
            "You MUST include the exact numerical metric from the extracted data "
            "(e.g. 'Only 2 CTAs were detected' or '28.6% of images are missing alt text'). "
            "Do not write generic advice that could apply to any page."
        )
    )


class AnalysisResult(BaseModel):
    recommendations: list[Recommendation] = Field(
        description="3 to 5 recommendations ordered by priority (1 = highest). Generate these FIRST.",
    )
    insights: InsightSections


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
