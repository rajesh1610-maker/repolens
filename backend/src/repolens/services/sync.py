from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import (
    Contributor,
    Issue,
    PullRequest,
    Release,
    Repo,
    StarsDaily,
    SyncRun,
    TrafficDaily,
    User,
)
from .auth import resolve_pat
from .github_client import GitHubClient, StatsNotReady
from .inbox_builder import rebuild_inbox_items

log = logging.getLogger(__name__)

# How far back to look on the very first sync (no prior successful run).
INITIAL_SYNC_LOOKBACK = timedelta(days=90)

# Contributors are scored by commits in the trailing N weeks. 13 weeks ≈ 90
# days, matching the spec's "last 90d" requirement (specs/02_data_model.md).
CONTRIBUTOR_RECENT_WEEKS = 13


class SyncBusy(Exception):
    """Raised when a sync is already running and the caller should back off."""


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed: datetime = datetime.fromisoformat(value)
    return parsed


def _iso_date(value: str | None) -> date | None:
    """Parse a GitHub ISO timestamp into the UTC date component."""
    parsed = _parse_iso(value)
    return parsed.date() if parsed is not None else None


def _derive_pr_state(gh_pr: dict[str, Any]) -> str:
    """GitHub's PR state is open|closed; we promote to 'merged' if merged_at is set."""
    if gh_pr.get("merged_at"):
        return "merged"
    state: str = gh_pr.get("state", "open")
    return state


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


async def _upsert_release(
    db: AsyncSession, repo_id: uuid.UUID, gh_release: dict[str, Any], now: datetime
) -> None:
    payload = {
        "tag_name": gh_release.get("tag_name", ""),
        "name": gh_release.get("name"),
        "published_at": _parse_iso(gh_release.get("published_at")),
        "draft": bool(gh_release.get("draft", False)),
        "prerelease": bool(gh_release.get("prerelease", False)),
        "body_md": gh_release.get("body"),
        "synced_at": now,
    }
    stmt = (
        insert(Release)
        .values(
            id=uuid.uuid4(),
            repo_id=repo_id,
            github_id=gh_release["id"],
            **payload,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=payload,
        )
    )
    await db.execute(stmt)


async def sync_traffic_for_repo(
    db: AsyncSession, github: GitHubClient, repo: Repo
) -> int:
    """Pull GitHub's last-14-days views + clones, upsert one row per (repo, day).

    Returns the number of distinct days touched. Idempotent: re-syncing
    the rolling window updates existing rows (GitHub revises counts as
    new events arrive) and inserts new days on the leading edge.
    """
    views_payload = await github.get_repo_traffic_views(repo.owner, repo.name)
    clones_payload = await github.get_repo_traffic_clones(repo.owner, repo.name)

    by_day: dict[date, dict[str, int]] = {}
    for entry in views_payload.get("views") or []:
        d = _iso_date(entry.get("timestamp"))
        if d is None:
            continue
        by_day.setdefault(d, {"views": 0, "unique_views": 0, "clones": 0, "unique_clones": 0})
        by_day[d]["views"] = int(entry.get("count", 0))
        by_day[d]["unique_views"] = int(entry.get("uniques", 0))
    for entry in clones_payload.get("clones") or []:
        d = _iso_date(entry.get("timestamp"))
        if d is None:
            continue
        by_day.setdefault(d, {"views": 0, "unique_views": 0, "clones": 0, "unique_clones": 0})
        by_day[d]["clones"] = int(entry.get("count", 0))
        by_day[d]["unique_clones"] = int(entry.get("uniques", 0))

    if not by_day:
        return 0

    now = datetime.now(UTC)
    rows = [
        {
            "repo_id": repo.id,
            "day": day,
            "views": vals["views"],
            "unique_views": vals["unique_views"],
            "clones": vals["clones"],
            "unique_clones": vals["unique_clones"],
            "synced_at": now,
        }
        for day, vals in by_day.items()
    ]
    stmt = insert(TrafficDaily).values(rows)
    update_payload = {
        col: getattr(stmt.excluded, col)
        for col in ("views", "unique_views", "clones", "unique_clones", "synced_at")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["repo_id", "day"], set_=update_payload
    )
    await db.execute(stmt)
    return len(rows)


