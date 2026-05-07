from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Issue, PullRequest, Repo, SyncRun, User
from .auth import resolve_pat
from .github_client import GitHubClient
from .inbox_builder import rebuild_inbox_items

log = logging.getLogger(__name__)

# How far back to look on the very first sync (no prior successful run).
INITIAL_SYNC_LOOKBACK = timedelta(days=90)


class SyncBusy(Exception):
    """Raised when a sync is already running and the caller should back off."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _derive_pr_state(gh_pr: dict[str, Any]) -> str:
    """GitHub's PR state is open|closed; we promote to 'merged' if merged_at is set."""
    if gh_pr.get("merged_at"):
        return "merged"
    return gh_pr.get("state", "open")


def _label_names(gh_item: dict[str, Any]) -> list[str]:
    return [label.get("name", "") for label in gh_item.get("labels", []) if label.get("name")]


async def _last_successful_sync_started_at(db: AsyncSession) -> datetime | None:
    stmt = (
        select(SyncRun.started_at)
        .where(SyncRun.status == "ok")
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _upsert_user(db: AsyncSession, gh_user: dict[str, Any]) -> User:
    """Upsert a user row keyed on github_id and return the fresh ORM instance.

    Note: we deliberately do NOT use `.returning(User)` here — SQLAlchemy
    2.0's ORM cache returns the originally-inserted instance after the
    `ON CONFLICT DO UPDATE` path, which leaks stale field values to the
    caller. We re-query with `populate_existing=True` so the in-session
    instance reflects the post-upsert DB state. Same pattern guards
    `routers/settings.py::save_pat`.
    """
    stmt = (
        insert(User)
        .values(
            id=uuid.uuid4(),
            github_id=gh_user["id"],
            github_login=gh_user["login"],
            email=gh_user.get("email"),
            avatar_url=gh_user.get("avatar_url"),
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_={
                "github_login": gh_user["login"],
                "email": gh_user.get("email"),
                "avatar_url": gh_user.get("avatar_url"),
            },
        )
    )
    await db.execute(stmt)
    await db.flush()
    select_stmt = (
        select(User)
        .where(User.github_id == gh_user["id"])
        .execution_options(populate_existing=True)
    )
    return (await db.execute(select_stmt)).scalar_one()


async def _upsert_repo(
    db: AsyncSession, user_id: uuid.UUID, gh_repo: dict[str, Any], now: datetime
) -> None:
    pushed_at = _parse_iso(gh_repo.get("pushed_at"))
    payload = {
        "owner": gh_repo["owner"]["login"],
        "name": gh_repo["name"],
        "full_name": gh_repo["full_name"],
        "description": gh_repo.get("description"),
        "visibility": gh_repo.get("visibility", "public"),
        "default_branch": gh_repo.get("default_branch"),
        "stars": gh_repo.get("stargazers_count", 0),
        "forks": gh_repo.get("forks_count", 0),
        "open_issues_count": gh_repo.get("open_issues_count", 0),
        "pushed_at": pushed_at,
        "synced_at": now,
    }
    stmt = (
        insert(Repo)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            github_id=gh_repo["id"],
            **payload,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=payload,
        )
    )
    await db.execute(stmt)


async def _upsert_pull_request(
    db: AsyncSession, repo_id: uuid.UUID, gh_pr: dict[str, Any], now: datetime
) -> None:
    payload = {
        "number": gh_pr["number"],
        "title": gh_pr.get("title", ""),
        "state": _derive_pr_state(gh_pr),
        "draft": bool(gh_pr.get("draft", False)),
        "author_login": (gh_pr.get("user") or {}).get("login"),
        "author_avatar_url": (gh_pr.get("user") or {}).get("avatar_url"),
        "labels": _label_names(gh_pr),
        "created_at": _parse_iso(gh_pr.get("created_at")),
        "updated_at": _parse_iso(gh_pr.get("updated_at")),
        "closed_at": _parse_iso(gh_pr.get("closed_at")),
        "merged_at": _parse_iso(gh_pr.get("merged_at")),
        "raw": gh_pr,
        "synced_at": now,
    }
    stmt = (
        insert(PullRequest)
        .values(
            id=uuid.uuid4(),
            repo_id=repo_id,
            github_id=gh_pr["id"],
            **payload,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=payload,
        )
    )
    await db.execute(stmt)


async def _upsert_issue(
    db: AsyncSession, repo_id: uuid.UUID, gh_issue: dict[str, Any], now: datetime
) -> None:
    reactions = gh_issue.get("reactions") or {}
    payload = {
        "number": gh_issue["number"],
        "title": gh_issue.get("title", ""),
        "state": gh_issue.get("state", "open"),
        "author_login": (gh_issue.get("user") or {}).get("login"),
        "author_avatar_url": (gh_issue.get("user") or {}).get("avatar_url"),
        "labels": _label_names(gh_issue),
        "comments_count": int(gh_issue.get("comments", 0)),
        "reactions_total": int(reactions.get("total_count", 0)),
        "created_at": _parse_iso(gh_issue.get("created_at")),
        "updated_at": _parse_iso(gh_issue.get("updated_at")),
        "closed_at": _parse_iso(gh_issue.get("closed_at")),
        "raw": gh_issue,
        "synced_at": now,
    }
    stmt = (
        insert(Issue)
        .values(
            id=uuid.uuid4(),
            repo_id=repo_id,
            github_id=gh_issue["id"],
            **payload,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=payload,
        )
    )
    await db.execute(stmt)


