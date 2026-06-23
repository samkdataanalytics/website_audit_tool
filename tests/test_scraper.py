"""Tests for the PageScraper adapter."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from website_audit_tool.adapters.scraper import PageScraper, ScraperError

_SAMPLE_HTML = """
<html>
<body>
  <h1>Hello World</h1>
  <h2>Section One</h2>
  <h2>Section Two</h2>
  <p>Buy now and get started with our free trial today.</p>
  <a href="/about">About</a>
  <a href="/contact">Contact us</a>
  <a href="https://external.com/page">External link</a>
  <a href="https://another.com">Another external</a>
</body>
</html>
"""

_BASE_URL = "https://example.com"


def _mock_response(html: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


@patch("website_audit_tool.adapters.scraper.requests.Session.get")
def test_scrape_returns_metrics(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response(_SAMPLE_HTML)
    scraper = PageScraper()
    metrics = scraper.scrape(_BASE_URL)

    assert metrics.url == _BASE_URL
    assert metrics.word_count > 0
    assert metrics.header_counts.get("h1") == 1
    assert metrics.header_counts.get("h2") == 2
    assert metrics.cta_count >= 1
    assert len(metrics.internal_links) == 2
    assert len(metrics.external_links) == 2


@patch("website_audit_tool.adapters.scraper.requests.Session.get")
def test_scrape_raises_on_timeout(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.Timeout()
    scraper = PageScraper()
    with pytest.raises(ScraperError, match="timed out"):
        scraper.scrape(_BASE_URL)


@patch("website_audit_tool.adapters.scraper.requests.Session.get")
def test_scrape_raises_on_http_error(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response("", status=404)
    scraper = PageScraper()
    with pytest.raises(ScraperError, match="HTTP 404"):
        scraper.scrape(_BASE_URL)
