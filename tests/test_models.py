"""Tests for core domain entities."""

from website_audit_tool.core.models import (
    AnalysisResult,
    AuditResult,
    InsightSection,
    InsightSections,
    PageMetrics,
    Recommendation,
    Severity,
)


def _make_metrics(**kwargs: object) -> PageMetrics:
    defaults: dict[str, object] = {
        "url": "https://example.com",
        "word_count": 100,
        "header_counts": {"h1": 1, "h2": 2},
        "cta_count": 3,
        "internal_links": ["https://example.com/about"],
        "external_links": ["https://other.com"],
    }
    defaults.update(kwargs)
    return PageMetrics(**defaults)  # type: ignore[arg-type]


def _make_analysis() -> AnalysisResult:
    return AnalysisResult(
        insights=InsightSections(
            seo_structure=InsightSection(analysis="ok", score=75),
            messaging_clarity=InsightSection(analysis="ok", score=70),
            cta_usage=InsightSection(analysis="ok", score=65),
            content_depth=InsightSection(analysis="ok", score=80),
            ux_concerns=InsightSection(analysis="ok", score=60),
        ),
        recommendations=[
            Recommendation(priority=1, severity=Severity.critical, title="Fix H1", reasoning="0 H1 tags found."),
            Recommendation(priority=2, severity=Severity.warning, title="Add meta desc", reasoning="Meta description not set."),
            Recommendation(priority=3, severity=Severity.suggestion, title="Improve CTAs", reasoning="Only 3 CTAs detected."),
        ],
    )


def test_total_links() -> None:
    metrics = _make_metrics(
        internal_links=["https://example.com/a", "https://example.com/b"],
        external_links=["https://other.com"],
    )
    assert metrics.total_links == 3


def test_total_links_empty() -> None:
    metrics = _make_metrics(internal_links=[], external_links=[])
    assert metrics.total_links == 0


def test_images_missing_alt_pct_zero_when_no_images() -> None:
    metrics = _make_metrics(images_count=0, images_missing_alt=0)
    assert metrics.images_missing_alt_pct == 0.0


def test_images_missing_alt_pct_calculated() -> None:
    metrics = _make_metrics(images_count=4, images_missing_alt=1)
    assert metrics.images_missing_alt_pct == 25.0


def test_audit_result_scraped_at_is_set() -> None:
    metrics = _make_metrics()
    result = AuditResult(
        metrics=metrics,
        analysis=_make_analysis(),
        prompt_log_path="/logs/x.json",
        scraped_data_path="/scraped/x.json",
    )
    assert result.scraped_at is not None


def test_analysis_result_recommendations_sorted() -> None:
    analysis = _make_analysis()
    priorities = [r.priority for r in analysis.recommendations]
    assert priorities == sorted(priorities)
