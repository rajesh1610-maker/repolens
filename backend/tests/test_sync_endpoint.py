"""Smoke tests for /api/sync/last and /api/sync.

POST /api/sync hits real GitHub, so we don't exercise it here — that's the
manual demo path. We verify GET /api/sync/last responds correctly even when
no runs exist, and the structure when one does.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from repolens.main import app


@pytest.mark.asyncio
async def test_sync_last_returns_object_with_last_run_key() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/sync/last")
    assert response.status_code == 200
    body = response.json()
    assert "last_run" in body
    # last_run is None (no runs) or an object with these required fields
    if body["last_run"] is not None:
        for key in ("id", "status", "started_at", "repos_synced", "api_calls"):
            assert key in body["last_run"]
        assert body["last_run"]["status"] in {"running", "ok", "failed"}
