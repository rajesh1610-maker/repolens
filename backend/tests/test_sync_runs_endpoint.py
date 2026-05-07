"""Smoke test for GET /api/sync/runs."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from repolens.main import app


@pytest.mark.asyncio
async def test_runs_endpoint_returns_envelope_with_limit() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/sync/runs?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and isinstance(body["items"], list)
    assert body["limit"] == 5
    assert len(body["items"]) <= 5
    if body["items"]:
        sample = body["items"][0]
        for key in ("id", "status", "started_at", "repos_synced", "duration_ms"):
            assert key in sample
        assert sample["status"] in {"running", "ok", "failed"}


@pytest.mark.asyncio
async def test_runs_endpoint_clamps_limit() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 100 should be rejected by the Query validator (max=50)
        resp = await client.get("/api/sync/runs?limit=100")
    assert resp.status_code == 422
