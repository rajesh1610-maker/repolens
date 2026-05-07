"""Releases page endpoints.

GET /api/releases             — list of repos with their last release +
                                count of merged PRs since.
GET /api/releases/{owner}/{name}/draft  — generated draft notes for a
                                          tag (or the next semver bump).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import PullRequest, Release, Repo
from ..services.auth import get_current_user
from ..services.release_notes import generate_notes

router = APIRouter(prefix="/api", tags=["releases"])


def _serialize_release(rel: Release) -> dict[str, Any]:
    return {
        "id": str(rel.id),
        "github_id": rel.github_id,
        "tag_name": rel.tag_name,
        "name": rel.name,
        "published_at": rel.published_at.isoformat() if rel.published_at else None,
        "draft": rel.draft,
        "prerelease": rel.prerelease,
    }


def _suggest_next_tag(latest: str | None) -> str:
    """Trivial next-tag suggestion: bump patch on a `vMAJOR.MINOR.PATCH` tag.

    If we can't parse, default to "vNEXT". The user edits before
    publishing — we just want to give them a starting string that's
    not blank.
    """
    if not latest:
        return "v0.1.0"
    s = latest.lstrip("v")
    parts = s.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return f"{latest}-next"
    major, minor, patch = (int(p) for p in parts)
    prefix = "v" if latest.startswith("v") else ""
    return f"{prefix}{major}.{minor}.{patch + 1}"


@router.get("/releases")
async def list_releases_overview(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per repo: latest release + count of merged PRs since.

    Used by the Releases page sidebar to show repos in "ready to ship"
    order (most unreleased commits first).
    """
    user = await get_current_user(db)
    if user is None:
        return {"items": []}

    public_only = bool(user.public_only_mode)

    # Repos this user owns + tracks (+ honor public_only_mode)
    repo_stmt = select(Repo).where(
        Repo.user_id == user.id, Repo.tracked.is_(True)
    )
    if public_only:
        repo_stmt = repo_stmt.where(Repo.visibility == "public")
    repos = list((await db.execute(repo_stmt)).scalars().all())

    # Latest non-draft release per repo
    latest_release_subq = (
        select(
            Release.repo_id,
            func.max(Release.published_at).label("latest_published"),
        )
        .where(Release.draft.is_(False))
        .group_by(Release.repo_id)
        .subquery()
    )
    latest_releases = {
        row.repo_id: row.latest_published
        for row in (await db.execute(select(latest_release_subq))).all()
    }

    # For each repo, count merged PRs since the latest release
    items: list[dict[str, Any]] = []
    for repo in repos:
        latest_at = latest_releases.get(repo.id)
        merged_count_q = select(func.count()).select_from(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.state == "merged",
        )
        if latest_at is not None:
            merged_count_q = merged_count_q.where(PullRequest.merged_at > latest_at)
        merged_count = (await db.execute(merged_count_q)).scalar() or 0

        # Get the latest release's tag for display
        tag_q = (
            select(Release.tag_name, Release.published_at)
            .where(Release.repo_id == repo.id, Release.draft.is_(False))
            .order_by(Release.published_at.desc())
            .limit(1)
        )
        tag_row = (await db.execute(tag_q)).first()
        items.append(
            {
                "repo_id": str(repo.id),
                "owner": repo.owner,
                "name": repo.name,
                "full_name": repo.full_name,
                "visibility": repo.visibility,
                "latest_tag": tag_row.tag_name if tag_row else None,
                "latest_published_at": tag_row.published_at.isoformat()
                if tag_row and tag_row.published_at
                else None,
                "unreleased_pr_count": merged_count,
            }
        )

    items.sort(key=lambda r: r["unreleased_pr_count"], reverse=True)
    return {"items": items}


@router.get("/releases/{owner}/{name}/draft")
async def get_release_draft(
    owner: str,
    name: str,
    next_tag: str | None = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Draft release notes for a repo's unreleased PRs.

    `next_tag` is what the user wants to call the next release; if
    omitted, we suggest one by bumping the patch on the latest tag.
    """
    user = await get_current_user(db)
    if user is None:
        raise HTTPException(status_code=400, detail="No user configured.")
    public_only = bool(user.public_only_mode)

    # Resolve the repo (404 + public_only respect)
    repo_stmt = select(Repo).where(
        Repo.owner == owner, Repo.name == name, Repo.user_id == user.id
    )
    repo = (await db.execute(repo_stmt)).scalar_one_or_none()
    if repo is None or (public_only and repo.visibility != "public"):
        raise HTTPException(
            status_code=404,
            detail=f"Repo {owner}/{name} not found or hidden by public-only mode.",
        )

    # Find latest release (any state) for the comparison anchor
    last_q = (
        select(Release)
        .where(Release.repo_id == repo.id, Release.draft.is_(False))
        .order_by(Release.published_at.desc().nullslast())
        .limit(1)
    )
    latest = (await db.execute(last_q)).scalar_one_or_none()

    # Pull merged PRs since
    pr_stmt = (
        select(PullRequest)
        .where(PullRequest.repo_id == repo.id, PullRequest.state == "merged")
        .order_by(PullRequest.merged_at.desc())
    )
    if latest is not None and latest.published_at is not None:
        pr_stmt = pr_stmt.where(PullRequest.merged_at > latest.published_at)
    prs = list((await db.execute(pr_stmt)).scalars().all())

    pulls_payload = [
        {
            "number": p.number,
            "title": p.title,
            "labels": list(p.labels or []),
            "author_login": p.author_login,
            "merged_at": p.merged_at.isoformat() if p.merged_at else None,
        }
        for p in prs
    ]

    suggested = next_tag or _suggest_next_tag(latest.tag_name if latest else None)
    notes_md = generate_notes(
        repo_full_name=repo.full_name,
        next_tag=suggested,
        previous_tag=latest.tag_name if latest else None,
        pulls=pulls_payload,
    )

    return {
        "repo_full_name": repo.full_name,
        "next_tag": suggested,
        "previous_tag": latest.tag_name if latest else None,
        "previous_published_at": latest.published_at.isoformat()
        if latest and latest.published_at
        else None,
        "pull_count": len(prs),
        "pulls": pulls_payload,
        "notes_markdown": notes_md,
    }
