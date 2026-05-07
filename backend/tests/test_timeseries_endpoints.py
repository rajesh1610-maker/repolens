"""Smoke tests for /api/repos/{owner}/{name}/traffic and /contributors.

Hits dev DB. Verifies envelope shape, filling logic on missing days,
404 path. Real numbers are exercised in the broader manual demo.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from repolens.main import app


@pytest.mark.asyncio
async def test_traffic_returns_full_window_with_zeros_for_missing_days() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        resp = await client.get(f"/api/repos/{owner}/{name}/traffic?days=14")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 14
    assert len(body["series"]) == 14
    assert all("day" in p and "views" in p for p in body["series"])
    assert "totals" in body


@pytest.mark.asyncio
async def test_traffic_404_for_unknown_repo() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/repos/no-such/repo/traffic")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_traffic_validates_days_param() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        # Below the floor of 7
        too_short = await client.get(f"/api/repos/{owner}/{name}/traffic?days=3")
        # Above the cap of 90
        too_long = await client.get(f"/api/repos/{owner}/{name}/traffic?days=365")
    assert too_short.status_code == 422
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_contributors_returns_envelope() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        resp = await client.get(f"/api/repos/{owner}/{name}/contributors")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_repos_response_includes_stars_30d_array() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/repos")
    body = resp.json()
    if not body:
        pytest.skip("no repos synced")
    sample = body[0]
    assert "stars_30d" in sample
    assert isinstance(sample["stars_30d"], list)
    # Always exactly 30 elements (the "missing days carry forward" rule)
    assert len(sample["stars_30d"]) == 30


@pytest.mark.asyncio
async def test_traffic_default_window_is_28_days() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        resp = await client.get(f"/api/repos/{owner}/{name}/traffic")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 28
    assert len(body["series"]) == 28


@pytest.mark.asyncio
async def test_traffic_accepts_min_and_max_window() -> None:
    """days=7 (floor) and days=90 (ceiling) are accepted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        r7 = await client.get(f"/api/repos/{owner}/{name}/traffic?days=7")
        r90 = await client.get(f"/api/repos/{owner}/{name}/traffic?days=90")
    assert r7.status_code == 200
    assert r90.status_code == 200
    assert len(r7.json()["series"]) == 7
    assert len(r90.json()["series"]) == 90


@pytest.mark.asyncio
async def test_contributors_envelope_includes_limit_and_db_total() -> None:
    """`total` reflects DB count, not items[] length — frontend can paginate."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        repos = (await client.get("/api/repos")).json()
        if not repos:
            pytest.skip("no repos synced")
        owner, name = repos[0]["owner"], repos[0]["name"]
        resp = await client.get(
            f"/api/repos/{owner}/{name}/contributors?limit=1"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 1
    assert len(body["items"]) <= 1
    assert body["total"] >= len(body["items"])
