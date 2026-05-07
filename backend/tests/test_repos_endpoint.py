"""Smoke test for GET /api/repos.

Hits the real DB the dev environment is pointed at. The endpoint must
return 200 and a JSON list (possibly empty if no sync has run).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from repolens.main import app


@pytest.mark.asyncio
async def test_list_repos_returns_json_list() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/repos")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    # If a sync has been run before this test, rows may exist; just sanity-check shape
    if body:
        sample = body[0]
        for key in ("id", "github_id", "full_name", "stars", "visibility", "tracked"):
            assert key in sample
