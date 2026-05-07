"""Verify sync_contributors_for_repo rebuilds (drops stale rows) per repo.

The contract documented in services/sync.py is "rebuild semantics" —
contributors who stop committing should disappear from the local table
on the next successful sync, not linger as ghosts.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, insert, select

from repolens.db import SessionLocal
from repolens.models import Contributor, Repo, User
from repolens.services.github_client import GitHubClient
from repolens.services.sync import sync_contributors_for_repo


def _stat_entry(login: str, weekly_commits: list[int]) -> dict[str, Any]:
    """Build a /stats/contributors entry given a per-week commit list."""
    return {
        "author": {"login": login, "avatar_url": f"https://x/{login}"},
        "total": sum(weekly_commits),
        "weeks": [
            {"w": 1700000000 + i * 86400 * 7, "a": 0, "d": 0, "c": c}
            for i, c in enumerate(weekly_commits)
        ],
    }


def _resp(payload: Any) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )


@pytest.fixture
async def fixture_repo():
    """A throwaway user + repo. Yields the repo (refreshed). Cleans up via cascade."""
    user_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    base = 6_000_000_000_000

    async with SessionLocal() as db:
        await db.execute(
            insert(User).values(
                id=user_id,
                github_id=base,
                github_login=f"contrib-test-{user_id.hex[:8]}",
                public_only_mode=False,
            )
        )
        await db.execute(
            insert(Repo).values(
                id=repo_id,
                user_id=user_id,
                github_id=base + 1,
                owner="ct",
                name="r",
                full_name="ct/r",
                visibility="public",
                stars=0,
                forks=0,
                open_issues_count=0,
                tracked=True,
            )
        )
        await db.commit()
        repo = (
            await db.execute(select(Repo).where(Repo.id == repo_id))
        ).scalar_one()

    yield repo

    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_first_sync_persists_contributors(fixture_repo) -> None:
    repo = fixture_repo

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stats/contributors"):
            return _resp(
                [
                    _stat_entry("alice", [1, 2, 3]),
                    _stat_entry("bob", [4, 0, 0]),
                ]
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            count = await sync_contributors_for_repo(db, gh, repo)
        await db.commit()
        rows = list(
            (await db.execute(select(Contributor).where(Contributor.repo_id == repo.id)))
            .scalars()
            .all()
        )

    assert count == 2
    assert {r.github_login for r in rows} == {"alice", "bob"}


@pytest.mark.asyncio
async def test_second_sync_drops_contributor_who_stopped(fixture_repo) -> None:
    """Bob disappears from GitHub's response → must disappear from our DB."""
    repo = fixture_repo

    def first_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stats/contributors"):
            return _resp(
                [
                    _stat_entry("alice", [1, 2]),
                    _stat_entry("bob", [4]),
                ]
            )
        return httpx.Response(404)

    def second_handler(request: httpx.Request) -> httpx.Response:
        # Bob is gone; alice is still around.
        if request.url.path.endswith("/stats/contributors"):
            return _resp([_stat_entry("alice", [5, 6, 7])])
        return httpx.Response(404)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=httpx.MockTransport(first_handler)) as gh:
            await sync_contributors_for_repo(db, gh, repo)
        await db.commit()
        async with GitHubClient(token="t", transport=httpx.MockTransport(second_handler)) as gh:
            count = await sync_contributors_for_repo(db, gh, repo)
        await db.commit()
        rows = list(
            (await db.execute(select(Contributor).where(Contributor.repo_id == repo.id)))
            .scalars()
            .all()
        )

    assert count == 1
    assert [r.github_login for r in rows] == ["alice"]


@pytest.mark.asyncio
async def test_202_response_does_not_drop_existing_contributors(fixture_repo) -> None:
    """A 202 means 'cache warming' — we must NOT delete the prior list."""
    repo = fixture_repo

    def first_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stats/contributors"):
            return _resp([_stat_entry("alice", [1, 2])])
        return httpx.Response(404)

    def warming_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stats/contributors"):
            return httpx.Response(202)
        return httpx.Response(404)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=httpx.MockTransport(first_handler)) as gh:
            await sync_contributors_for_repo(db, gh, repo)
        await db.commit()
        async with GitHubClient(token="t", transport=httpx.MockTransport(warming_handler)) as gh:
            count = await sync_contributors_for_repo(db, gh, repo)
        await db.commit()
        rows = list(
            (await db.execute(select(Contributor).where(Contributor.repo_id == repo.id)))
            .scalars()
            .all()
        )

    assert count == 0  # 202 → returned 0 rows
    # But alice is still there (we did NOT wipe on 202)
    assert [r.github_login for r in rows] == ["alice"]
