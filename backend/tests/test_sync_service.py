"""Integration tests for run_full_sync + upsert helpers.

GitHub is mocked via httpx.MockTransport on the GitHubClient passed
into run_full_sync. The DB is real (dev Postgres). All test data is
namespaced under a synthetic user (`github_id = 9_999_xxx`) and
cleaned up via CASCADE.

These tests would have caught:
 - The `RETURNING(User)` ORM-state bug from Phase 2 (settings flow).
 - A future regression in PR state derivation (open vs merged).
 - Idempotency failures in INSERT … ON CONFLICT logic.
 - inbox_items not being rebuilt at sync end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select

from repolens.db import SessionLocal
from repolens.models import InboxItem, Issue, PullRequest, Repo, SyncRun, User
from repolens.services.github_client import GitHubClient
from repolens.services.sync import (
    _upsert_pull_request,
    _upsert_repo,
    _upsert_user,
    run_full_sync,
)

TEST_USER_GITHUB_ID = 9_999_001


def _gh_user(login: str = "syncuser", uid: int = TEST_USER_GITHUB_ID) -> dict[str, Any]:
    return {
        "id": uid,
        "login": login,
        "email": None,
        "avatar_url": "https://avatars.example/x.png",
    }


def _gh_repo(repo_id: int = 9_999_101) -> dict[str, Any]:
    return {
        "id": repo_id,
        "owner": {"login": "syncuser"},
        "name": "demo",
        "full_name": "syncuser/demo",
        "description": "test repo",
        "visibility": "public",
        "default_branch": "main",
        "stargazers_count": 5,
        "forks_count": 1,
        "open_issues_count": 1,
        "pushed_at": "2026-05-01T00:00:00Z",
    }


def _gh_pr(prid: int = 9_999_201, number: int = 1) -> dict[str, Any]:
    """Stamp updated_at as 'now' so the since-floor in run_full_sync never skips it."""
    now_iso = datetime.now(UTC).isoformat()
    return {
        "id": prid,
        "number": number,
        "title": "Add feature X",
        "state": "open",
        "draft": False,
        "user": {"login": "alice", "avatar_url": "https://a.example"},
        "labels": [{"name": "feature"}],
        "created_at": now_iso,
        "updated_at": now_iso,
        "closed_at": None,
        "merged_at": None,
    }


def _gh_issue(iid: int = 9_999_301, number: int = 10) -> dict[str, Any]:
    now_iso = datetime.now(UTC).isoformat()
    return {
        "id": iid,
        "number": number,
        "title": "Bug somewhere",
        "state": "open",
        "user": {"login": "bob", "avatar_url": "https://b.example"},
        "labels": [{"name": "bug"}],
        "comments": 2,
        "reactions": {"total_count": 5},
        "created_at": now_iso,
        "updated_at": now_iso,
        "closed_at": None,
    }


def _resp(payload: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


def make_github_handler(
    *,
    pulls: list[dict[str, Any]] | None = None,
    issues: list[dict[str, Any]] | None = None,
    repos: list[dict[str, Any]] | None = None,
    user: dict[str, Any] | None = None,
):
    """Build a MockTransport handler that serves the standard sync endpoints."""
    pulls = pulls if pulls is not None else [_gh_pr()]
    issues = issues if issues is not None else [_gh_issue()]
    repos = repos if repos is not None else [_gh_repo()]
    user = user if user is not None else _gh_user()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/user":
            return _resp(user, headers={"x-ratelimit-remaining": "4998"})
        if path == "/user/repos":
            return _resp(repos)
        if path.endswith("/pulls"):
            return _resp(pulls)
        if path.endswith("/issues"):
            return _resp(issues)
        return httpx.Response(404, json={"message": "not stubbed"})

    return handler


@pytest.fixture
async def cleanup_test_user():
    """Remove the synthetic test user after each test (CASCADE drops the rest)."""
    yield
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.github_id == TEST_USER_GITHUB_ID))
        await db.commit()


# ---------------- run_full_sync ----------------


@pytest.mark.asyncio
async def test_run_full_sync_happy_path(cleanup_test_user) -> None:
    handler = make_github_handler()
    transport = httpx.MockTransport(handler)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            run = await run_full_sync(db, gh)

        assert run.status == "ok"
        assert run.repos_synced == 1
        assert run.pulls_synced == 1
        assert run.issues_synced == 1
        assert run.api_calls >= 4  # /user, /user/repos, /pulls, /issues

        # User row created
        user = (
            await db.execute(
                select(User).where(User.github_id == TEST_USER_GITHUB_ID)
            )
        ).scalar_one()
        assert user.github_login == "syncuser"

        # Repo row created
        repos = list(
            (await db.execute(select(Repo).where(Repo.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(repos) == 1
        assert repos[0].full_name == "syncuser/demo"
        assert repos[0].stars == 5
        assert repos[0].tracked is True  # default

        # PR row created
        prs = list(
            (await db.execute(select(PullRequest).where(PullRequest.repo_id == repos[0].id)))
            .scalars()
            .all()
        )
        assert len(prs) == 1
        assert prs[0].state == "open"
        assert prs[0].labels == ["feature"]

        # Issue row created
        issues = list(
            (await db.execute(select(Issue).where(Issue.repo_id == repos[0].id)))
            .scalars()
            .all()
        )
        assert len(issues) == 1
        assert issues[0].reactions_total == 5
        assert issues[0].comments_count == 2

        # Inbox rebuilt — both items are open, on a tracked repo
        inbox = list(
            (await db.execute(select(InboxItem).where(InboxItem.user_id == user.id)))
            .scalars()
            .all()
        )
        assert len(inbox) == 2
        assert {i.kind for i in inbox} == {"pr", "issue"}


@pytest.mark.asyncio
async def test_run_full_sync_is_idempotent(cleanup_test_user) -> None:
    """Two consecutive syncs leave the same row counts (no duplicates)."""
    handler = make_github_handler()
    transport = httpx.MockTransport(handler)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            await run_full_sync(db, gh)
        async with GitHubClient(token="t", transport=transport) as gh:
            await run_full_sync(db, gh)

        user = (
            await db.execute(
                select(User).where(User.github_id == TEST_USER_GITHUB_ID)
            )
        ).scalar_one()
        repos = list(
            (await db.execute(select(Repo).where(Repo.user_id == user.id)))
            .scalars()
            .all()
        )
        prs = list(
            (await db.execute(select(PullRequest).where(PullRequest.repo_id == repos[0].id)))
            .scalars()
            .all()
        )

    assert len(repos) == 1
    assert len(prs) == 1


@pytest.mark.asyncio
async def test_run_full_sync_failure_marks_run_failed(cleanup_test_user) -> None:
    """If GitHub returns 500 mid-pipeline, the SyncRun row records 'failed'."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return _resp(_gh_user())
        if request.url.path == "/user/repos":
            return httpx.Response(500, json={"message": "boom"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            with pytest.raises(httpx.HTTPStatusError):
                await run_full_sync(db, gh)

        # Find the SyncRun row created during this attempt
        run = (
            await db.execute(
                select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1)
            )
        ).scalar_one()
    assert run.status == "failed"
    assert run.error is not None
    assert "HTTPStatusError" in run.error


@pytest.mark.asyncio
async def test_run_full_sync_preserves_tracked_flag_across_runs(cleanup_test_user) -> None:
    """Untracking a repo locally must survive the next sync."""
    handler = make_github_handler()
    transport = httpx.MockTransport(handler)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            await run_full_sync(db, gh)

        user = (
            await db.execute(select(User).where(User.github_id == TEST_USER_GITHUB_ID))
        ).scalar_one()
        repo = (
            await db.execute(select(Repo).where(Repo.user_id == user.id))
        ).scalar_one()

        # Manually untrack
        repo.tracked = False
        await db.commit()

        # Re-sync
        async with GitHubClient(token="t", transport=transport) as gh:
            await run_full_sync(db, gh)

        await db.refresh(repo)

    assert repo.tracked is False


# ---------------- upsert helpers ----------------


@pytest.mark.asyncio
async def test_upsert_user_creates_then_updates() -> None:
    async with SessionLocal() as db:
        user = await _upsert_user(db, _gh_user(login="initial"))
        await db.commit()
        first_id = user.id

        # Same github_id, different login → update, same row
        updated = await _upsert_user(db, _gh_user(login="renamed"))
        await db.commit()

    assert updated.id == first_id
    assert updated.github_login == "renamed"

    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.github_id == TEST_USER_GITHUB_ID))
        await db.commit()


