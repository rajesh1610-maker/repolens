"""Integration tests for the inbox builder.

Each test creates its own user + repos + items with unique IDs and
cleans up via `ON DELETE CASCADE` from the user. Tests don't touch
the dev user's real repos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, insert, select

from repolens.db import SessionLocal
from repolens.models import InboxItem, Issue, PullRequest, Repo, User
from repolens.services.inbox_builder import rebuild_inbox_items


@pytest.fixture
async def test_user_id() -> uuid.UUID:
    """A throwaway user with two repos (one tracked, one untracked).

    Yields the user_id; teardown CASCADEs everything.
    """
    user_id = uuid.uuid4()
    tracked_repo_id = uuid.uuid4()
    untracked_repo_id = uuid.uuid4()
    # github_ids must be unique per repo across the table — use a high
    # base to avoid collisions with real synced repos.
    base = 9_000_000_000_000

    async with SessionLocal() as db:
        await db.execute(
            insert(User).values(
                id=user_id,
                github_id=base,
                github_login=f"test-{user_id.hex[:8]}",
                public_only_mode=False,
            )
        )
        await db.execute(
            insert(Repo).values(
                id=tracked_repo_id,
                user_id=user_id,
                github_id=base + 1,
                owner="test-owner",
                name="tracked-repo",
                full_name="test-owner/tracked-repo",
                visibility="public",
                stars=0,
                forks=0,
                open_issues_count=0,
                tracked=True,
            )
        )
        await db.execute(
            insert(Repo).values(
                id=untracked_repo_id,
                user_id=user_id,
                github_id=base + 2,
                owner="test-owner",
                name="untracked-repo",
                full_name="test-owner/untracked-repo",
                visibility="public",
                stars=0,
                forks=0,
                open_issues_count=0,
                tracked=False,
            )
        )
        await db.commit()

    yield user_id, tracked_repo_id, untracked_repo_id

    async with SessionLocal() as db:
        # CASCADE drops repos, PRs, issues, inbox_items
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _pr(repo_id: uuid.UUID, *, number: int, state: str = "open", **rest: Any) -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid.uuid4(),
        "repo_id": repo_id,
        "github_id": uuid.uuid4().int & ((1 << 63) - 1),
        "number": number,
        "title": f"PR {number}",
        "state": state,
        "draft": False,
        "author_login": "alice",
        "author_avatar_url": None,
        "labels": [],
        "created_at": now - timedelta(days=2),
        "updated_at": now - timedelta(days=1),
        **rest,
    }


def _issue(
    repo_id: uuid.UUID, *, number: int, state: str = "open", **rest: Any
) -> dict:
    now = datetime.now(UTC)
    return {
        "id": uuid.uuid4(),
        "repo_id": repo_id,
        "github_id": uuid.uuid4().int & ((1 << 63) - 1),
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "author_login": "bob",
        "author_avatar_url": None,
        "labels": [],
        "comments_count": 0,
        "reactions_total": 0,
        "created_at": now - timedelta(days=3),
        "updated_at": now - timedelta(days=1),
        **rest,
    }


@pytest.mark.asyncio
async def test_rebuild_includes_only_open_items_from_tracked_repos(
    test_user_id,
) -> None:
    user_id, tracked, untracked = test_user_id

    async with SessionLocal() as db:
        await db.execute(
            insert(PullRequest),
            [
                _pr(tracked, number=1),  # ✓ keep
                _pr(tracked, number=2, state="closed"),  # ✗ closed
                _pr(tracked, number=3, state="merged"),  # ✗ merged
                _pr(untracked, number=4),  # ✗ untracked repo
            ],
        )
        await db.execute(
            insert(Issue),
            [
                _issue(tracked, number=10),  # ✓ keep
                _issue(tracked, number=11, state="closed"),  # ✗ closed
                _issue(untracked, number=12),  # ✗ untracked repo
            ],
        )
        await db.commit()

        count = await rebuild_inbox_items(db, user_id)
        await db.commit()

        rows = list(
            (
                await db.execute(
                    select(InboxItem).where(InboxItem.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

    assert count == 2
    assert {r.number for r in rows} == {1, 10}
    assert {r.kind for r in rows} == {"pr", "issue"}
    assert all(r.state == "open" for r in rows)


@pytest.mark.asyncio
async def test_rebuild_replaces_previous_inbox(test_user_id) -> None:
    """A second rebuild must DELETE the prior rows, not duplicate."""
    user_id, tracked, _ = test_user_id

    async with SessionLocal() as db:
        await db.execute(insert(Issue), [_issue(tracked, number=1)])
        await db.commit()

        await rebuild_inbox_items(db, user_id)
        await db.commit()

        # Run again with no source changes
        count_two = await rebuild_inbox_items(db, user_id)
        await db.commit()

        total = (
            await db.execute(
                select(InboxItem).where(InboxItem.user_id == user_id)
            )
        ).scalars().all()

    assert count_two == 1
    assert len(total) == 1


@pytest.mark.asyncio
async def test_rebuild_handles_empty_source(test_user_id) -> None:
    """User with no PRs/issues → 0 inbox rows, no errors."""
    user_id, _, _ = test_user_id

    async with SessionLocal() as db:
        count = await rebuild_inbox_items(db, user_id)
        await db.commit()

    assert count == 0


@pytest.mark.asyncio
async def test_rebuild_persists_priority_score_and_denorm_fields(test_user_id) -> None:
    """Boost label + reactions: score should reflect static_priority output."""
    user_id, tracked, _ = test_user_id

    async with SessionLocal() as db:
        await db.execute(
            insert(Issue),
            [
                _issue(
                    tracked,
                    number=42,
                    labels=["good first issue", "bug"],
                    reactions_total=20,
                )
            ],
        )
        await db.commit()

        await rebuild_inbox_items(db, user_id)
        await db.commit()

        row = (
            await db.execute(
                select(InboxItem).where(InboxItem.user_id == user_id)
            )
        ).scalar_one()

    # 0.5 * 20 = 10, plus 5 for boost label = 15
    assert float(row.priority_score) == pytest.approx(15.0)
    assert row.repo_full_name == "test-owner/tracked-repo"
    assert row.url == "https://github.com/test-owner/tracked-repo/issues/42"
    assert row.labels == ["good first issue", "bug"]
    assert row.reactions_total == 20


@pytest.mark.asyncio
async def test_rebuild_url_for_pr_uses_pull_segment(test_user_id) -> None:
    user_id, tracked, _ = test_user_id

    async with SessionLocal() as db:
        await db.execute(insert(PullRequest), [_pr(tracked, number=99, draft=True)])
        await db.commit()

        await rebuild_inbox_items(db, user_id)
        await db.commit()

        row = (
            await db.execute(
                select(InboxItem).where(InboxItem.user_id == user_id)
            )
        ).scalar_one()

    assert row.url == "https://github.com/test-owner/tracked-repo/pull/99"
    assert row.draft is True
    # Draft penalty: -10
    assert float(row.priority_score) == pytest.approx(-10.0)
