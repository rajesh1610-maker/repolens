"""Tests for the async GitHub client.

Uses httpx.MockTransport so no network calls are made and no real PAT is
required. Each test seeds the canned responses it needs.
"""

from __future__ import annotations

import json
from datetime import UTC

import httpx
import pytest

from repolens.services.github_client import GitHubClient


def _make_response(payload: object, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


@pytest.mark.asyncio
async def test_get_authenticated_user_sends_bearer_and_parses_response() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return _make_response(
            {"id": 42, "login": "octocat", "email": None, "avatar_url": "https://x"},
            headers={"x-ratelimit-remaining": "4998", "x-ratelimit-limit": "5000"},
        )

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="testtoken", transport=transport) as gh:
        user = await gh.get_authenticated_user()

    assert user["login"] == "octocat"
    assert user["id"] == 42
    req = captured["req"]
    assert req.headers["authorization"] == "Bearer testtoken"
    assert req.headers["accept"] == "application/vnd.github+json"
    assert req.headers["x-github-api-version"] == "2022-11-28"
    assert req.url.path == "/user"
    # rate limit captured from response headers
    assert gh.rate_limit_remaining == 4998
    assert gh.rate_limit_limit == 5000
    assert gh.api_calls == 1


@pytest.mark.asyncio
async def test_list_user_repos_yields_each_repo_and_follows_pagination() -> None:
    page_1 = [{"id": 1, "full_name": "a/one"}, {"id": 2, "full_name": "a/two"}]
    page_2 = [{"id": 3, "full_name": "a/three"}]
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            assert request.url.path == "/user/repos"
            assert request.url.params.get("affiliation") == "owner,collaborator,organization_member"
            assert request.url.params.get("per_page") == "100"
            return _make_response(
                page_1,
                headers={
                    "link": '<https://api.github.com/user/repos?page=2>; rel="next"',
                    "x-ratelimit-remaining": "4997",
                },
            )
        return _make_response(page_2, headers={"x-ratelimit-remaining": "4996"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="t", transport=transport) as gh:
        collected = [r async for r in gh.list_user_repos()]

    assert [r["full_name"] for r in collected] == ["a/one", "a/two", "a/three"]
    assert gh.api_calls == 2
    assert gh.rate_limit_remaining == 4996


@pytest.mark.asyncio
async def test_raise_for_status_on_4xx() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="bad", transport=transport) as gh:
        with pytest.raises(httpx.HTTPStatusError):
            await gh.get_authenticated_user()
    # api_calls still incremented even though the call failed
    assert gh.api_calls == 1


@pytest.mark.asyncio
async def test_next_page_url_returns_none_without_link_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _make_response([{"id": 1, "full_name": "a/x"}])

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="t", transport=transport) as gh:
        repos = [r async for r in gh.list_user_repos()]
    assert len(repos) == 1


@pytest.mark.asyncio
async def test_list_repo_pulls_walks_pages_and_stops_at_since() -> None:
    """`since` short-circuits the iterator the moment we cross it."""
    page1 = [
        {"id": 11, "number": 5, "updated_at": "2026-05-01T00:00:00+00:00"},
        {"id": 10, "number": 4, "updated_at": "2026-04-15T00:00:00+00:00"},
        {"id": 9, "number": 3, "updated_at": "2026-04-10T00:00:00+00:00"},
    ]
    page2 = [
        {"id": 8, "number": 2, "updated_at": "2026-03-01T00:00:00+00:00"},
    ]
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if "page=2" in str(request.url):
            return _make_response(page2)
        return _make_response(
            page1,
            headers={"link": '<https://api.github.com/x?page=2>; rel="next"'},
        )

    transport = httpx.MockTransport(handler)
    from datetime import datetime

    since = datetime(2026, 4, 14, tzinfo=UTC)
    async with GitHubClient(token="t", transport=transport) as gh:
        prs = [
            p
            async for p in gh.list_repo_pulls("a", "b", since=since)
        ]

    # Should yield 11, 10 (both newer than since), then stop on 9 (older).
    assert [p["number"] for p in prs] == [5, 4]
    # Crucially: page2 should NEVER be fetched — we stopped early.
    assert all("page=2" not in str(r.url) for r in captured)


@pytest.mark.asyncio
async def test_list_repo_issues_filters_pull_requests_and_passes_since() -> None:
    """The `pull_request` key marks an item as a PR; `since` must be on the wire."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _make_response(
            [
                {"id": 100, "number": 1, "title": "real issue"},
                {
                    "id": 101,
                    "number": 2,
                    "title": "PR masquerading",
                    "pull_request": {"url": "..."},
                },
                {"id": 102, "number": 3, "title": "another real issue"},
            ]
        )

    transport = httpx.MockTransport(handler)
    from datetime import datetime

    since = datetime(2026, 5, 1, tzinfo=UTC)
    async with GitHubClient(token="t", transport=transport) as gh:
        issues = [i async for i in gh.list_repo_issues("a", "b", since=since)]

    assert [i["number"] for i in issues] == [1, 3]
    # Confirm `since` was sent on the wire as ISO-8601
    assert captured[0].url.params.get("since") == since.isoformat()
