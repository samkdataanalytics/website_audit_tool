"""Infrastructure adapter: deterministic HTML scraper using requests + BeautifulSoup."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from website_audit_tool.core.models import PageMetrics

# Keywords that typically signal a call-to-action anchor
_CTA_KEYWORDS: frozenset[str] = frozenset(
    {
        "buy", "shop", "order", "get", "start", "sign up", "signup",
        "register", "subscribe", "download", "try", "learn more",
        "contact", "book", "schedule", "request", "join", "apply",
        "claim", "get started", "free trial",
    }
)


class ScraperError(Exception):
    """Raised when the scraper cannot fetch or parse a page."""


class PageScraper:
    """Fetches a URL and extracts deterministic page metrics."""

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "WebsiteAuditBot/0.1 (+https://github.com/samkdataanalytics/website_audit_tool)"
        )

    def scrape(self, url: str) -> PageMetrics:
        """Fetch *url* and return its PageMetrics.

        Raises:
            ScraperError: on network failure, non-2xx response, or parse failure.
        """
        html = self._fetch(url)
        return self._parse(url, html)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> str:
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.text
        except requests.Timeout as exc:
            raise ScraperError(f"Request timed out after {self._timeout}s: {url}") from exc
        except requests.ConnectionError as exc:
            raise ScraperError(f"Connection error for {url}") from exc
        except requests.HTTPError as exc:
            raise ScraperError(
                f"HTTP {exc.response.status_code} for {url}"
            ) from exc

    def _parse(self, url: str, html: str) -> PageMetrics:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            raise ScraperError(f"Failed to parse HTML for {url}") from exc

        base_domain = urlparse(url).netloc

        images_count, images_missing_alt = self._count_images(soup)
        meta_title, meta_description = self._extract_meta(soup)

        return PageMetrics(
            url=url,
            word_count=self._count_words(soup),
            header_counts=self._count_headers(soup),
            cta_count=self._count_ctas(soup),
            internal_links=self._collect_links(soup, url, base_domain, internal=True),
            external_links=self._collect_links(soup, url, base_domain, internal=False),
            images_count=images_count,
            images_missing_alt=images_missing_alt,
            meta_title=meta_title,
            meta_description=meta_description,
        )

    @staticmethod
    def _count_words(soup: BeautifulSoup) -> int:
        body = soup.find("body")
        if body is None:
            return 0
        text = body.get_text(separator=" ")
        return len(re.findall(r"\b\w+\b", text))

    @staticmethod
    def _count_headers(soup: BeautifulSoup) -> dict[str, int]:
        counts: dict[str, int] = {}
        for level in ("h1", "h2", "h3", "h4", "h5", "h6"):
            n = len(soup.find_all(level))
            if n:
                counts[level] = n
        return counts

    @staticmethod
    def _count_ctas(soup: BeautifulSoup) -> int:
        count = 0
        for tag in soup.find_all("a"):
            text = tag.get_text(separator=" ").strip().lower()
            if any(kw in text for kw in _CTA_KEYWORDS):
                count += 1
        return count

    @staticmethod
    def _collect_links(
        soup: BeautifulSoup,
        base_url: str,
        base_domain: str,
        *,
        internal: bool,
    ) -> list[str]:
        links: list[str] = []
        for tag in soup.find_all("a", href=True):
            href: str = str(tag["href"] or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            domain = urlparse(absolute).netloc
            is_internal = domain == base_domain or domain == ""
            if is_internal == internal:
                links.append(absolute)
        return links

    @staticmethod
    def _count_images(soup: BeautifulSoup) -> tuple[int, int]:
        """Return (total_images, images_missing_alt)."""
        imgs = soup.find_all("img")
        missing = sum(
            1 for img in imgs if not str(img.get("alt") or "").strip()
        )
        return len(imgs), missing

    @staticmethod
    def _extract_meta(soup: BeautifulSoup) -> tuple[str, str]:
        """Return (meta_title, meta_description)."""
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        desc_tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "description"})
        description = str(desc_tag.get("content") or "").strip() if desc_tag else ""

        return title, description
