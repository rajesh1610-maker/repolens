from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Issue, PullRequest, Repo
from ..services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["repos"])


def _serialize_repo(
    repo: Repo,
    *,
    open_pulls_count: int = 0,
    open_issues_real_count: int = 0,
    merged_pulls_30d: int = 0,
) -> dict[str, Any]:
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
        "open_pulls_count": open_pulls_count,
        "open_issues_real_count": open_issues_real_count,
        "merged_pulls_30d": merged_pulls_30d,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
        "tracked": repo.tracked,
        "synced_at": repo.synced_at.isoformat() if repo.synced_at else None,
    }


def _serialize_pull(pr: PullRequest) -> dict[str, Any]:
    return {
        "id": str(pr.id),
        "number": pr.number,
        "title": pr.title,
        "state": pr.state,
        "draft": pr.draft,
        "author_login": pr.author_login,
        "author_avatar_url": pr.author_avatar_url,
        "labels": pr.labels,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
        "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
    }


def _serialize_issue(issue: Issue) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "number": issue.number,
        "title": issue.title,
        "state": issue.state,
        "author_login": issue.author_login,
        "author_avatar_url": issue.author_avatar_url,
        "labels": issue.labels,
        "comments_count": issue.comments_count,
        "reactions_total": issue.reactions_total,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
    }


async def _aggregate_counts_by_repo(
    db: AsyncSession,
) -> dict[uuid.UUID, dict[str, int]]:
    """Return per-repo aggregate counts in one round trip.

    Keyed by repo_id; values: open_pulls_count, open_issues_real_count,
    merged_pulls_30d.
    """
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    pulls_q = select(
        PullRequest.repo_id,
        func.count().filter(PullRequest.state == "open").label("open_pulls"),
        func.count()
        .filter(and_(PullRequest.state == "merged", PullRequest.merged_at >= thirty_days_ago))
        .label("merged_30d"),
    ).group_by(PullRequest.repo_id)

    issues_q = select(
        Issue.repo_id,
        func.count().filter(Issue.state == "open").label("open_issues"),
    ).group_by(Issue.repo_id)

    pulls_rows = (await db.execute(pulls_q)).all()
    issues_rows = (await db.execute(issues_q)).all()

    counts: dict[uuid.UUID, dict[str, int]] = {}
    for row in pulls_rows:
        counts.setdefault(row.repo_id, {})["open_pulls_count"] = row.open_pulls or 0
        counts.setdefault(row.repo_id, {})["merged_pulls_30d"] = row.merged_30d or 0
    for row in issues_rows:
        counts.setdefault(row.repo_id, {})["open_issues_real_count"] = row.open_issues or 0
    return counts


def _is_hidden_by_public_only(repo: Repo, public_only: bool) -> bool:
    return public_only and repo.visibility != "public"


@router.get("/repos")
async def list_repos(
    include_untracked: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    user = await get_current_user(db)
    public_only = bool(user and user.public_only_mode)

    stmt = select(Repo)
    if not include_untracked:
        stmt = stmt.where(Repo.tracked.is_(True))
    if public_only:
        stmt = stmt.where(Repo.visibility == "public")
    stmt = stmt.order_by(Repo.pushed_at.desc().nullslast())

    repos = list((await db.execute(stmt)).scalars().all())
    counts = await _aggregate_counts_by_repo(db)

    return [
        _serialize_repo(
            r,
            open_pulls_count=counts.get(r.id, {}).get("open_pulls_count", 0),
            open_issues_real_count=counts.get(r.id, {}).get("open_issues_real_count", 0),
            merged_pulls_30d=counts.get(r.id, {}).get("merged_pulls_30d", 0),
        )
        for r in repos
    ]


@router.get("/repos/{owner}/{name}")
async def get_repo_detail(
    owner: str, name: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await get_current_user(db)
    public_only = bool(user and user.public_only_mode)

    stmt = select(Repo).where(Repo.owner == owner, Repo.name == name)
    repo = (await db.execute(stmt)).scalar_one_or_none()
    if repo is None or _is_hidden_by_public_only(repo, public_only):
        raise HTTPException(
            status_code=404, detail=f"Repo {owner}/{name} not found or hidden by public-only mode."
        )

    counts = (await _aggregate_counts_by_repo(db)).get(repo.id, {})
    return _serialize_repo(
        repo,
        open_pulls_count=counts.get("open_pulls_count", 0),
        open_issues_real_count=counts.get("open_issues_real_count", 0),
        merged_pulls_30d=counts.get("merged_pulls_30d", 0),
    )


async def _resolve_repo_or_404(
    owner: str, name: str, db: AsyncSession
) -> Repo:
    user = await get_current_user(db)
    public_only = bool(user and user.public_only_mode)
    stmt = select(Repo).where(Repo.owner == owner, Repo.name == name)
    repo = (await db.execute(stmt)).scalar_one_or_none()
    if repo is None or _is_hidden_by_public_only(repo, public_only):
        raise HTTPException(
            status_code=404, detail=f"Repo {owner}/{name} not found or hidden by public-only mode."
        )
    return repo


@router.get("/repos/{owner}/{name}/pulls")
async def list_repo_pulls(
    owner: str,
    name: str,
    state: str = Query("all", pattern="^(all|open|closed|merged)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = await _resolve_repo_or_404(owner, name, db)
    stmt = select(PullRequest).where(PullRequest.repo_id == repo.id)
    if state != "all":
        stmt = stmt.where(PullRequest.state == state)
    stmt = stmt.order_by(PullRequest.updated_at.desc()).offset(offset).limit(limit)

    total_q = select(func.count()).select_from(PullRequest).where(PullRequest.repo_id == repo.id)
    if state != "all":
        total_q = total_q.where(PullRequest.state == state)

    rows = list((await db.execute(stmt)).scalars().all())
    total = (await db.execute(total_q)).scalar() or 0
    return {
        "items": [_serialize_pull(p) for p in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/repos/{owner}/{name}/issues")
async def list_repo_issues(
    owner: str,
    name: str,
    state: str = Query("all", pattern="^(all|open|closed)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = await _resolve_repo_or_404(owner, name, db)
    stmt = select(Issue).where(Issue.repo_id == repo.id)
    if state != "all":
        stmt = stmt.where(Issue.state == state)
    stmt = stmt.order_by(Issue.updated_at.desc()).offset(offset).limit(limit)

    total_q = select(func.count()).select_from(Issue).where(Issue.repo_id == repo.id)
    if state != "all":
        total_q = total_q.where(Issue.state == state)

    rows = list((await db.execute(stmt)).scalars().all())
    total = (await db.execute(total_q)).scalar() or 0
    return {
        "items": [_serialize_issue(i) for i in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


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
