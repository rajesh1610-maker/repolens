"""Single-user-mode user resolution.

v0.1 has at most one row in `users`. `get_current_user` returns it (or None
if no PAT has ever been saved and no sync has run). When multi-user lands
in v0.4 this becomes a session-cookie lookup.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


async def get_current_user(db: AsyncSession) -> User | None:
    result = await db.execute(select(User).limit(1))
    return result.scalar_one_or_none()


async def resolve_pat(db: AsyncSession) -> str | None:
    """Return the active GitHub PAT.

    Order of precedence:
        1. Encrypted PAT on the user row (saved via Settings UI)
        2. `GITHUB_PAT` env var (Phase 1 fallback)
        3. None — caller must error
    """
    from .crypto import decrypt
    from ..config import get_settings

    user = await get_current_user(db)
    if user is not None and user.pat_encrypted is not None:
        return decrypt(user.pat_encrypted)
    return get_settings().github_pat
