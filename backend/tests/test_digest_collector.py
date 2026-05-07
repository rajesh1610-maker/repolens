"""Integration tests for the digest fact collector.

Each test seeds its own user + repo + activity in a Mon-Sun window and
asserts the collector picks up exactly that window. Teardown CASCADEs
from the user row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, insert

from repolens.db import SessionLocal
from repolens.models import (
    Issue,
    PullRequest,
    Release,
    Repo,
    StarsDaily,
    TrafficDaily,
    User,
)
from repolens.services.digest_collector import collect_facts, week_window

# A fixed Mon-Sun window inside the past so we never accidentally
# overlap with the system clock's "current week" during a test run.
PERIOD_START = date(2026, 4, 27)  # Monday
PERIOD_END = date(2026, 5, 3)  # Sunday
INSIDE = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
BEFORE = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
AFTER = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
async def seeded_user_repo() -> Any:
    user_id = uuid.uuid4()
    repo_id = uuid.uuid4()
    base_gh = 8_500_000_000_000

    async with SessionLocal() as db:
        await db.execute(
            insert(User).values(
                id=user_id,
                github_id=base_gh,
                github_login=f"digest-test-{user_id.hex[:8]}",
                public_only_mode=False,
            )
        )
        await db.execute(
            insert(Repo).values(
                id=repo_id,
                user_id=user_id,
                github_id=base_gh + 1,
                owner="dt",
                name="repo",
                full_name="dt/repo",
                visibility="public",
                stars=10,
                forks=0,
                open_issues_count=0,
                tracked=True,
            )
        )
        await db.commit()

    yield user_id, repo_id

    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _load_user(user_id: uuid.UUID) -> User:
    async with SessionLocal() as db:
        from sqlalchemy import select

        return (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one()


def _pr_row(repo_id: uuid.UUID, **rest: Any) -> dict[str, Any]:
    base = {
        "id": uuid.uuid4(),
        "repo_id": repo_id,
        "github_id": uuid.uuid4().int & ((1 << 63) - 1),
        "number": 1,
        "title": "PR",
        "state": "merged",
        "draft": False,
        "author_login": "alice",
        "labels": [],
        "created_at": INSIDE - timedelta(days=1),
        "updated_at": INSIDE,
    }
    base.update(rest)
    return base


def _issue_row(repo_id: uuid.UUID, **rest: Any) -> dict[str, Any]:
    base = {
        "id": uuid.uuid4(),
        "repo_id": repo_id,
        "github_id": uuid.uuid4().int & ((1 << 63) - 1),
        "number": 1,
        "title": "Issue",
        "state": "open",
        "author_login": "bob",
        "labels": [],
        "comments_count": 0,
        "reactions_total": 0,
        "created_at": INSIDE,
        "updated_at": INSIDE,
    }
    base.update(rest)
    return base


def test_week_window_returns_previous_full_week() -> None:
    # 2026-05-07 is a Thursday → previous full week is 2026-04-27..2026-05-03
    start, end = week_window(reference=date(2026, 5, 7))
    assert start == PERIOD_START
    assert end == PERIOD_END
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6  # Sunday


def test_week_window_when_reference_is_monday() -> None:
    # 2026-05-04 (Monday) → previous full week = 2026-04-27..2026-05-03
    start, end = week_window(reference=date(2026, 5, 4))
    assert start == PERIOD_START
    assert end == PERIOD_END


@pytest.mark.asyncio
async def test_collect_facts_includes_only_in_window_merged_prs(
    seeded_user_repo,
) -> None:
    user_id, repo_id = seeded_user_repo
    async with SessionLocal() as db:
        await db.execute(
            insert(PullRequest),
            [
                _pr_row(repo_id, number=10, merged_at=INSIDE),  # ✓
                _pr_row(repo_id, number=11, merged_at=BEFORE),  # ✗ before
                _pr_row(repo_id, number=12, merged_at=AFTER),  # ✗ after
                _pr_row(
                    repo_id, number=13, state="open", merged_at=None
                ),  # ✗ unmerged
            ],
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["totals"]["merged_prs"] == 1
    assert [pr["number"] for pr in facts["merged_prs"]] == [10]
    assert facts["repo_count"] == 1


@pytest.mark.asyncio
async def test_collect_facts_separates_new_and_closed_issues(
    seeded_user_repo,
) -> None:
    user_id, repo_id = seeded_user_repo
    async with SessionLocal() as db:
        await db.execute(
            insert(Issue),
            [
                _issue_row(repo_id, number=1, created_at=INSIDE, state="open"),  # new
                _issue_row(
                    repo_id,
                    number=2,
                    created_at=BEFORE,
                    closed_at=INSIDE,
                    state="closed",
                ),  # closed-in-window only
                _issue_row(
                    repo_id,
                    number=3,
                    created_at=BEFORE,
                    state="open",
                ),  # not new, not closed → drop
            ],
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["totals"]["opened_issues"] == 1
    assert facts["totals"]["closed_issues"] == 1
    assert {i["number"] for i in facts["new_issues"]} == {1}
    assert {i["number"] for i in facts["closed_issues"]} == {2}


@pytest.mark.asyncio
async def test_collect_facts_releases_window(seeded_user_repo) -> None:
    user_id, repo_id = seeded_user_repo
    async with SessionLocal() as db:
        await db.execute(
            insert(Release),
            [
                {
                    "id": uuid.uuid4(),
                    "repo_id": repo_id,
                    "github_id": 1,
                    "tag_name": "v1.0.0",
                    "name": "v1.0.0",
                    "published_at": INSIDE,
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "id": uuid.uuid4(),
                    "repo_id": repo_id,
                    "github_id": 2,
                    "tag_name": "v0.9.0",
                    "name": "v0.9.0",
                    "published_at": BEFORE,
                    "draft": False,
                    "prerelease": False,
                },
                {
                    "id": uuid.uuid4(),
                    "repo_id": repo_id,
                    "github_id": 3,
                    "tag_name": "v1.0.1-draft",
                    "name": "draft",
                    "published_at": INSIDE,
                    "draft": True,  # ✗ excluded
                    "prerelease": False,
                },
            ],
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["totals"]["releases"] == 1
    assert facts["releases"][0]["tag"] == "v1.0.0"


@pytest.mark.asyncio
async def test_collect_facts_stars_delta_uses_boundary_snapshots(
    seeded_user_repo,
) -> None:
    """Delta = stars(period_end) - stars(period_start - 1)."""
    user_id, repo_id = seeded_user_repo
    boundary_before = PERIOD_START - timedelta(days=1)

    async with SessionLocal() as db:
        await db.execute(
            insert(StarsDaily),
            [
                {"repo_id": repo_id, "day": boundary_before, "stars_total": 100},
                {"repo_id": repo_id, "day": PERIOD_END, "stars_total": 107},
            ],
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["totals"]["stars_delta"] == 7
    assert facts["stars_by_repo"][0]["delta"] == 7


@pytest.mark.asyncio
async def test_collect_facts_traffic_window_sum(seeded_user_repo) -> None:
    user_id, repo_id = seeded_user_repo
    async with SessionLocal() as db:
        await db.execute(
            insert(TrafficDaily),
            [
                {
                    "repo_id": repo_id,
                    "day": PERIOD_START + timedelta(days=1),
                    "views": 50,
                    "unique_views": 10,
                    "clones": 5,
                    "unique_clones": 2,
                },
                {
                    "repo_id": repo_id,
                    "day": PERIOD_END,
                    "views": 30,
                    "unique_views": 8,
                    "clones": 3,
                    "unique_clones": 1,
                },
                # Outside window — must be excluded
                {
                    "repo_id": repo_id,
                    "day": PERIOD_START - timedelta(days=2),
                    "views": 999,
                    "unique_views": 999,
                    "clones": 999,
                    "unique_clones": 999,
                },
            ],
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["totals"]["views"] == 80
    assert facts["totals"]["unique_views"] == 18
    assert facts["totals"]["clones"] == 8


@pytest.mark.asyncio
async def test_collect_facts_no_repos_returns_empty_facts(seeded_user_repo) -> None:
    """User with all repos untracked → all-zero facts dict, no crashes."""
    user_id, repo_id = seeded_user_repo
    async with SessionLocal() as db:
        from sqlalchemy import update

        await db.execute(
            update(Repo).where(Repo.id == repo_id).values(tracked=False)
        )
        await db.commit()

    user = await _load_user(user_id)
    async with SessionLocal() as db:
        facts = await collect_facts(db, user, PERIOD_START, PERIOD_END)

    assert facts["repo_count"] == 0
    assert facts["totals"]["merged_prs"] == 0
    assert facts["merged_prs"] == []
    assert facts["stuck_issues"] == []
