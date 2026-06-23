"""Infrastructure adapter: Anthropic LLM client."""

from __future__ import annotations

import copy
import json
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, Field

from website_audit_tool.core.models import (
    AnalysisResult,
    InsightSection,
    InsightSections,
    LLMInteraction,
    PageMetrics,
    Recommendation,
)

_T = TypeVar("_T", bound=BaseModel)


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve all $ref occurrences so the schema has no cross-references.

    Haiku omits fields that appear after deeply nested $ref chains.
    Inlining gives the model a flat, self-contained structure to follow.
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                resolved = copy.deepcopy(defs.get(ref_name, {}))
                for k, v in obj.items():
                    if k != "$ref":
                        resolved[k] = v
                return resolve(resolved)
            return {k: resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [resolve(item) for item in obj]
        return obj

    return resolve(schema)


class _RecsResult(BaseModel):
    """Intermediate container for the recommendations-only tool call."""
    recommendations: list[Recommendation] = Field(
        description="3 to 5 recommendations ordered by priority (1 = highest)."
    )


class _FlatInsights(BaseModel):
    """Flat insight schema — no nested objects — so Haiku generates all 10 fields reliably."""
    seo_structure: str = Field(
        description=(
            "SEO structure analysis. You MUST cite the exact H-tag counts and meta tag presence "
            "(e.g. '1 H1 tag detected — correct; 0 H2 tags is below standard'). "
            "Never write generic advice."
        )
    )
    seo_structure_score: int = Field(description="SEO structure score 0–100.", ge=0, le=100)
    messaging_clarity: str = Field(
        description=(
            "Messaging clarity analysis. You MUST cite the exact word count and meta description "
            "(e.g. 'With 420 words and a missing meta description...'). Never write generic advice."
        )
    )
    messaging_clarity_score: int = Field(description="Messaging clarity score 0–100.", ge=0, le=100)
    cta_usage: str = Field(
        description=(
            "CTA usage analysis. You MUST cite the exact CTA count extracted "
            "(e.g. '3 CTAs detected — within the 1–3 standard'). Never write generic advice."
        )
    )
    cta_usage_score: int = Field(description="CTA usage score 0–100.", ge=0, le=100)
    content_depth: str = Field(
        description=(
            "Content depth analysis. You MUST cite the exact word count and heading structure "
            "(e.g. '1,204 words exceeds the 500–900 benchmark for a service page'). "
            "Never write generic advice."
        )
    )
    content_depth_score: int = Field(description="Content depth score 0–100.", ge=0, le=100)
    ux_concerns: str = Field(
        description=(
            "UX concerns. You MUST cite link counts, image alt-text percentage, or heading issues "
            "(e.g. '2 of 14 images (14.3%) are missing alt text — an accessibility and SEO issue'). "
            "Never write generic advice."
        )
    )
    ux_concerns_score: int = Field(description="UX concerns score 0–100.", ge=0, le=100)


_SYSTEM_PROMPT = (
    "You are an expert SEO and UX analyst for a web agency. "
    "Analyse the given web page metrics and call the requested tool with your findings. "
    "Every insight and recommendation MUST cite a specific metric "
    "(e.g. exact word count, heading counts, CTA count, link counts, "
    "image alt-text percentage, meta tag presence). "
    "Be direct, specific, and non-generic — never write advice that could apply to any page.\n\n"
    "INDUSTRY BENCHMARKS — use these to contextualise every finding:\n"
    "- Word count: landing pages 300–600 words; service/product pages 500–900 words; "
    "blog posts 1,200–2,000 words\n"
    "- H1 tags: exactly 1 is optimal; 0 = critical SEO gap; more than 1 dilutes page focus\n"
    "- CTAs: 1–3 per page is standard; 0 = conversion gap; more than 5 may signal lack of focus\n"
    "- Internal links: 5–15 is healthy; fewer than 3 may indicate weak site architecture\n"
    "- Image alt text: 100% coverage is the target; any gap is an accessibility and SEO issue\n"
    "- Meta description: 120–160 characters is optimal; missing means Google auto-generates it\n"
    "- Meta title: 50–60 characters is optimal; missing or over 60 chars is an SEO issue\n\n"
    "EXAMPLES — good insight vs bad insight:\n"
    "  Good: 'The page has 0 H1 tags — a critical SEO issue and below the standard of exactly 1. "
    "Without an H1, search engines have no primary signal for the page topic. "
    "Add a single descriptive H1 above the fold immediately.'\n"
    "  Bad:  'You should improve your headings for better SEO.' "
    "(no metric cited, applies to any page — never write this)\n\n"
    "  Good: 'With 1 CTA detected, the page sits at the low end of the 1–3 standard for a "
    "service page. A single CTA limits conversion paths; add a secondary CTA lower on the page.'\n"
    "  Bad:  'Add more calls to action to improve conversions.' "
    "(no metric cited, generic — never write this)"
)


class AnthropicClient:
    """Sends page metrics to the Anthropic API and returns a structured AnalysisResult."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, metrics: PageMetrics) -> tuple[AnalysisResult, LLMInteraction]:
        """Generate structured SEO/UX insights for the given page metrics.

        Uses two focused tool calls so each schema stays small enough for
        Haiku to complete without truncating either field.

        Returns:
            (AnalysisResult, LLMInteraction) — structured analysis + full audit trail.

        Raises:
            anthropic.APIError: on any Anthropic API failure.
            RuntimeError: if the LLM does not call a required tool.
        """
        user_prompt = self._build_user_prompt(metrics)

        recs_result, recs_usage = self._call_tool(
            user_prompt=user_prompt,
            tool_name="submit_recommendations",
            tool_description=(
                "Submit 3–5 prioritized recommendations for this page. "
                "Each must cite the exact metric number in its reasoning."
            ),
            schema=_inline_refs(_RecsResult.model_json_schema()),
            model_class=_RecsResult,
        )

        flat_insights, ins_usage = self._call_tool(
            user_prompt=user_prompt,
            tool_name="submit_insights",
            tool_description=(
                "Submit SEO/UX analysis with per-category scores. "
                "Every text field must cite the exact metric numbers from the audit data."
            ),
            schema=_FlatInsights.model_json_schema(),
            model_class=_FlatInsights,
        )

        insights_result = InsightSections(
            seo_structure=InsightSection(analysis=flat_insights.seo_structure, score=flat_insights.seo_structure_score),
            messaging_clarity=InsightSection(analysis=flat_insights.messaging_clarity, score=flat_insights.messaging_clarity_score),
            cta_usage=InsightSection(analysis=flat_insights.cta_usage, score=flat_insights.cta_usage_score),
            content_depth=InsightSection(analysis=flat_insights.content_depth, score=flat_insights.content_depth_score),
            ux_concerns=InsightSection(analysis=flat_insights.ux_concerns, score=flat_insights.ux_concerns_score),
        )

        analysis = AnalysisResult(
            recommendations=recs_result.recommendations,
            insights=insights_result,
        )

        interaction = LLMInteraction(
            model=self._model,
            max_tokens=8192,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            raw_output=json.dumps(analysis.model_dump(), indent=2),
            input_tokens=recs_usage.input_tokens + ins_usage.input_tokens,
            output_tokens=recs_usage.output_tokens + ins_usage.output_tokens,
        )

        return analysis, interaction

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_prompt(self, metrics: PageMetrics) -> str:
        header_str = ", ".join(
            f"{tag}: {count}" for tag, count in sorted(metrics.header_counts.items())
        )
        return (
            f"Audit this web page and call the requested tool with your findings.\n\n"
            f"**URL:** {metrics.url}\n\n"
            f"**Extracted Metrics:**\n"
            f"- Word count: {metrics.word_count}\n"
            f"- Heading structure: {header_str or 'none detected'}\n"
            f"- Call-to-action elements: {metrics.cta_count}\n"
            f"- Internal links: {len(metrics.internal_links)}\n"
            f"- External links: {len(metrics.external_links)}\n"
            f"- Images: {metrics.images_count} total, "
            f"{metrics.images_missing_alt} missing alt text "
            f"({metrics.images_missing_alt_pct:.1f}%)\n"
            f"- Meta title: {metrics.meta_title or 'not set'}\n"
            f"- Meta description: {metrics.meta_description or 'not set'}\n\n"
            f"Every field must reference the specific numbers above."
        )

    def _call_tool(
        self,
        user_prompt: str,
        tool_name: str,
        tool_description: str,
        schema: dict[str, Any],
        model_class: type[_T],
    ) -> tuple[_T, anthropic.types.Usage]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_prompt}],
        )

        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            raise RuntimeError(f"LLM did not call the {tool_name} tool.")

        return model_class.model_validate(tool_blocks[0].input), response.usage
