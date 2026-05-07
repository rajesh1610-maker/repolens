from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
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
            url: str = section[0].strip().lstrip("<").rstrip(">")
            rel = section[1].strip()
            if rel == 'rel="next"':
                return url
        return None

    async def get_authenticated_user(self) -> dict[str, Any]:
        response = await self._get("/user")
        data: dict[str, Any] = response.json()
        return data

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

    async def list_repo_pulls(
        self,
        owner: str,
        name: str,
        *,
        since: datetime | None = None,
        state: str = "all",
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream PRs for one repo, sorted updated-desc.

        GitHub's /pulls endpoint does NOT support a `since` query param
        (unlike /issues), so we sort updated-desc and stop early when we
        cross `since`. Caller passes the upstream sync floor.
        """
        response = await self._get(
            f"/repos/{owner}/{name}/pulls",
            params={
                "state": state,
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
            },
        )

        async def _walk(initial: httpx.Response) -> AsyncIterator[dict[str, Any]]:
            current = initial
            while True:
                for item in current.json():
                    if since is not None and item.get("updated_at"):
                        if datetime.fromisoformat(item["updated_at"]) < since:
                            return
                    yield item
                next_url = self._next_page_url(current)
                if not next_url:
                    return
                current = await self._get(next_url)

        async for item in _walk(response):
            yield item

    async def list_repo_issues(
        self,
        owner: str,
        name: str,
        *,
        since: datetime | None = None,
        state: str = "all",
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream issues for one repo (PRs filtered out).

        GitHub returns PRs and Issues mixed under /issues; we drop any item
        with a `pull_request` key. The endpoint supports `since` natively.
        """
        params: dict[str, Any] = {
            "state": state,
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
        }
        if since is not None:
            params["since"] = since.isoformat()

        response = await self._get(f"/repos/{owner}/{name}/issues", params=params)
        for item in response.json():
            if "pull_request" in item:
                continue
            yield item

        next_url = self._next_page_url(response)
        while next_url:
            response = await self._get(next_url)
            for item in response.json():
                if "pull_request" in item:
                    continue
                yield item
            next_url = self._next_page_url(response)

    async def list_repo_releases(
        self,
        owner: str,
        name: str,
        *,
        per_page: int = 30,
        max_pages: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream releases for a repo, newest first.

        Follows `Link: rel="next"` pagination so repos with > per_page
        releases sync completely. `max_pages` caps the walk for safety —
        a misbehaving server with infinite pagination loops can't burn
        the whole rate-limit quota. Defaults to no cap (None).

        GitHub's /releases endpoint has no `since` query; we always
        re-walk every page. With per_page=100 and a typical 10-50
        release repo, that's a single request.
        """
        url: str | None = f"/repos/{owner}/{name}/releases"
        params: dict[str, Any] | None = {"per_page": per_page}
        pages_seen = 0
        while url is not None:
            response = await self._get(url, params=params)
            for item in response.json():
                yield item
            pages_seen += 1
            if max_pages is not None and pages_seen >= max_pages:
                return
            url = self._next_page_url(response)
            params = None  # subsequent URLs already carry their own query
