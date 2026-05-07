"""Releases page endpoints.

GET /api/releases             — list of repos with their last release +
                                count of merged PRs since.
GET /api/releases/{owner}/{name}/draft  — generated draft notes for a
                                          tag (or the next semver bump).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
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

    Performance: this endpoint is N+1-free. We fetch repos, latest
    releases (one query, grouped by repo_id), and merged-PR counts
    (one query, grouped by repo_id with a per-repo published_at gate)
    — three queries total, regardless of repo count.
    """
    user = await get_current_user(db)
    if user is None:
        return {"items": []}

    public_only = bool(user.public_only_mode)

    # 1. Repos this user owns + tracks (+ honor public_only_mode)
    repo_stmt = select(Repo).where(Repo.user_id == user.id, Repo.tracked.is_(True))
    if public_only:
        repo_stmt = repo_stmt.where(Repo.visibility == "public")
    repos = list((await db.execute(repo_stmt)).scalars().all())
    if not repos:
        return {"items": []}

    repo_ids = [r.id for r in repos]

    # 2. Latest non-draft release per repo, with the corresponding tag.
    # Two-step: first get max(published_at) per repo, then JOIN to find the
    # tag at that timestamp. Postgres `DISTINCT ON` is the natural form.
    latest_rel_stmt = (
        select(Release.repo_id, Release.tag_name, Release.published_at)
        .distinct(Release.repo_id)
        .where(Release.repo_id.in_(repo_ids), Release.draft.is_(False))
        .order_by(Release.repo_id, Release.published_at.desc().nullslast())
    )
    latest_release_by_repo: dict[Any, tuple[str, datetime | None]] = {
        row.repo_id: (row.tag_name, row.published_at)
        for row in (await db.execute(latest_rel_stmt)).all()
    }

    # 3. Merged-PR count per repo, gated by each repo's latest published_at.
    # We do one query that returns (repo_id, count) where the count is for
    # PRs merged AFTER each repo's latest release. The CASE expression
    # encodes "pre-release" gate per row; missing released = no gate.
    pr_count_stmt = (
        select(PullRequest.repo_id, func.count().label("c"))
        .where(
            PullRequest.repo_id.in_(repo_ids),
            PullRequest.state == "merged",
            PullRequest.merged_at.is_not(None),  # NULL guard: ignore corrupt rows
        )
        .group_by(PullRequest.repo_id)
    )
    # Apply the per-repo gate via OR of (no release yet) OR (merged_at > that release)
    gates = []
    for rid, (_, latest_at) in latest_release_by_repo.items():
        if latest_at is not None:
            gates.append(
                and_(PullRequest.repo_id == rid, PullRequest.merged_at > latest_at)
            )
    repos_with_release = set(latest_release_by_repo.keys())
    repos_without_release = [rid for rid in repo_ids if rid not in repos_with_release]
    if repos_without_release:
        gates.append(PullRequest.repo_id.in_(repos_without_release))
    if gates:
        pr_count_stmt = pr_count_stmt.where(or_(*gates))
    else:
        # No repos at all to gate — short-circuit to zero counts
        pr_count_stmt = pr_count_stmt.where(PullRequest.repo_id == None)  # noqa: E711

    merged_counts: dict[Any, int] = {
        row.repo_id: row.c for row in (await db.execute(pr_count_stmt)).all()
    }

    items: list[dict[str, Any]] = []
    for repo in repos:
        tag, published_at = latest_release_by_repo.get(repo.id, (None, None))
        items.append(
            {
                "repo_id": str(repo.id),
                "owner": repo.owner,
                "name": repo.name,
                "full_name": repo.full_name,
                "visibility": repo.visibility,
                "latest_tag": tag,
                "latest_published_at": published_at.isoformat() if published_at else None,
                "unreleased_pr_count": merged_counts.get(repo.id, 0),
            }
        )

    items.sort(key=lambda r: int(r["unreleased_pr_count"]), reverse=True)
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

    # Pull merged PRs since the latest release. Defensive: a PR with
    # state='merged' but NULL merged_at is corrupt sync data — skip it
    # rather than silently include or exclude based on the time gate.
    pr_stmt = (
        select(PullRequest)
        .where(
            PullRequest.repo_id == repo.id,
            PullRequest.state == "merged",
            PullRequest.merged_at.is_not(None),
        )
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