@pytest.mark.asyncio
async def test_upsert_repo_does_not_clobber_tracked_flag(cleanup_test_user) -> None:
    """Re-upserting a repo whose user has untracked it must not flip back to tracked=true."""
    async with SessionLocal() as db:
        user = await _upsert_user(db, _gh_user())
        await db.commit()

        await _upsert_repo(db, user.id, _gh_repo(), datetime.now(UTC))
        await db.commit()

        repo = (
            await db.execute(select(Repo).where(Repo.user_id == user.id))
        ).scalar_one()
        repo.tracked = False
        await db.commit()

        # Second upsert with same github_id
        await _upsert_repo(db, user.id, _gh_repo(), datetime.now(UTC))
        await db.commit()

        await db.refresh(repo)

    assert repo.tracked is False


@pytest.mark.asyncio
async def test_upsert_pull_request_derives_merged_state(cleanup_test_user) -> None:
    """A PR with merged_at set should land with state='merged' regardless of GitHub's state."""
    async with SessionLocal() as db:
        user = await _upsert_user(db, _gh_user())
        await db.commit()
        await _upsert_repo(db, user.id, _gh_repo(), datetime.now(UTC))
        await db.commit()
        repo = (
            await db.execute(select(Repo).where(Repo.user_id == user.id))
        ).scalar_one()

        gh_pr_merged = _gh_pr()
        # GitHub's "state" is just 'open'|'closed'; merged_at promotes locally.
        gh_pr_merged["state"] = "closed"
        gh_pr_merged["merged_at"] = "2026-05-02T12:00:00Z"

        await _upsert_pull_request(db, repo.id, gh_pr_merged, datetime.now(UTC))
        await db.commit()

        pr = (
            await db.execute(select(PullRequest).where(PullRequest.repo_id == repo.id))
        ).scalar_one()

    assert pr.state == "merged"
    assert pr.merged_at is not None


