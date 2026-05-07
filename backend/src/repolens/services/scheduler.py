"""APScheduler integration.

Single AsyncIOScheduler running in the FastAPI event loop. One periodic
job (`_tick`) calls attempt_sync(); SyncBusy / CryptoError / no-PAT are
all swallowed and logged — the scheduler tick is fire-and-forget.

Gated by `scheduler_enabled` config (D5) so dev with `uvicorn --reload`
doesn't burn API quota on every save.

Jobstore is in-memory (D6) — single fixed-cadence job, rebuilt on
startup from env. No persistence needed in v0.1.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..config import get_settings
from ..db import SessionLocal
from .crypto import CryptoError
from .sync import SyncBusy, attempt_sync

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _tick() -> None:
    """One scheduled sync attempt. All errors logged, none re-raised."""
    try:
        async with SessionLocal() as db:
            run = await attempt_sync(db)
        log.info(
            "scheduler.sync ok repos=%s pulls=%s issues=%s api_calls=%s",
            run.repos_synced,
            run.pulls_synced,
            run.issues_synced,
            run.api_calls,
        )
    except SyncBusy:
        log.info("scheduler.sync skipped — a sync is already running")
    except CryptoError as exc:
        log.warning("scheduler.sync skipped — crypto error: %s", exc)
    except ValueError as exc:
        log.warning("scheduler.sync skipped — %s", exc)
    except Exception:
        log.exception("scheduler.sync failed")


def start_scheduler() -> None:
    """Start the scheduler if config says so. Idempotent."""
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("scheduler disabled (set REPOLENS_SCHEDULER_ENABLED=true to enable)")
        return
    if _scheduler is not None:
        log.warning("scheduler already started; skipping")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _tick,
        IntervalTrigger(minutes=settings.scheduler_interval_minutes),
        id="repolens.full_sync",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
        next_run_time=None,  # don't fire immediately on startup
    )
    _scheduler.start()
    log.info(
        "scheduler started — interval %s minutes",
        settings.scheduler_interval_minutes,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler stopped")
