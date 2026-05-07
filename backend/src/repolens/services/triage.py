"""Triage column queries: Stale, Hot, Stuck.

Each is a deterministic SQL filter over `issues` (open only, in tracked
repos owned by the current user, honoring public_only_mode). The
columns are MUTUALLY DISCOVERABLE — an issue can appear in more than one
(e.g., a 70-day-old issue with 5 reactions is both Stale and Hot). The
frontend renders all three independently; the user sees that overlap as
information, not duplication.

Thresholds match the original spec/03 plan:
    Stale  — open >60 days, no recent activity
    Hot    — high reactions
    Stuck  — `needs-info` / `awaiting-response` / `blocked` label,
             AND >14 days since last activity
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Issue, Repo, User

STALE_DAYS = 60
STUCK_DAYS = 14
STUCK_LABELS: frozenset[str] = frozenset(
    {"needs-info", "needs info", "awaiting-response", "awaiting response", "blocked"}
)


def _serialize(issue: Issue, repo: Repo) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "repo_id": str(repo.id),
        "repo_full_name": repo.full_name,
        "repo_visibility": repo.visibility,
        "number": issue.number,
        "title": issue.title,
        "url": f"https://github.com/{repo.full_name}/issues/{issue.number}",
        "author_login": issue.author_login,
        "author_avatar_url": issue.author_avatar_url,
        "labels": issue.labels,
        "comments_count": issue.comments_count,
        "reactions_total": issue.reactions_total,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
    }


def _user_scope(user: User) -> list:
    """Common predicates: open + tracked + owned by user + public_only-respecting."""
    where = [
        Issue.state == "open",
        Repo.user_id == user.id,
        Repo.tracked.is_(True),
    ]
    if user.public_only_mode:
        where.append(Repo.visibility == "public")
    return where


def _base_select() -> Select:
    return select(Issue, Repo).join(Repo, Issue.repo_id == Repo.id)


async def stale_issues(
    db: AsyncSession, user: User, *, limit: int = 50
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=STALE_DAYS)
    stmt = (
        _base_select()
        .where(and_(*_user_scope(user), Issue.updated_at < cutoff))
        .order_by(Issue.updated_at.asc())  # oldest first
        .limit(limit)
    )
    return [_serialize(i, r) for (i, r) in (await db.execute(stmt)).all()]


async def hot_issues(
    db: AsyncSession, user: User, *, limit: int = 50
) -> list[dict[str, Any]]:
    stmt = (
        _base_select()
        .where(and_(*_user_scope(user), Issue.reactions_total > 0))
        .order_by(Issue.reactions_total.desc(), Issue.updated_at.desc())
        .limit(limit)
    )
    return [_serialize(i, r) for (i, r) in (await db.execute(stmt)).all()]


async def stuck_issues(
    db: AsyncSession, user: User, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Open issues with a 'needs info / blocked' label that haven't moved in 14d.

    JSONB label match is case-insensitive in Python — we fetch a bit
    wider in SQL (label-array is non-empty) and filter precisely in Python.
    For v0.1 with realistic repo sizes this is fine; later we'll add a
    GIN index + jsonb_array_elements_text() for native containment.
    """
    cutoff = datetime.now(UTC) - timedelta(days=STUCK_DAYS)
    stmt = (
        _base_select()
        .where(
            and_(
                *_user_scope(user),
                Issue.updated_at < cutoff,
                Issue.labels != [],
            )
        )
        .order_by(Issue.updated_at.asc())
        .limit(limit * 2)  # over-fetch for client-side filter
    )
    rows = []
    for issue, repo in (await db.execute(stmt)).all():
        for label in issue.labels or []:
            if isinstance(label, str) and label.strip().lower() in STUCK_LABELS:
                rows.append(_serialize(issue, repo))
                break
        if len(rows) >= limit:
            break
    return rows
