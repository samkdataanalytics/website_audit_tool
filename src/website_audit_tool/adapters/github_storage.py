"""Infrastructure adapter: persist files to a GitHub repo via the Contents API."""

from __future__ import annotations

import base64
import logging

import requests

logger = logging.getLogger(__name__)


class GitHubStorage:
    """Writes files to a GitHub repository using the GitHub Contents API."""

    def __init__(self, token: str, repo: str) -> None:
        # repo format: "owner/repo-name"
        self._repo = repo
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def save(self, path: str, content: str, message: str) -> str:
        """Create *path* in the repo with *content* and return its HTML URL.

        Raises:
            requests.HTTPError: if the GitHub API rejects the request.
        """
        encoded = base64.b64encode(content.encode()).decode()
        url = f"https://api.github.com/repos/{self._repo}/contents/{path}"
        resp = self._session.put(url, json={"message": message, "content": encoded})
        resp.raise_for_status()
        html_url: str = resp.json()["content"]["html_url"]
        logger.info("Saved to GitHub: %s", html_url)
        return html_url
