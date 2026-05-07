from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Repo, SyncRun, User
from .github_client import GitHubClient


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


async def _upsert_user(db: AsyncSession, gh_user: dict[str, Any]) -> User:
    stmt = (
        insert(User)
        .values(
            id=uuid.uuid4(),
            github_id=gh_user["id"],
            github_login=gh_user["login"],
            email=gh_user.get("email"),
            avatar_url=gh_user.get("avatar_url"),
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_={
                "github_login": gh_user["login"],
                "email": gh_user.get("email"),
                "avatar_url": gh_user.get("avatar_url"),
            },
        )
        .returning(User)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def _upsert_repo(
    db: AsyncSession, user_id: uuid.UUID, gh_repo: dict[str, Any], now: datetime
) -> None:
    pushed_at = _parse_iso(gh_repo.get("pushed_at"))
    payload = {
        "owner": gh_repo["owner"]["login"],
        "name": gh_repo["name"],
        "full_name": gh_repo["full_name"],
        "description": gh_repo.get("description"),
        "visibility": gh_repo.get("visibility", "public"),
        "default_branch": gh_repo.get("default_branch"),
        "stars": gh_repo.get("stargazers_count", 0),
        "forks": gh_repo.get("forks_count", 0),
        "open_issues_count": gh_repo.get("open_issues_count", 0),
        "pushed_at": pushed_at,
        "synced_at": now,
    }
    stmt = (
        insert(Repo)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            github_id=gh_repo["id"],
            **payload,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=payload,
        )
    )
    await db.execute(stmt)


async def sync_repos(db: AsyncSession, github: GitHubClient) -> SyncRun:
    """Pull the user's repos from GitHub and upsert into the local DB.

    Records a SyncRun row in all cases (success or failure) for audit.
    Returns the persisted SyncRun.
    """
    sync_run = SyncRun(status="running")
    db.add(sync_run)
    await db.commit()
    await db.refresh(sync_run)
    sync_run_id = sync_run.id

    try:
        gh_user = await github.get_authenticated_user()
        user = await _upsert_user(db, gh_user)
        await db.commit()

        now = datetime.now(UTC)
        repos_synced = 0
        async for gh_repo in github.list_user_repos():
            await _upsert_repo(db, user.id, gh_repo, now)
            repos_synced += 1
        await db.commit()

        await db.execute(
            update(SyncRun)
            .where(SyncRun.id == sync_run_id)
            .values(
                status="ok",
                repos_synced=repos_synced,
                api_calls=github.api_calls,
                rate_limit_remaining=github.rate_limit_remaining,
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await db.execute(
            update(SyncRun)
            .where(SyncRun.id == sync_run_id)
            .values(
                status="failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                api_calls=github.api_calls,
                rate_limit_remaining=github.rate_limit_remaining,
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()
        raise

    await db.refresh(sync_run)
    return sync_run
