"""Phase 8: collect 7-day activity facts for the weekly digest.

Pure SQL — no GitHub calls, no LLM calls. Reads from the same tables the
dashboards already read from, so the digest reflects exactly what the
user sees in the UI. The output is a deterministic JSON-shaped dict so:

    1. The same window can be regenerated and the input reproduced from
       the persisted `input_summary` JSONB column.
    2. Tests can pin the LLM input independent of cron timing.

Window convention: Mon 00:00 UTC ≤ event_time < next-Mon 00:00 UTC. Dates
on the digest row use `period_start = Mon`, `period_end = Sun` so the
"week of YYYY-MM-DD" label is stable across timezones.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Issue, PullRequest, Release, Repo, StarsDaily, TrafficDaily, User
from .triage import stuck_issues

# Cap how much detail we feed the LLM. The digest has ~1500 token output;
# more than these counts tip the prompt into "summarize a list" territory
# rather than "write a story." The tail is summarized via _and N more counts.
MAX_MERGED_PRS = 20
MAX_NEW_ISSUES = 20
MAX_CLOSED_ISSUES = 20
MAX_STUCK = 10
MAX_RELEASES = 10


def week_window(reference: date | None = None) -> tuple[date, date]:
    """Return (period_start, period_end) for the most recently completed week.

    If `reference` is a Monday, we return the *previous* Mon-Sun window —
    that's the natural "send this on Sunday night" or "first thing Monday"
    semantics. Caller can pass any date; we always anchor to the Monday
    of the prior calendar week.
    """
    today = reference or datetime.now(UTC).date()
    # Monday of THIS week:
    this_monday = today - timedelta(days=today.weekday())
    period_start = this_monday - timedelta(days=7)
    period_end = this_monday - timedelta(days=1)
    return period_start, period_end


def _to_datetime(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


async def collect_facts(
    db: AsyncSession,
    user: User,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    """Build the JSON facts dict the LLM will read.

    Visibility (D16): public_only_mode filters which repos contribute.
    Same predicate logic as the dashboards — the digest never leaks a
    private repo when public_only is on.
    """
    start_dt = _to_datetime(period_start)
    end_dt = _to_datetime(period_end + timedelta(days=1))  # half-open

    repo_where = [Repo.user_id == user.id, Repo.tracked.is_(True)]
    if user.public_only_mode:
        repo_where.append(Repo.visibility == "public")

    repos_stmt = select(Repo).where(and_(*repo_where))
    repos: list[Repo] = list((await db.execute(repos_stmt)).scalars().all())
    repo_ids = [r.id for r in repos]
    repo_by_id = {r.id: r for r in repos}

    if not repo_ids:
        return _empty_facts(user, period_start, period_end)

    merged_prs = await _merged_prs(db, repo_ids, repo_by_id, start_dt, end_dt)
    new_issues = await _new_issues(db, repo_ids, repo_by_id, start_dt, end_dt)
    closed_issues = await _closed_issues(db, repo_ids, repo_by_id, start_dt, end_dt)
    releases = await _releases(db, repo_ids, repo_by_id, start_dt, end_dt)
    stars_delta_total, stars_by_repo = await _stars_delta(
        db, repo_ids, repo_by_id, period_start, period_end
    )
    traffic = await _traffic_totals(db, repo_ids, period_start, period_end)
    stuck = [_stuck_to_fact(s) for s in await stuck_issues(db, user, limit=MAX_STUCK)]

    return {
        "user": {"github_login": user.github_login},
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "repo_count": len(repos),
        "totals": {
            "merged_prs": len(merged_prs["all"]),
            "opened_issues": len(new_issues["all"]),
            "closed_issues": len(closed_issues["all"]),
            "releases": len(releases["all"]),
            "stars_delta": stars_delta_total,
            "views": traffic["views"],
            "unique_views": traffic["unique_views"],
            "clones": traffic["clones"],
        },
        "merged_prs": merged_prs["sample"],
        "merged_prs_truncated": merged_prs["truncated"],
        "new_issues": new_issues["sample"],
        "new_issues_truncated": new_issues["truncated"],
        "closed_issues": closed_issues["sample"],
        "closed_issues_truncated": closed_issues["truncated"],
        "releases": releases["sample"],
        "releases_truncated": releases["truncated"],
        "stars_by_repo": stars_by_repo,
        "stuck_issues": stuck,
    }


def _empty_facts(
    user: User, period_start: date, period_end: date
) -> dict[str, Any]:
    return {
        "user": {"github_login": user.github_login},
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "repo_count": 0,
        "totals": {
            "merged_prs": 0,
            "opened_issues": 0,
            "closed_issues": 0,
            "releases": 0,
            "stars_delta": 0,
            "views": 0,
            "unique_views": 0,
            "clones": 0,
        },
        "merged_prs": [],
        "merged_prs_truncated": 0,
        "new_issues": [],
        "new_issues_truncated": 0,
        "closed_issues": [],
        "closed_issues_truncated": 0,
        "releases": [],
        "releases_truncated": 0,
        "stars_by_repo": [],
        "stuck_issues": [],
    }


async def _merged_prs(
    db: AsyncSession,
    repo_ids: list[Any],
    repo_by_id: dict[Any, Repo],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, Any]:
    stmt = (
        select(PullRequest)
        .where(
            and_(
                PullRequest.repo_id.in_(repo_ids),
                PullRequest.merged_at.is_not(None),
                PullRequest.merged_at >= start_dt,
                PullRequest.merged_at < end_dt,
            )
        )
        .order_by(PullRequest.merged_at.desc())
    )
    rows: list[PullRequest] = list((await db.execute(stmt)).scalars().all())
    sample = [
        {
            "repo": repo_by_id[pr.repo_id].full_name,
            "number": pr.number,
            "title": pr.title,
            "author": pr.author_login,
            "labels": pr.labels,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        }
        for pr in rows[:MAX_MERGED_PRS]
    ]
    return {
        "all": rows,
        "sample": sample,
        "truncated": max(0, len(rows) - MAX_MERGED_PRS),
    }


async def _new_issues(
    db: AsyncSession,
    repo_ids: list[Any],
    repo_by_id: dict[Any, Repo],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, Any]:
    stmt = (
        select(Issue)
        .where(
            and_(
                Issue.repo_id.in_(repo_ids),
                Issue.created_at >= start_dt,
                Issue.created_at < end_dt,
            )
        )
        .order_by(Issue.reactions_total.desc(), Issue.created_at.desc())
    )
    rows: list[Issue] = list((await db.execute(stmt)).scalars().all())
    sample = [
        {
            "repo": repo_by_id[i.repo_id].full_name,
            "number": i.number,
            "title": i.title,
            "author": i.author_login,
            "labels": i.labels,
            "reactions_total": i.reactions_total,
            "comments_count": i.comments_count,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in rows[:MAX_NEW_ISSUES]
    ]
    return {
        "all": rows,
        "sample": sample,
        "truncated": max(0, len(rows) - MAX_NEW_ISSUES),
    }


async def _closed_issues(
    db: AsyncSession,
    repo_ids: list[Any],
    repo_by_id: dict[Any, Repo],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, Any]:
    stmt = (
        select(Issue)
        .where(
            and_(
                Issue.repo_id.in_(repo_ids),
                Issue.closed_at.is_not(None),
                Issue.closed_at >= start_dt,
                Issue.closed_at < end_dt,
            )
        )
        .order_by(Issue.closed_at.desc())
    )
    rows: list[Issue] = list((await db.execute(stmt)).scalars().all())
    sample = [
        {
            "repo": repo_by_id[i.repo_id].full_name,
            "number": i.number,
            "title": i.title,
            "labels": i.labels,
            "closed_at": i.closed_at.isoformat() if i.closed_at else None,
        }
        for i in rows[:MAX_CLOSED_ISSUES]
    ]
    return {
        "all": rows,
        "sample": sample,
        "truncated": max(0, len(rows) - MAX_CLOSED_ISSUES),
    }


async def _releases(
    db: AsyncSession,
    repo_ids: list[Any],
    repo_by_id: dict[Any, Repo],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, Any]:
    stmt = (
        select(Release)
        .where(
            and_(
                Release.repo_id.in_(repo_ids),
                Release.published_at.is_not(None),
                Release.published_at >= start_dt,
                Release.published_at < end_dt,
                Release.draft.is_(False),
            )
        )
        .order_by(Release.published_at.desc())
    )
    rows: list[Release] = list((await db.execute(stmt)).scalars().all())
    sample = [
        {
            "repo": repo_by_id[r.repo_id].full_name,
            "tag": r.tag_name,
            "name": r.name,
            "prerelease": r.prerelease,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows[:MAX_RELEASES]
    ]
    return {
        "all": rows,
        "sample": sample,
        "truncated": max(0, len(rows) - MAX_RELEASES),
    }


async def _stars_delta(
    db: AsyncSession,
    repo_ids: list[Any],
    repo_by_id: dict[Any, Repo],
    period_start: date,
    period_end: date,
) -> tuple[int, list[dict[str, Any]]]:
    """Sum stars_delta = stars_total(period_end) - stars_total(period_start - 1).

    StarsDaily is a daily snapshot, so the delta over the window is just
    the difference between the last day inside the window and the day
    BEFORE the window started. If we don't have a "day before" snapshot
    yet (new install), the start anchor is the earliest snapshot we do
    have inside the window — best-effort.
    """
    boundary_before = period_start - timedelta(days=1)

    end_stmt = select(StarsDaily.repo_id, StarsDaily.stars_total).where(
        and_(StarsDaily.repo_id.in_(repo_ids), StarsDaily.day == period_end)
    )
    end_rows = {row[0]: row[1] for row in (await db.execute(end_stmt)).all()}

    start_stmt = select(StarsDaily.repo_id, StarsDaily.stars_total).where(
        and_(StarsDaily.repo_id.in_(repo_ids), StarsDaily.day == boundary_before)
    )
    start_rows = {row[0]: row[1] for row in (await db.execute(start_stmt)).all()}

    total = 0
    by_repo: list[dict[str, Any]] = []
    for repo_id in repo_ids:
        end_v = end_rows.get(repo_id)
        start_v = start_rows.get(repo_id)
        if end_v is None or start_v is None:
            continue
        delta = int(end_v) - int(start_v)
        if delta == 0:
            continue
        total += delta
        by_repo.append(
            {
                "repo": repo_by_id[repo_id].full_name,
                "delta": delta,
                "stars_total": int(end_v),
            }
        )
    by_repo.sort(key=lambda d: int(d["delta"]), reverse=True)
    return total, by_repo


async def _traffic_totals(
    db: AsyncSession,
    repo_ids: list[Any],
    period_start: date,
    period_end: date,
) -> dict[str, int]:
    stmt = select(
        func.coalesce(func.sum(TrafficDaily.views), 0),
        func.coalesce(func.sum(TrafficDaily.unique_views), 0),
        func.coalesce(func.sum(TrafficDaily.clones), 0),
    ).where(
        and_(
            TrafficDaily.repo_id.in_(repo_ids),
            TrafficDaily.day >= period_start,
            TrafficDaily.day <= period_end,
        )
    )
    row = (await db.execute(stmt)).one()
    return {
        "views": int(row[0]),
        "unique_views": int(row[1]),
        "clones": int(row[2]),
    }


def _stuck_to_fact(s: dict[str, Any]) -> dict[str, Any]:
    """Trim the triage row to only what the LLM needs."""
    return {
        "repo": s["repo_full_name"],
        "number": s["number"],
        "title": s["title"],
        "labels": s["labels"],
        "reactions_total": s["reactions_total"],
        "comments_count": s["comments_count"],
        "updated_at": s["updated_at"],
    }
