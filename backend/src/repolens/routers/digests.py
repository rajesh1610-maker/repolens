"""Phase 8 endpoints: weekly AI digest.

POST /api/digests/generate          — generate (or regenerate) a digest
                                      for the most recent completed week
                                      (or an explicit period).
GET  /api/digests/latest            — most recent digest, or None
GET  /api/digests                   — list digests (newest first)
GET  /api/digests/{id}              — full digest by id
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import Digest
from ..services.auth import get_current_user, resolve_anthropic_key
from ..services.digest_generator import (
    DigestGenerationError,
    generate_digest,
    latest_digest,
    list_digests,
)

router = APIRouter(prefix="/api/digests", tags=["digests"])


class GenerateRequest(BaseModel):
    """Both fields optional: omit to use last completed Mon-Sun window."""

    period_start: date | None = Field(default=None)
    period_end: date | None = Field(default=None)


def _serialize(d: Digest) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "period_start": d.period_start.isoformat(),
        "period_end": d.period_end.isoformat(),
        "body_md": d.body_md,
        "input_summary": d.input_summary,
        "validation_warnings": d.validation_warnings,
        "model": d.model,
        "tokens_in": d.tokens_in,
        "tokens_out": d.tokens_out,
        "cache_creation_input_tokens": d.cache_creation_input_tokens,
        "cache_read_input_tokens": d.cache_read_input_tokens,
        "cost_usd": float(d.cost_usd),
        "stop_reason": d.stop_reason,
        "generated_at": d.generated_at.isoformat() if d.generated_at else None,
    }


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        raise HTTPException(status_code=400, detail="No user configured.")

    api_key = await resolve_anthropic_key(db)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "Anthropic API key not configured. Save one in Settings or set "
                "ANTHROPIC_API_KEY in the environment."
            ),
        )

    if (body.period_start is None) != (body.period_end is None):
        raise HTTPException(
            status_code=400,
            detail="period_start and period_end must be provided together.",
        )
    if (
        body.period_start is not None
        and body.period_end is not None
        and body.period_start > body.period_end
    ):
        raise HTTPException(
            status_code=400, detail="period_start must be <= period_end."
        )

    settings = get_settings()
    try:
        result = await generate_digest(
            db,
            user,
            api_key,
            model=settings.digest_model,
            period_start=body.period_start,
            period_end=body.period_end,
        )
    except DigestGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "digest": _serialize(result.digest),
        "warnings": result.warnings,
    }


@router.get("/latest")
async def get_latest(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        return {"digest": None}
    d = await latest_digest(db, user)
    return {"digest": _serialize(d) if d is not None else None}


@router.get("")
async def get_list(
    limit: int = 20, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        return {"items": [], "limit": limit}
    items = await list_digests(db, user, limit=max(1, min(limit, 100)))
    return {
        "items": [_serialize(d) for d in items],
        "limit": limit,
    }


@router.get("/{digest_id}")
async def get_one(
    digest_id: str, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        did = uuid.UUID(digest_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid digest id.") from exc
    stmt = select(Digest).where(Digest.id == did, Digest.user_id == user.id)
    digest = (await db.execute(stmt)).scalar_one_or_none()
    if digest is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return {"digest": _serialize(digest)}
