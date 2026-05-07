from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Repo, User
from ..services.auth import get_current_user
from ..services.crypto import CryptoError, encrypt
from ..services.github_client import GitHubClient

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PatSaveRequest(BaseModel):
    pat: str = Field(..., min_length=20, description="GitHub PAT (classic or fine-grained)")

    @field_validator("pat")
    @classmethod
    def _strip_whitespace(cls, v: str) -> str:
        return v.strip()


class PublicOnlyToggleRequest(BaseModel):
    public_only_mode: bool


def _user_summary(user: User | None) -> dict[str, Any]:
    if user is None:
        return {
            "configured": False,
            "github_login": None,
            "avatar_url": None,
            "has_pat": False,
            "has_anthropic_key": False,
            "public_only_mode": False,
        }
    return {
        "configured": True,
        "github_login": user.github_login,
        "avatar_url": user.avatar_url,
        "has_pat": user.pat_encrypted is not None,
        "has_anthropic_key": user.anthropic_key_encrypted is not None,
        "public_only_mode": user.public_only_mode,
    }


async def _repo_counts(db: AsyncSession) -> dict[str, int]:
    total_q = select(func.count()).select_from(Repo)
    tracked_q = total_q.where(Repo.tracked.is_(True))
    public_q = total_q.where(Repo.visibility == "public")
    private_q = total_q.where(Repo.visibility == "private")
    total = (await db.execute(total_q)).scalar() or 0
    tracked = (await db.execute(tracked_q)).scalar() or 0
    public = (await db.execute(public_q)).scalar() or 0
    private = (await db.execute(private_q)).scalar() or 0
    return {"total": total, "tracked": tracked, "public": public, "private": private}


@router.get("")
async def get_settings_overview(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    user = await get_current_user(db)
    return {
        "user": _user_summary(user),
        "repos": await _repo_counts(db),
    }


@router.post("/pat")
async def save_pat(body: PatSaveRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Validate the PAT against GitHub /user, then encrypt and persist."""
    try:
        async with GitHubClient(token=body.pat) as gh:
            gh_user = await gh.get_authenticated_user()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not authenticate with GitHub: {type(exc).__name__}",
        ) from exc

    existing = await get_current_user(db)
    if existing is not None and existing.github_id != gh_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"RepoLens v0.1 is single-user. Current user is "
                f"{existing.github_login} (id {existing.github_id}); the PAT "
                f"you supplied authenticates as {gh_user['login']} (id "
                f"{gh_user['id']}). Wipe local data first or use the existing user's PAT."
            ),
        )

    try:
        pat_blob = encrypt(body.pat)
    except CryptoError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    stmt = (
        insert(User)
        .values(
            github_id=gh_user["id"],
            github_login=gh_user["login"],
            email=gh_user.get("email"),
            avatar_url=gh_user.get("avatar_url"),
            pat_encrypted=pat_blob,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_={
                "github_login": gh_user["login"],
                "email": gh_user.get("email"),
                "avatar_url": gh_user.get("avatar_url"),
                "pat_encrypted": pat_blob,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
    fresh = await get_current_user(db)
    return {"ok": True, "user": _user_summary(fresh)}


@router.delete("/pat")
async def delete_pat(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        raise HTTPException(status_code=404, detail="No user configured")
    await db.execute(update(User).where(User.id == user.id).values(pat_encrypted=None))
    await db.commit()
    await db.refresh(user)
    return {"ok": True, "user": _user_summary(user)}


@router.patch("")
async def patch_settings(
    body: PublicOnlyToggleRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user = await get_current_user(db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save a PAT first (no user row exists yet).",
        )
    await db.execute(
        update(User).where(User.id == user.id).values(public_only_mode=body.public_only_mode)
    )
    await db.commit()
    await db.refresh(user)
    return {"ok": True, "user": _user_summary(user)}
