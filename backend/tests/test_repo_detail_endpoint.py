"""Smoke tests for repo detail / pulls / issues endpoints.

We hit the dev DB (which has 5 real repos from rajesh1610-maker). These
tests don't write data; they verify the response contract on existing rows.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from repolens.main import app


@pytest.mark.asyncio
async def test_get_repo_detail_returns_404_for_unknown() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/repos/no-such-owner/no-such-repo")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_repo_detail_shape_for_existing_repo() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First get the list to find a real repo
        list_resp = await client.get("/api/repos")
        assert list_resp.status_code == 200
        repos = list_resp.json()
        if not repos:
            pytest.skip("no repos synced — skipping detail shape check")
        first = repos[0]
        resp = await client.get(f"/api/repos/{first['owner']}/{first['name']}")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "id",
        "full_name",
        "visibility",
        "open_pulls_count",
        "open_issues_real_count",
        "merged_pulls_30d",
    ):
        assert key in body


@pytest.mark.asyncio
async def test_pulls_endpoint_returns_paginated_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/repos")
        repos = list_resp.json()
        if not repos:
            pytest.skip("no repos synced")
        first = repos[0]
        resp = await client.get(f"/api/repos/{first['owner']}/{first['name']}/pulls?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and isinstance(body["items"], list)
    assert "total" in body and isinstance(body["total"], int)
    assert body["limit"] == 10
    assert body["offset"] == 0


@pytest.mark.asyncio
async def test_pulls_state_filter_validation() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/repos")
        repos = list_resp.json()
        if not repos:
            pytest.skip("no repos synced")
        first = repos[0]
        resp = await client.get(
            f"/api/repos/{first['owner']}/{first['name']}/pulls?state=invalid"
        )
    # Pydantic regex validation rejects the bad value
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_issues_endpoint_returns_paginated_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_resp = await client.get("/api/repos")
        repos = list_resp.json()
        if not repos:
            pytest.skip("no repos synced")
        first = repos[0]
        resp = await client.get(f"/api/repos/{first['owner']}/{first['name']}/issues?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["limit"] == 5
