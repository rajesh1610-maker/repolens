"""End-to-end tests for the /api/settings router.

Strategy: snapshot the dev user's mutable fields (pat_encrypted,
public_only_mode) before each test, mutate freely, restore on
teardown. GitHub's /user endpoint is mocked at the GitHubClient layer
via monkeypatch so the tests never hit the network and never
exercise a real PAT.

These tests would have caught:
  - The Phase 2 RETURNING(User) bug (`has_pat: false` after save).
  - A regression in the single-user 409 path.
  - PAT validation routes (whitespace, bad-token).
  - public_only_mode persistence.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from repolens.db import SessionLocal
from repolens.main import app
from repolens.models import User
from repolens.services import github_client as gh_client_module


@pytest.fixture
async def user_state_restored():
    """Snapshot dev user state, restore on teardown.

    Yields the user_id (or None if no user exists yet — tests can skip).
    """
    async with SessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            yield None
            return
        snapshot = {
            "github_id": user.github_id,
            "github_login": user.github_login,
            "pat_encrypted": user.pat_encrypted,
            "anthropic_key_encrypted": user.anthropic_key_encrypted,
            "public_only_mode": user.public_only_mode,
        }
        user_id = user.id

    yield {"id": user_id, **snapshot}

    async with SessionLocal() as db:
        # Restore — the user row may have been deleted; recreate or update.
        existing = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if existing is None:
            from sqlalchemy import insert as sql_insert

            await db.execute(
                sql_insert(User).values(id=user_id, **snapshot)
            )
        else:
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(
                    github_id=snapshot["github_id"],
                    github_login=snapshot["github_login"],
                    pat_encrypted=snapshot["pat_encrypted"],
                    anthropic_key_encrypted=snapshot["anthropic_key_encrypted"],
                    public_only_mode=snapshot["public_only_mode"],
                )
            )
        await db.commit()


def _patch_github_user_lookup(monkeypatch, *, login: str, github_id: int) -> dict[str, Any]:
    """Make GitHubClient.get_authenticated_user return our fake user."""
    captured: dict[str, Any] = {"calls": 0, "tokens": []}
    fake_user = {
        "id": github_id,
        "login": login,
        "email": None,
        "avatar_url": "https://avatars.example/x",
    }

    async def fake_get_user(self):
        captured["calls"] += 1
        captured["tokens"].append(self.token)
        return fake_user

    monkeypatch.setattr(
        gh_client_module.GitHubClient, "get_authenticated_user", fake_get_user
    )
    return captured


# ---------------- GET /api/settings ----------------


@pytest.mark.asyncio
async def test_get_settings_returns_overview_with_all_keys(user_state_restored) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    for top in ("user", "repos", "scheduler"):
        assert top in body
    for k in ("configured", "github_login", "has_pat", "public_only_mode"):
        assert k in body["user"]
    for k in ("total", "tracked", "public", "private"):
        assert k in body["repos"]
    for k in ("enabled", "interval_minutes", "watchdog_minutes"):
        assert k in body["scheduler"]


# ---------------- POST /api/settings/pat ----------------


@pytest.mark.asyncio
async def test_save_pat_persists_encrypted_and_returns_has_pat_true(
    user_state_restored, monkeypatch
) -> None:
    """The Phase 2 regression: the response must accurately reflect has_pat=true."""
    if user_state_restored is None:
        pytest.skip("no dev user")
    captured = _patch_github_user_lookup(
        monkeypatch,
        login=user_state_restored["github_login"],
        github_id=user_state_restored["github_id"],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/settings/pat",
            json={"pat": "ghp_validlookingtoken_xxxxx"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["user"]["has_pat"] is True
    assert captured["calls"] == 1
    assert captured["tokens"][0] == "ghp_validlookingtoken_xxxxx"


@pytest.mark.asyncio
async def test_save_pat_strips_whitespace_before_calling_github(
    user_state_restored, monkeypatch
) -> None:
    if user_state_restored is None:
        pytest.skip("no dev user")
    captured = _patch_github_user_lookup(
        monkeypatch,
        login=user_state_restored["github_login"],
        github_id=user_state_restored["github_id"],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/settings/pat",
            json={"pat": "  ghp_paddedtoken_xxxxx  \n"},
        )

    assert resp.status_code == 200
    # The token reaching GitHubClient must be stripped
    assert captured["tokens"][0] == "ghp_paddedtoken_xxxxx"


@pytest.mark.asyncio
async def test_save_pat_returns_400_when_github_rejects(
    user_state_restored, monkeypatch
) -> None:
    if user_state_restored is None:
        pytest.skip("no dev user")

    async def fake_get_user_raises(self):
        import httpx

        raise httpx.HTTPStatusError(
            "Bad credentials",
            request=httpx.Request("GET", "https://api.github.com/user"),
            response=httpx.Response(401),
        )

    monkeypatch.setattr(
        gh_client_module.GitHubClient,
        "get_authenticated_user",
        fake_get_user_raises,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/settings/pat", json={"pat": "ghp_obviouslybadtoken_xx"}
        )
    assert resp.status_code == 400
    assert "authenticate" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_save_pat_409_for_different_github_user(
    user_state_restored, monkeypatch
) -> None:
    """Single-user enforcement: a PAT for a different GitHub account must 409."""
    if user_state_restored is None:
        pytest.skip("no dev user")
    # Mock /user to return a *different* github_id than the existing user.
    different_id = user_state_restored["github_id"] + 100_000
    _patch_github_user_lookup(
        monkeypatch, login="someone_else", github_id=different_id
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/settings/pat", json={"pat": "ghp_othertoken_xxxxxx"}
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "single-user" in detail
    assert "someone_else" in detail


@pytest.mark.asyncio
async def test_save_pat_rejects_short_token() -> None:
    """Pydantic min_length=20 enforces basic sanity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/settings/pat", json={"pat": "tiny"})
    assert resp.status_code == 422


# ---------------- DELETE /api/settings/pat ----------------


@pytest.mark.asyncio
async def test_delete_pat_clears_encrypted_field(
    user_state_restored, monkeypatch
) -> None:
    if user_state_restored is None:
        pytest.skip("no dev user")
    _patch_github_user_lookup(
        monkeypatch,
        login=user_state_restored["github_login"],
        github_id=user_state_restored["github_id"],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Save first to ensure there's something to delete
        await client.post(
            "/api/settings/pat", json={"pat": "ghp_savedtoken_xxxxxxx"}
        )
        resp = await client.delete("/api/settings/pat")

    assert resp.status_code == 200
    assert resp.json()["user"]["has_pat"] is False

    # Confirm at the DB level
    async with SessionLocal() as db:
        u = (await db.execute(select(User).limit(1))).scalar_one()
    assert u.pat_encrypted is None


# ---------------- PATCH public_only_mode ----------------


@pytest.mark.asyncio
async def test_patch_public_only_mode_persists(user_state_restored) -> None:
    if user_state_restored is None:
        pytest.skip("no dev user")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            "/api/settings", json={"public_only_mode": True}
        )
    assert resp.status_code == 200
    assert resp.json()["user"]["public_only_mode"] is True

    # Fresh GET reflects it
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp2 = await client.get("/api/settings")
    assert resp2.json()["user"]["public_only_mode"] is True
