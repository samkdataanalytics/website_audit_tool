"""CLI entry point for the Website Audit Tool."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from website_audit_tool.adapters.llm_client import AnthropicClient
from website_audit_tool.adapters.scraper import PageScraper, ScraperError
from website_audit_tool.use_cases.audit_page import AuditPageUseCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit",
        description="AI-powered website audit tool",
    )
    parser.add_argument("--url", required=True, help="URL of the page to audit")
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout in seconds (default: 10)",
    )
    return parser


def main() -> None:
    """Wire up dependencies and run the audit."""
    load_dotenv()

    args = _build_arg_parser().parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY is not set — LLM analysis will raise NotImplementedError"
        )

    scraper = PageScraper(timeout=args.timeout)
    llm_client = AnthropicClient(api_key=api_key)
    use_case = AuditPageUseCase(scraper=scraper, llm_client=llm_client)

    try:
        result = use_case.execute(args.url)
    except ScraperError as exc:
        logger.error("Scraping failed: %s", exc)
        sys.exit(1)
    except NotImplementedError as exc:
        logger.error("LLM analysis not yet implemented: %s", exc)
        sys.exit(1)

    m = result.metrics
    a = result.analysis

    print("\n=== Audit Metrics ===")
    print(f"URL            : {m.url}")
    print(f"Words          : {m.word_count}")
    print(f"Headers        : {m.header_counts}")
    print(f"CTAs           : {m.cta_count}")
    print(f"Internal links : {len(m.internal_links)}")
    print(f"External links : {len(m.external_links)}")
    print(f"Images         : {m.images_count} ({m.images_missing_alt_pct}% missing alt)")
    print(f"Meta title     : {m.meta_title or '(not set)'}")
    print(f"Meta desc      : {m.meta_description or '(not set)'}")

    print("\n=== Insights ===")
    ins = a.insights
    print(f"\n[SEO Structure]\n{ins.seo_structure}")
    print(f"\n[Messaging Clarity]\n{ins.messaging_clarity}")
    print(f"\n[CTA Usage]\n{ins.cta_usage}")
    print(f"\n[Content Depth]\n{ins.content_depth}")
    print(f"\n[UX Concerns]\n{ins.ux_concerns}")

    print("\n=== Recommendations ===")
    for rec in sorted(a.recommendations, key=lambda r: r.priority):
        print(f"\n{rec.priority}. {rec.title}")
        print(f"   {rec.reasoning}")

    print(f"\nLog saved to: {result.prompt_log_path}")


if __name__ == "__main__":
    main()
