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
    from ..config import get_settings
    from .crypto import decrypt

    user = await get_current_user(db)
    if user is not None and user.pat_encrypted is not None:
        return decrypt(user.pat_encrypted)
    return get_settings().github_pat


async def resolve_anthropic_key(db: AsyncSession) -> str | None:
    """Return the active Anthropic API key (Phase 8 — weekly digest).

    Mirrors `resolve_pat`:
        1. Encrypted key on the user row (saved via Settings UI)
        2. `ANTHROPIC_API_KEY` env var (dev fallback)
        3. None — caller must surface a "configure key first" error
    """
    from ..config import get_settings
    from .crypto import decrypt

    user = await get_current_user(db)
    if user is not None and user.anthropic_key_encrypted is not None:
        return decrypt(user.anthropic_key_encrypted)
    return get_settings().anthropic_api_key
