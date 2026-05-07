from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..services.auth import get_current_user
from ..services.triage import hot_issues, stale_issues, stuck_issues

router = APIRouter(prefix="/api", tags=["triage"])


@router.get("/triage")
async def get_triage(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """All three triage columns in one call.

    Returning all three together is a UX win — the page shows them side
    by side and any single column is small enough to ship inline.
    """
    user = await get_current_user(db)
    if user is None:
        return {"stale": [], "hot": [], "stuck": []}

    return {
        "stale": await stale_issues(db, user),
        "hot": await hot_issues(db, user),
        "stuck": await stuck_issues(db, user),
    }
