from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import SyncRun
from ..services.auth import resolve_pat
from ..services.crypto import CryptoError
from ..services.github_client import GitHubClient
from ..services.sync import sync_repos

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _serialize_run(run: SyncRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "repos_synced": run.repos_synced,
        "api_calls": run.api_calls,
        "rate_limit_remaining": run.rate_limit_remaining,
        "error": run.error,
    }


@router.get("/last")
async def get_last_sync(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return the most recent sync run (any status), or null if none."""
    stmt = select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    return {"last_run": _serialize_run(run)}


@router.post("")
async def trigger_sync(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Run a sync now. Synchronous — returns when done.

    Phase 3: with only repo metadata, this typically completes in <2s.
    Phase 4 (PR/issue sync) will move to a background task with status polling.
    """
    try:
        pat = await resolve_pat(db)
    except CryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Cannot decrypt the saved PAT: {exc}. "
                f"Restore REPOLENS_ENCRYPTION_KEY or DELETE /api/settings/pat and re-save."
            ),
        ) from exc

    if not pat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No PAT configured. Save one via Settings or set GITHUB_PAT in backend/.env.",
        )

    try:
        async with GitHubClient(token=pat) as github:
            run = await sync_repos(db, github)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Sync failed: {type(exc).__name__}: {exc}",
        ) from exc

    return {"ok": True, "run": _serialize_run(run)}