async def sync_pulls_for_repo(
    db: AsyncSession,
    github: GitHubClient,
    repo: Repo,
    *,
    since: datetime | None,
) -> int:
    now = datetime.now(UTC)
    count = 0
    async for gh_pr in github.list_repo_pulls(repo.owner, repo.name, since=since):
        await _upsert_pull_request(db, repo.id, gh_pr, now)
        count += 1
    return count


async def sync_issues_for_repo(
    db: AsyncSession,
    github: GitHubClient,
    repo: Repo,
    *,
    since: datetime | None,
) -> int:
    now = datetime.now(UTC)
    count = 0
    async for gh_issue in github.list_repo_issues(repo.owner, repo.name, since=since):
        await _upsert_issue(db, repo.id, gh_issue, now)
        count += 1
    return count


async def run_full_sync(db: AsyncSession, github: GitHubClient) -> SyncRun:
    """Top-level orchestration. Runs the full pipeline and records a SyncRun.

    Order:
        1. Identify the user, upsert
        2. List repos, upsert each
        3. For each tracked repo: pulls + issues (incremental via `since`)

    `since` is the started_at of the most recent successful run, or
    `now - INITIAL_SYNC_LOOKBACK` on the very first sync.
    """
    sync_run = SyncRun(status="running")
    db.add(sync_run)
    await db.commit()
    await db.refresh(sync_run)
    sync_run_id = sync_run.id

    since_floor = (
        await _last_successful_sync_started_at(db)
        or datetime.now(UTC) - INITIAL_SYNC_LOOKBACK
    )

    try:
        gh_user = await github.get_authenticated_user()
        user = await _upsert_user(db, gh_user)
        await db.commit()

        # Step 1: repos
        now = datetime.now(UTC)
        repos_synced = 0
        async for gh_repo in github.list_user_repos():
            await _upsert_repo(db, user.id, gh_repo, now)
            repos_synced += 1
        await db.commit()

        # Step 2: PRs + issues for each tracked repo *of this user*.
        # The user_id filter matters once multi-user lands (and prevents
        # cross-user fan-out in tests that create synthetic users).
        result = await db.execute(
            select(Repo).where(
                Repo.user_id == user.id,
                Repo.tracked.is_(True),
            )
        )
        tracked_repos = list(result.scalars().all())

        pulls_synced = 0
        issues_synced = 0
        for repo in tracked_repos:
            pulls_synced += await sync_pulls_for_repo(db, github, repo, since=since_floor)
            issues_synced += await sync_issues_for_repo(db, github, repo, since=since_floor)
            await db.commit()  # per-repo commits = bounded loss on mid-sync failure

        # Step 3: rebuild Inbox derived table. Inside the success path so
        # a failed sync never wipes out a working Inbox.
        await rebuild_inbox_items(db, user.id)
        await db.commit()

        await db.execute(
            update(SyncRun)
            .where(SyncRun.id == sync_run_id)
            .values(
                status="ok",
                repos_synced=repos_synced,
                pulls_synced=pulls_synced,
                issues_synced=issues_synced,
                api_calls=github.api_calls,
                rate_limit_remaining=github.rate_limit_remaining,
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await db.execute(
            update(SyncRun)
            .where(SyncRun.id == sync_run_id)
            .values(
                status="failed",
                error=f"{type(exc).__name__}: {exc}"[:500],
                api_calls=github.api_calls,
                rate_limit_remaining=github.rate_limit_remaining,
                finished_at=datetime.now(UTC),
            )
        )
        await db.commit()
        raise

    await db.refresh(sync_run)
    return sync_run


# Backwards-compatible alias for callers that still import sync_repos.
# Phase 4a: this now means "run the full pipeline" (repos + pulls + issues).
sync_repos = run_full_sync


# ---- 4c: slot acquisition + watchdog (D4) ---------------------------------


async def reap_stale_running_runs(db: AsyncSession) -> int:
    """Mark any 'running' rows older than the watchdog window as 'failed'.

    Returns count of reaped rows. Caller decides whether to log/surface.
    Idempotent — if a real run is in progress and within the window, it's
    untouched.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.sync_watchdog_minutes)
    stmt = (
        update(SyncRun)
        .where(SyncRun.status == "running", SyncRun.started_at < cutoff)
        .values(
            status="failed",
            error=f"watchdog: timed out after {settings.sync_watchdog_minutes}m",
            finished_at=datetime.now(UTC),
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0


async def is_sync_running(db: AsyncSession) -> bool:
    """True if a SyncRun is still 'running' AND within the watchdog window."""
    await reap_stale_running_runs(db)
    stmt = select(SyncRun.id).where(SyncRun.status == "running").limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def attempt_sync(db: AsyncSession) -> SyncRun:
    """One-shot sync entry point shared by manual API and scheduler.

    Raises:
        SyncBusy: a sync is already in flight (within watchdog window).
        CryptoError: PAT can't be decrypted.
        ValueError: no PAT configured anywhere.
        Exception: GitHub or DB failure (already recorded on the SyncRun row).
    """
    if await is_sync_running(db):
        raise SyncBusy("a sync is already running")

    pat = await resolve_pat(db)  # may raise CryptoError
    if not pat:
        raise ValueError("no PAT configured")

    async with GitHubClient(token=pat) as github:
        return await run_full_sync(db, github)
