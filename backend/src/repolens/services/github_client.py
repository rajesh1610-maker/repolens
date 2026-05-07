from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from .. import __version__


class GitHubClient:
    """Async wrapper around the GitHub REST API.

    Tracks rate-limit headers across all requests so the caller can persist
    the snapshot to `sync_runs`. ETag handling and exponential backoff land
    in Phase 4 with the PR/issue sync.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token
        self.api_calls: int = 0
        self.rate_limit_remaining: int | None = None
        self.rate_limit_limit: int | None = None
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"repolens/{__version__}",
            },
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(
        self, url: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        response = await self._client.get(url, params=params)
        self.api_calls += 1
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        limit = response.headers.get("x-ratelimit-limit")
        if limit is not None:
            self.rate_limit_limit = int(limit)
        response.raise_for_status()
        return response

    @staticmethod
    def _next_page_url(response: httpx.Response) -> str | None:
        link = response.headers.get("link")
        if not link:
            return None
        for part in link.split(","):
            section = part.strip().split(";")
            if len(section) < 2:
                continue
            url = section[0].strip().lstrip("<").rstrip(">")
            rel = section[1].strip()
            if rel == 'rel="next"':
                return url
        return None

    async def get_authenticated_user(self) -> dict[str, Any]:
        response = await self._get("/user")
        return response.json()

    async def list_user_repos(self) -> AsyncIterator[dict[str, Any]]:
        """Stream all repos visible to the PAT, following Link pagination."""
        response = await self._get(
            "/user/repos",
            params={
                "affiliation": "owner,collaborator,organization_member",
                "per_page": 100,
                "sort": "pushed",
                "direction": "desc",
            },
        )
        for repo in response.json():
            yield repo

        next_url = self._next_page_url(response)
        while next_url:
            response = await self._get(next_url)
            for repo in response.json():
                yield repo
            next_url = self._next_page_url(response)
