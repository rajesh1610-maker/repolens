"""Tests for the async GitHub client.

Uses httpx.MockTransport so no network calls are made and no real PAT is
required. Each test seeds the canned responses it needs.
"""

from __future__ import annotations

import json

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
