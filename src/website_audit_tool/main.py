"""CLI entry point for the Website Audit Tool."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from website_audit_tool.adapters.github_storage import GitHubStorage
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

    gh_token = os.getenv("GITHUB_TOKEN", "")
    gh_repo = os.getenv("GITHUB_REPO", "")
    github = GitHubStorage(token=gh_token, repo=gh_repo) if gh_token and gh_repo else None

    scraper = PageScraper(timeout=args.timeout)
    llm_client = AnthropicClient(api_key=api_key)
    use_case = AuditPageUseCase(scraper=scraper, llm_client=llm_client, github_storage=github)

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
    print(f"\n[SEO Structure] Score: {ins.seo_structure.score}/100\n{ins.seo_structure.analysis}")
    print(f"\n[Messaging Clarity] Score: {ins.messaging_clarity.score}/100\n{ins.messaging_clarity.analysis}")
    print(f"\n[CTA Usage] Score: {ins.cta_usage.score}/100\n{ins.cta_usage.analysis}")
    print(f"\n[Content Depth] Score: {ins.content_depth.score}/100\n{ins.content_depth.analysis}")
    print(f"\n[UX Concerns] Score: {ins.ux_concerns.score}/100\n{ins.ux_concerns.analysis}")

    print("\n=== Recommendations ===")
    for rec in sorted(a.recommendations, key=lambda r: r.priority):
        print(f"\n{rec.priority}. [{rec.severity.value.upper()}] {rec.title}")
        print(f"   {rec.reasoning}")

    print(f"\nScraped data : {result.scraped_data_path}")
    print(f"Prompt log   : {result.prompt_log_path}")


if __name__ == "__main__":
    main()
