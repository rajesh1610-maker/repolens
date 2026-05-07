from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import SyncRun
from ..services.crypto import CryptoError
from ..services.sync import SyncBusy, attempt_sync, reap_stale_running_runs

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _serialize_run(run: SyncRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    duration_ms: int | None = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    return {
        "id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": duration_ms,
        "repos_synced": run.repos_synced,
        "pulls_synced": run.pulls_synced,
        "issues_synced": run.issues_synced,
        "api_calls": run.api_calls,
        "rate_limit_remaining": run.rate_limit_remaining,
        "error": run.error,
    }


@router.get("/last")
async def get_last_sync(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await reap_stale_running_runs(db)
    stmt = select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1)
    run = (await db.execute(stmt)).scalar_one_or_none()
    return {"last_run": _serialize_run(run)}


@router.get("/runs")
async def list_recent_runs(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Last N sync runs, newest first. Powers the Settings → Sync admin table."""
    await reap_stale_running_runs(db)
    stmt = select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        "items": [_serialize_run(r) for r in rows],
        "limit": limit,
    }


@router.post("")
async def trigger_sync(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Run a sync now. Returns 409 if one is already in flight."""
    try:
        run = await attempt_sync(db)
    except SyncBusy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sync is already running. Wait for it to finish or check the watchdog.",
        )
    except CryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Cannot decrypt the saved PAT: {exc}. "
                f"Restore REPOLENS_ENCRYPTION_KEY or DELETE /api/settings/pat and re-save."
            ),
        ) from exc
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No PAT configured. Save one via Settings or set GITHUB_PAT in backend/.env.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Sync failed: {type(exc).__name__}: {exc}",
        ) from exc

    return {"ok": True, "run": _serialize_run(run)}
