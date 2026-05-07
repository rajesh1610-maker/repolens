from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Repo

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
async def list_repos(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """List tracked repos, ordered by most-recently pushed.

    Phase 1: returns every tracked repo. Phase 2 will additionally apply the
    `users.public_only_mode` display filter per D16.
    """
    stmt = (
        select(Repo)
        .where(Repo.tracked.is_(True))
        .order_by(Repo.pushed_at.desc().nullslast())
    )
    result = await db.execute(stmt)
    return [_serialize_repo(r) for r in result.scalars().all()]
