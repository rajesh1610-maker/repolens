from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Repo
from ..services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["repos"])


def _serialize_repo(repo: Repo) -> dict[str, Any]:
    return {
        "id": str(repo.id),
        "github_id": repo.github_id,
        "owner": repo.owner,
        "name": repo.name,
        "full_name": repo.full_name,
        "description": repo.description,
        "visibility": repo.visibility,
        "default_branch": repo.default_branch,
        "stars": repo.stars,
        "forks": repo.forks,
        "open_issues_count": repo.open_issues_count,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
        "tracked": repo.tracked,
        "synced_at": repo.synced_at.isoformat() if repo.synced_at else None,
    }


@router.get("/repos")
async def list_repos(
    include_untracked: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List repos, ordered by most-recently pushed.

    Filters applied (per D16):
        - `tracked = true` (unless `include_untracked=true` query flag — used
          by the Settings page to show the full tracking checklist)
        - `visibility = 'public'` if the current user has public_only_mode on
    """
    user = await get_current_user(db)
    public_only = bool(user and user.public_only_mode)

    stmt = select(Repo)
    if not include_untracked:
        stmt = stmt.where(Repo.tracked.is_(True))
    if public_only:
        stmt = stmt.where(Repo.visibility == "public")
    stmt = stmt.order_by(Repo.pushed_at.desc().nullslast())

    result = await db.execute(stmt)
    return [_serialize_repo(r) for r in result.scalars().all()]


async def _set_tracked(repo_id: uuid.UUID, tracked: bool, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(select(Repo).where(Repo.id == repo_id))
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    await db.execute(update(Repo).where(Repo.id == repo_id).values(tracked=tracked))
    await db.commit()
    await db.refresh(repo)
    return _serialize_repo(repo)


@router.post("/repos/{repo_id}/track")
async def track_repo(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await _set_tracked(repo_id, True, db)


@router.post("/repos/{repo_id}/untrack")
async def untrack_repo(repo_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await _set_tracked(repo_id, False, db)
