"""Tests for the slot-acquisition + watchdog logic.

These exercise sync.is_sync_running and reap_stale_running_runs against
the dev DB. Each test creates and cleans up its own test rows so we don't
pollute real history.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert

from repolens.db import SessionLocal
from repolens.models import SyncRun
from repolens.services.sync import (
    is_sync_running,
    reap_stale_running_runs,
)


async def _insert_run(started_at: datetime, status: str = "running") -> uuid.UUID:
    rid = uuid.uuid4()
    async with SessionLocal() as db:
        await db.execute(
            insert(SyncRun).values(
                id=rid,
                started_at=started_at,
                repos_synced=0,
                pulls_synced=0,
                issues_synced=0,
                api_calls=0,
                status=status,
            )
        )
        await db.commit()
    return rid


async def _cleanup(rid: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(SyncRun).where(SyncRun.id == rid))
        await db.commit()


@pytest.mark.asyncio
async def test_recent_running_run_blocks_new_acquisition() -> None:
    rid = await _insert_run(datetime.now(UTC) - timedelta(minutes=2))
    try:
        async with SessionLocal() as db:
            assert await is_sync_running(db) is True
    finally:
        await _cleanup(rid)


@pytest.mark.asyncio
async def test_stale_running_run_is_reaped_then_unblocks() -> None:
    """A 'running' row older than the watchdog window must be marked failed."""
    # 30 minutes old > default 15-minute watchdog
    rid = await _insert_run(datetime.now(UTC) - timedelta(minutes=30))
    try:
        async with SessionLocal() as db:
            reaped = await reap_stale_running_runs(db)
            assert reaped >= 1
            # After reaping, no rows should be 'running'
            assert await is_sync_running(db) is False
    finally:
        await _cleanup(rid)


@pytest.mark.asyncio
async def test_no_running_runs_returns_false() -> None:
    async with SessionLocal() as db:
        # The dev DB might already have completed runs; no `running` ones.
        await reap_stale_running_runs(db)
        assert await is_sync_running(db) is False