@pytest.mark.asyncio
async def test_run_full_sync_filters_open_only_into_inbox(cleanup_test_user) -> None:
    """Closed/merged items must not appear in the rebuilt inbox."""
    closed_pr = _gh_pr(prid=9_999_211, number=2)
    closed_pr["state"] = "closed"
    closed_pr["closed_at"] = datetime.now(UTC).isoformat()

    closed_issue = _gh_issue(iid=9_999_311, number=11)
    closed_issue["state"] = "closed"
    closed_issue["closed_at"] = datetime.now(UTC).isoformat()

    handler = make_github_handler(
        pulls=[_gh_pr(), closed_pr],
        issues=[_gh_issue(), closed_issue],
    )
    transport = httpx.MockTransport(handler)

    async with SessionLocal() as db:
        async with GitHubClient(token="t", transport=transport) as gh:
            await run_full_sync(db, gh)

        user = (
            await db.execute(select(User).where(User.github_id == TEST_USER_GITHUB_ID))
        ).scalar_one()
        inbox = list(
            (await db.execute(select(InboxItem).where(InboxItem.user_id == user.id)))
            .scalars()
            .all()
        )

    # 2 open items → 2 inbox rows. The 2 closed never made it.
    assert len(inbox) == 2
    assert all(i.state == "open" for i in inbox)