async def sync_stars_snapshot_for_repo(
    db: AsyncSession, repo: Repo
) -> None:
    """Snapshot today's stargazer count from the already-synced repo row.

    No additional API call: `repo.stars` was set when /user/repos was
    fetched at the top of run_full_sync. Idempotent on (repo_id, day).
    """
    today = datetime.now(UTC).date()
    stmt = (
        insert(StarsDaily)
        .values(repo_id=repo.id, day=today, stars_total=repo.stars)
        .on_conflict_do_update(
            index_elements=["repo_id", "day"],
            set_={"stars_total": repo.stars, "synced_at": datetime.now(UTC)},
        )
    )
    await db.execute(stmt)


def parse_contributor_stats(
    stats: list[dict[str, Any]], *, recent_weeks: int = CONTRIBUTOR_RECENT_WEEKS
) -> list[dict[str, Any]]:
    """Pure transform: GitHub /stats/contributors → list of contributor rows.

    Sums commits over the last `recent_weeks` weeks (≈90 days at 13).
    Skips entries with no author login. The `last_commit_at` is the
    most recent week with a non-zero commit count, converted from the
    Unix timestamp GitHub returns. Pure for testability.
    """
    parsed: list[dict[str, Any]] = []
    for entry in stats:
        author = entry.get("author") or {}
        login = author.get("login")
        if not login:
            continue
        weeks = entry.get("weeks") or []
        recent = weeks[-recent_weeks:]
        commits_total = sum(int(w.get("c", 0)) for w in recent)
        last_active_ts = max(
            (int(w.get("w", 0)) for w in recent if w.get("c")), default=0
        )
        last_commit_at: datetime | None = (
            datetime.fromtimestamp(last_active_ts, tz=UTC) if last_active_ts else None
        )
        parsed.append(
            {
                "github_login": login,
                "avatar_url": author.get("avatar_url"),
                "commits_total": commits_total,
                "last_commit_at": last_commit_at,
            }
        )
    return parsed


async def sync_contributors_for_repo(
    db: AsyncSession, github: GitHubClient, repo: Repo
) -> int:
    """Rebuild contributors for one repo from GitHub's /stats/contributors.

    Semantics: REPLACE the per-repo contributor list with whatever GitHub
    returns. Old rows for contributors no longer in the response are
    deleted — the spec ("we rebuild the full list on each successful
    contributors-sync, so missing rows indicate the contributor stopped
    contributing") is enforced here. The DELETE + INSERT are inside the
    same per-repo transaction (committed together by run_full_sync), so a
    failed insert leaves the previous contributor list intact.

    Returns the count of contributor rows persisted. Returns 0 (no error,
    no DELETE) when GitHub answers 202 — the cache is still warming and
    we'll get real data on the next sync.
    """
    try:
        stats = await github.get_repo_contributors_stats(repo.owner, repo.name)
    except StatsNotReady:
        log.info("contributors stats not ready for %s; will retry next sync", repo.full_name)
        return 0

    parsed = parse_contributor_stats(stats)

    # Replace, don't merge: drop the prior list for this repo. (Pure
    # upsert would leave inactive contributors as ghosts.)
    await db.execute(delete(Contributor).where(Contributor.repo_id == repo.id))

    if not parsed:
        return 0

    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "repo_id": repo.id,
            "github_login": entry["github_login"],
            "avatar_url": entry["avatar_url"],
            "commits_total": entry["commits_total"],
            "last_commit_at": entry["last_commit_at"],
            "synced_at": now,
        }
        for entry in parsed
    ]
    await db.execute(insert(Contributor).values(rows))
    return len(rows)


async def sync_releases_for_repo(
    db: AsyncSession, github: GitHubClient, repo: Repo
) -> int:
    now = datetime.now(UTC)
    count = 0
    async for gh_rel in github.list_repo_releases(repo.owner, repo.name):
        await _upsert_release(db, repo.id, gh_rel, now)
        count += 1
    return count


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
        releases_synced = 0
        traffic_days_synced = 0
        contributors_synced = 0
        for repo in tracked_repos:
            pulls_synced += await sync_pulls_for_repo(db, github, repo, since=since_floor)
            issues_synced += await sync_issues_for_repo(db, github, repo, since=since_floor)
            releases_synced += await sync_releases_for_repo(db, github, repo)
            traffic_days_synced += await sync_traffic_for_repo(db, github, repo)
            await sync_stars_snapshot_for_repo(db, repo)
            contributors_synced += await sync_contributors_for_repo(db, github, repo)
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
                releases_synced=releases_synced,
                traffic_days_synced=traffic_days_synced,
                contributors_synced=contributors_synced,
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
    rowcount: int = getattr(result, "rowcount", 0) or 0
    return rowcount


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
