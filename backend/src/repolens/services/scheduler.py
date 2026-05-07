"""APScheduler integration.

Two jobs in a single AsyncIOScheduler running in the FastAPI event loop:

  * `repolens.full_sync` — interval-driven GitHub sync (D5/D6).
  * `repolens.weekly_digest` — Sun 22:00 UTC, generates the AI digest
    for the just-completed Mon-Sun window (Phase 8b). Skipped silently
    when there's no API key configured — no errors leaked to the
    scheduler loop.

Both ticks are fire-and-forget: SyncBusy / CryptoError / missing
prerequisites are caught and logged so a single failure doesn't take
the loop down.

Gated by `scheduler_enabled` config so dev with `uvicorn --reload`
doesn't burn API quota on every save. Jobstore is in-memory — single
process, single fixed cadence per job, rebuilt on startup from env.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import get_settings
from ..db import SessionLocal
from .auth import get_current_user, resolve_anthropic_key
from .crypto import CryptoError
from .digest_generator import DigestGenerationError, generate_digest
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


async def _weekly_digest_tick() -> None:
    """One scheduled weekly-digest generation. All errors logged, none re-raised.

    Resolves the API key fresh each tick so a key saved mid-week starts
    working without a restart. No-op when the key is missing — a
    digest is opt-in.
    """
    settings = get_settings()
    try:
        async with SessionLocal() as db:
            user = await get_current_user(db)
            if user is None:
                log.info("scheduler.weekly_digest skipped — no user configured")
                return
            api_key = await resolve_anthropic_key(db)
            if not api_key:
                log.info(
                    "scheduler.weekly_digest skipped — no Anthropic key configured"
                )
                return
            result = await generate_digest(
                db, user, api_key, model=settings.digest_model
            )
        log.info(
            "scheduler.weekly_digest ok period=%s..%s tokens_in=%s tokens_out=%s "
            "cost=$%s warnings=%s",
            result.digest.period_start,
            result.digest.period_end,
            result.digest.tokens_in,
            result.digest.tokens_out,
            result.digest.cost_usd,
            len(result.warnings),
        )
    except DigestGenerationError as exc:
        log.warning("scheduler.weekly_digest failed — %s", exc)
    except CryptoError as exc:
        log.warning("scheduler.weekly_digest skipped — crypto error: %s", exc)
    except Exception:
        log.exception("scheduler.weekly_digest failed")


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
    # Sun 22:00 UTC — late enough that the Mon-Sun window is closed,
    # early enough to land in the user's Monday-morning email if we
    # ever wire up notifications (Phase 9+).
    _scheduler.add_job(
        _weekly_digest_tick,
        CronTrigger(day_of_week="sun", hour=22, minute=0, timezone="UTC"),
        id="repolens.weekly_digest",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    log.info(
        "scheduler started — sync every %s min, weekly digest Sun 22:00 UTC",
        settings.scheduler_interval_minutes,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler stopped")
