"""Infrastructure adapter: Anthropic LLM client."""

from __future__ import annotations

import json

import anthropic

from website_audit_tool.core.models import AnalysisResult, LLMInteraction, PageMetrics

_SYSTEM_PROMPT = (
    "You are an expert SEO and UX analyst. "
    "Analyse the given web page metrics and call the `submit_analysis` tool with your findings. "
    "Every insight and recommendation MUST cite a specific metric "
    "(e.g. exact word count, heading counts, CTA count, link counts, "
    "image alt-text percentage, meta tag presence). "
    "Be direct, specific, and non-generic — never write advice that could apply to any page."
)


class AnthropicClient:
    """Sends page metrics to the Anthropic API and returns a structured AnalysisResult."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def analyze(self, metrics: PageMetrics) -> tuple[AnalysisResult, LLMInteraction]:
        """Generate structured SEO/UX insights for the given page metrics.

        Returns:
            (AnalysisResult, LLMInteraction) — structured analysis + full audit trail.

        Raises:
            anthropic.APIError: on any Anthropic API failure.
            RuntimeError: if the LLM does not call the analysis tool.
        """
        _MAX_TOKENS = 4096

        header_str = ", ".join(
            f"{tag}: {count}" for tag, count in sorted(metrics.header_counts.items())
        )

        user_prompt = (
            f"Audit this web page. Call `submit_analysis` with your findings.\n\n"
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
            f"Each insight field must reference the specific numbers above. "
            f"Provide 3–5 recommendations ordered by priority (1 = highest)."
        )

        tools: list[anthropic.types.ToolParam] = [
            {
                "name": "submit_analysis",
                "description": (
                    "Submit the complete structured SEO/UX analysis. "
                    "Call this tool exactly once with all findings populated."
                ),
                "input_schema": AnalysisResult.model_json_schema(),
            }
        ]

        with self._client.messages.stream(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=tools,
            tool_choice={"type": "tool", "name": "submit_analysis"},
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            response = stream.get_final_message()

        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_blocks:
            raise RuntimeError("LLM did not call the submit_analysis tool.")

        analysis = AnalysisResult.model_validate(tool_blocks[0].input)

        interaction = LLMInteraction(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            raw_output=json.dumps(tool_blocks[0].input, indent=2),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return analysis, interaction
