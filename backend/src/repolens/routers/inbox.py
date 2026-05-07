"""Inbox listing endpoint.

The Inbox table stores the *atemporal* priority. We compute the
time-decayed total at query time so ranking is always-fresh between
syncs:

    total_score = priority_score
                  - 5 * EXTRACT(EPOCH FROM (now() - last_activity_at)) / 86400.0

Filters:
    - kind: "all" | "pr" | "issue"
    - hide_drafts: bool
    - has_reactions: bool
    - search: substring match on title (case-insensitive)

Public-only mode (D16): if `users.public_only_mode` is true, every
private repo is hidden from the response, including in the facet counts.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import InboxItem
from ..services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["inbox"])

PRIORITY_TIME_DECAY_PER_DAY = 5.0  # mirrors services/priority.py


def _total_score_expr() -> ColumnElement[float]:
    """SQL expression for the time-decayed total score.

    Mirrors `services.priority.total_score` so Python and SQL never
    drift; the test suite pins the constant in both places.
    """
    seconds_since = func.extract(
        "EPOCH", func.now() - InboxItem.last_activity_at
    )
    days_since = seconds_since / 86400.0
    return InboxItem.priority_score - PRIORITY_TIME_DECAY_PER_DAY * days_since


def _serialize(item: InboxItem, total_score: float) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "kind": item.kind,
        "source_id": str(item.source_id),
        "repo_id": str(item.repo_id),
        "repo_full_name": item.repo_full_name,
        "repo_visibility": item.repo_visibility,
        "number": item.number,
        "title": item.title,
        "url": item.url,
        "state": item.state,
        "draft": item.draft,
        "author_login": item.author_login,
        "author_avatar_url": item.author_avatar_url,
        "labels": item.labels,
        "reactions_total": item.reactions_total,
        "comments_count": item.comments_count,
        "priority_score_static": float(item.priority_score),
        "total_score": float(total_score),
        "is_review_request": item.is_review_request,
        "is_mention": item.is_mention,
        "is_needs_response": item.is_needs_response,
        "is_stale": item.is_stale,
        "last_activity_at": item.last_activity_at.isoformat()
        if item.last_activity_at
        else None,
    }


def _apply_filters(
    stmt: Select[Any],
    *,
    kind: str,
    hide_drafts: bool,
    has_reactions: bool,
    search: str | None,
    public_only: bool,
) -> Select[Any]:
    if kind != "all":
        stmt = stmt.where(InboxItem.kind == kind)
    if hide_drafts:
        stmt = stmt.where(InboxItem.draft.is_(False))
    if has_reactions:
        stmt = stmt.where(InboxItem.reactions_total > 0)
    if search:
        stmt = stmt.where(InboxItem.title.ilike(f"%{search}%"))
    if public_only:
        stmt = stmt.where(InboxItem.repo_visibility == "public")
    return stmt


@router.get("/inbox")
async def list_inbox(
    kind: str = Query("all", pattern="^(all|pr|issue)$"),
    hide_drafts: bool = False,
    has_reactions: bool = False,
    search: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        # No user = nothing to inbox. Honest empty response.
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "facets": {"all": 0, "pr": 0, "issue": 0, "with_reactions": 0},
        }

    user_id = user.id
    public_only = bool(user.public_only_mode)
    total_expr = _total_score_expr()

    base_where = [InboxItem.user_id == user_id]
    if public_only:
        base_where.append(InboxItem.repo_visibility == "public")

    # Items + computed total score, ordered by total desc.
    items_stmt = (
        _apply_filters(
            select(InboxItem, total_expr.label("total_score")).where(and_(*base_where)),
            kind=kind,
            hide_drafts=hide_drafts,
            has_reactions=has_reactions,
            search=search,
            public_only=False,  # already in base_where
        )
        .order_by(total_expr.desc(), InboxItem.last_activity_at.desc())
        .limit(limit)
        .offset(offset)
    )

    # Total of filtered set.
    total_stmt = (
        _apply_filters(
            select(func.count()).select_from(InboxItem).where(and_(*base_where)),
            kind=kind,
            hide_drafts=hide_drafts,
            has_reactions=has_reactions,
            search=search,
            public_only=False,
        )
    )

    # Facets — counts before the kind filter (so chips remain meaningful).
    # We DO honor public_only and hide_drafts/has_reactions in facets so the
    # numbers match what the user would see when toggling kind.
    def _facet_query(facet_kind: str) -> Select[Any]:
        return _apply_filters(
            select(func.count()).select_from(InboxItem).where(and_(*base_where)),
            kind=facet_kind,
            hide_drafts=hide_drafts,
            has_reactions=has_reactions,
            search=search,
            public_only=False,  # already in base_where
        )

    all_count_stmt = _facet_query("all")
    pr_count_stmt = _facet_query("pr")
    issue_count_stmt = _facet_query("issue")
    with_reactions_stmt = (
        select(func.count())
        .select_from(InboxItem)
        .where(and_(*base_where, InboxItem.reactions_total > 0))
    )

    items_rows = (await db.execute(items_stmt)).all()
    total = (await db.execute(total_stmt)).scalar() or 0
    all_count = (await db.execute(all_count_stmt)).scalar() or 0
    pr_count = (await db.execute(pr_count_stmt)).scalar() or 0
    issue_count = (await db.execute(issue_count_stmt)).scalar() or 0
    with_reactions = (await db.execute(with_reactions_stmt)).scalar() or 0

    return {
        "items": [_serialize(item, score) for (item, score) in items_rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": {
            "all": all_count,
            "pr": pr_count,
            "issue": issue_count,
            "with_reactions": with_reactions,
        },
    }
