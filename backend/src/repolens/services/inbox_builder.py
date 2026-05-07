"""Rebuild the `inbox_items` derived table from the source-of-truth tables.

Called at the end of every successful sync. The rebuild is a single
transaction:

    BEGIN;
      DELETE FROM inbox_items WHERE user_id = :user_id;
      INSERT INTO inbox_items SELECT ... FROM pull_requests JOIN repos ...;
      INSERT INTO inbox_items SELECT ... FROM issues JOIN repos ...;
    COMMIT;

Atomicity matters: a failed insert leaves the previous Inbox intact.
Filters: only OPEN items, only TRACKED repos. The public-only display
filter is applied at query time (Settings → Visibility), not here —
that way the toggle is instant and reversible without re-syncing.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InboxItem, Issue, PullRequest, Repo
from .priority import static_priority


def _row_to_item_dict(
    *,
    kind: str,
    source_id: uuid.UUID,
    repo: Repo,
    user_id: uuid.UUID,
    number: int,
    title: str,
    state: str,
    draft: bool,
    author_login: str | None,
    author_avatar_url: str | None,
    labels: list[str],
    reactions_total: int,
    comments_count: int,
    last_activity_at,
) -> dict[str, Any]:
    """Build the dict that becomes one row in `inbox_items`.

    Keeps every field explicit — the call site is the single place where
    we map from source-table rows to inbox rows, so verbosity is OK.
    """
    url_segment = "pull" if kind == "pr" else "issues"
    score = static_priority(
        {
            "kind": kind,
            "draft": draft,
            "reactions_total": reactions_total,
            "labels": labels,
        }
    )
    return {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "repo_id": repo.id,
        "kind": kind,
        "source_id": source_id,
        "repo_full_name": repo.full_name,
        "repo_visibility": repo.visibility,
        "number": number,
        "title": title,
        "url": f"https://github.com/{repo.full_name}/{url_segment}/{number}",
        "state": state,
        "draft": draft,
        "author_login": author_login,
        "author_avatar_url": author_avatar_url,
        "labels": labels or [],
        "reactions_total": reactions_total,
        "comments_count": comments_count,
        "priority_score": score,
        # Phase 5: these are placeholders. Phase 6+ wires them from
        # comments / review-request / mention syncing.
        "is_review_request": False,
        "is_mention": False,
        "is_needs_response": False,
        "is_stale": False,
        "last_activity_at": last_activity_at,
    }


async def rebuild_inbox_items(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Replace the user's inbox in one transaction. Returns rows inserted.

    The caller is expected to commit. We use `flush` here so the rebuild
    composes inside a wider transaction (e.g., end-of-sync).
    """
    # 1. Drop existing inbox for this user.
    await db.execute(delete(InboxItem).where(InboxItem.user_id == user_id))

    # 2. PRs — join to repos to keep this user-scoped + tracked-only.
    pr_stmt = (
        select(PullRequest, Repo)
        .join(Repo, PullRequest.repo_id == Repo.id)
        .where(
            PullRequest.state == "open",
            Repo.user_id == user_id,
            Repo.tracked.is_(True),
        )
    )
    rows: list[dict[str, Any]] = []
    for pr, repo in (await db.execute(pr_stmt)).all():
        rows.append(
            _row_to_item_dict(
                kind="pr",
                source_id=pr.id,
                repo=repo,
                user_id=user_id,
                number=pr.number,
                title=pr.title,
                state=pr.state,
                draft=pr.draft,
                author_login=pr.author_login,
                author_avatar_url=pr.author_avatar_url,
                labels=list(pr.labels or []),
                reactions_total=0,  # PRs don't carry reactions in our schema
                comments_count=0,  # likewise — Phase 6 fills this
                last_activity_at=pr.updated_at,
            )
        )

    # 3. Issues — same join, no PR-specific fields.
    issue_stmt = (
        select(Issue, Repo)
        .join(Repo, Issue.repo_id == Repo.id)
        .where(
            Issue.state == "open",
            Repo.user_id == user_id,
            Repo.tracked.is_(True),
        )
    )
    for issue, repo in (await db.execute(issue_stmt)).all():
        rows.append(
            _row_to_item_dict(
                kind="issue",
                source_id=issue.id,
                repo=repo,
                user_id=user_id,
                number=issue.number,
                title=issue.title,
                state=issue.state,
                draft=False,
                author_login=issue.author_login,
                author_avatar_url=issue.author_avatar_url,
                labels=list(issue.labels or []),
                reactions_total=issue.reactions_total,
                comments_count=issue.comments_count,
                last_activity_at=issue.updated_at,
            )
        )

    if rows:
        await db.execute(InboxItem.__table__.insert(), rows)
    await db.flush()
    return len(rows)
