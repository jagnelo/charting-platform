"""
ARQ worker — async task queue backed by Redis.
Run with: python -m app.workers.arq_worker
Or via the dedicated Docker container.

Tasks defined here are enqueued by routers/services and executed here
in separate worker processes, keeping the FastAPI server non-blocking.
"""

import logging
from datetime import UTC, datetime

from arq import cron
from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)


# ── Task implementations ──────────────────────────────────────────────────────


async def task_bulk_fetch_instrument(
    ctx: dict,
    instrument_id: int,
    timeframes: list[str] | None = None,
    run_id: int | None = None,
    end: str | None = None,
):
    """
    ARQ task: pull maximum available history for one instrument.
    Enqueued automatically when a new instrument is registered.
    """
    from app.database import AsyncSessionLocal
    from app.models.instrument import Instrument
    from app.models.ohlcv import Timeframe
    from app.services.bulk_fetch import bulk_fetch_instrument, refresh_cancel_key

    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            logger.warning(f"bulk_fetch: instrument {instrument_id} not found")
            return

        tf_list = [Timeframe(tf) for tf in timeframes] if timeframes else None
        summary = await bulk_fetch_instrument(
            db,
            instrument,
            tf_list,
            redis=ctx.get("redis"),
            cancel_key=refresh_cancel_key(run_id) if run_id is not None else None,
            end=datetime.fromisoformat(end) if end else None,
        )
        logger.info(f"bulk_fetch complete for {instrument.symbol}: {summary}")
        return summary


async def task_refresh_benchmark_family_history(
    ctx: dict, instrument_ids: list[int], timeframes: list[str] | None = None
):
    """Compatibility task for callers that submit a bounded family batch.

    The HTTP maintenance route currently submits the existing per-instrument task
    directly.  Keeping this small batch entry point makes scheduled/admin callers
    able to use the same contract without adding provider logic to the router.
    """

    results = []
    for instrument_id in instrument_ids:
        results.append(await task_bulk_fetch_instrument(ctx, instrument_id, timeframes=timeframes))
    return {"instrument_count": len(instrument_ids), "results": results}


async def task_refresh_benchmark_family_holdings_run(ctx: dict, run_id: int):
    """Execute one durable provider-backed family holdings refresh unit at a time."""

    from datetime import date, datetime

    from app.database import AsyncSessionLocal
    from app.models.benchmark_family_history import BenchmarkFamilyHoldingsRefreshRun
    from app.services.benchmark_family_history import queue_snapshot_member_history
    from app.services.etf_holdings_refresh import refresh_benchmark_family_holdings_for_date

    async with AsyncSessionLocal() as db:
        run = await db.get(BenchmarkFamilyHoldingsRefreshRun, run_id)
        if run is None:
            logger.warning("benchmark-family-holdings-refresh: run %s not found", run_id)
            return {"status": "missing", "run_id": run_id}
        if run.status in {"completed", "canceled", "failed"}:
            return {"status": run.status, "run_id": run_id}

        run.status = "running"
        run.started_at = run.started_at or datetime.now(UTC)
        run.progress = {
            **(run.progress or {}),
            "status": "running",
            "total_units": run.total_units,
        }
        await db.commit()

        for requested_date_text in run.requested_dates or []:
            requested_date = date.fromisoformat(str(requested_date_text))
            for family_key in run.family_keys or []:
                run = await db.get(BenchmarkFamilyHoldingsRefreshRun, run_id)
                if run is None:
                    return {"status": "missing", "run_id": run_id}
                if run.cancel_requested or run.status == "canceled":
                    run.status = "canceled"
                    run.finished_at = datetime.now(UTC)
                    run.progress = {
                        **(run.progress or {}),
                        "status": "canceled",
                        "cancel_requested": True,
                    }
                    await db.commit()
                    return {"status": "canceled", "run_id": run_id}

                try:
                    async with db.begin_nested():
                        summary = await refresh_benchmark_family_holdings_for_date(
                            db,
                            family_key=str(family_key),
                            requested_date=requested_date,
                            roles=list(run.roles or []),
                        )
                except Exception as exc:  # noqa: BLE001 - retain per-unit failure evidence.
                    summary = {
                        "family_key": str(family_key),
                        "requested_date": requested_date,
                        "refreshed": 0,
                        "unavailable": 0,
                        "failed": 1,
                        "legs": [],
                        "error": str(exc) or "Benchmark family holdings refresh failed.",
                    }

                refreshed_snapshot_ids = [
                    int(leg["snapshot_id"])
                    for leg in summary.get("legs", [])
                    if isinstance(leg, dict)
                    and leg.get("status") == "refreshed"
                    and leg.get("snapshot_id") is not None
                ]
                if refreshed_snapshot_ids:
                    try:
                        history_queue = await queue_snapshot_member_history(
                            db,
                            ctx.get("redis"),
                            refreshed_snapshot_ids,
                        )
                    except Exception as exc:  # noqa: BLE001 - retain bounded queue evidence.
                        history_queue = {
                            "status": "queue_error",
                            "snapshot_ids": refreshed_snapshot_ids,
                            "queued": 0,
                            "already_queued": 0,
                            "error": str(exc)[:500],
                        }
                else:
                    history_queue = {
                        "status": "no_snapshots",
                        "snapshot_ids": [],
                        "queued": 0,
                        "already_queued": 0,
                    }

                run = await db.get(BenchmarkFamilyHoldingsRefreshRun, run_id)
                if run is None:
                    return {"status": "missing", "run_id": run_id}
                run.completed_units += 1
                run.refreshed_count += int(summary.get("refreshed", 0))
                run.unavailable_count += int(summary.get("unavailable", 0))
                run.failed_count += int(summary.get("failed", 0))
                prior_units = list((run.progress or {}).get("units") or [])
                prior_units.append(
                    {
                        "family_key": str(family_key),
                        "requested_date": requested_date.isoformat(),
                        "refreshed": int(summary.get("refreshed", 0)),
                        "unavailable": int(summary.get("unavailable", 0)),
                        "failed": int(summary.get("failed", 0)),
                        "legs": summary.get("legs") or [],
                        "history_queue": history_queue,
                        "error": summary.get("error"),
                    }
                )
                run.progress = {
                    "status": "running",
                    "total_units": run.total_units,
                    "completed_units": run.completed_units,
                    "last_unit": {
                        "family_key": str(family_key),
                        "requested_date": requested_date.isoformat(),
                    },
                    "units": prior_units,
                }
                await db.commit()

        run = await db.get(BenchmarkFamilyHoldingsRefreshRun, run_id)
        if run is None:
            return {"status": "missing", "run_id": run_id}
        if run.cancel_requested:
            run.status = "canceled"
        else:
            run.status = "completed"
        run.finished_at = datetime.now(UTC)
        run.progress = {
            **(run.progress or {}),
            "status": run.status,
            "completed_units": run.completed_units,
        }
        await db.commit()
        return {
            "status": run.status,
            "run_id": run_id,
            "completed_units": run.completed_units,
            "refreshed": run.refreshed_count,
            "unavailable": run.unavailable_count,
            "failed": run.failed_count,
        }


async def task_refresh_scheduled_benchmark_family_holdings_unit(
    ctx: dict,
    family_key: str,
    requested_date_text: str,
    roles: list[str] | None = None,
):
    """Run one scheduled family/date unit and queue its canonical member history."""

    from datetime import date, datetime

    from app.database import AsyncSessionLocal
    from app.services.benchmark_family_history import queue_snapshot_member_history
    from app.services.etf_holdings_refresh import refresh_benchmark_family_holdings_for_date

    requested_date = date.fromisoformat(str(requested_date_text))
    async with AsyncSessionLocal() as db:
        try:
            async with db.begin_nested():
                summary = await refresh_benchmark_family_holdings_for_date(
                    db,
                    family_key=family_key,
                    requested_date=requested_date,
                    roles=roles,
                )
        except Exception as exc:  # noqa: BLE001 - retain bounded unit failure evidence.
            summary = {
                "family_key": family_key,
                "requested_date": requested_date,
                "roles": roles or [],
                "refreshed": 0,
                "unavailable": 0,
                "failed": 1,
                "legs": [],
                "error": str(exc) or "Scheduled benchmark family refresh failed.",
            }
        snapshot_ids = [
            int(leg["snapshot_id"])
            for leg in summary.get("legs", [])
            if isinstance(leg, dict)
            and leg.get("status") == "refreshed"
            and leg.get("snapshot_id") is not None
        ]
        try:
            history_queue = await queue_snapshot_member_history(
                db,
                ctx.get("redis"),
                snapshot_ids,
            )
        except Exception as exc:  # noqa: BLE001 - retain bounded queue failure evidence.
            history_queue = {
                "status": "queue_error",
                "snapshot_ids": snapshot_ids,
                "queued": 0,
                "already_queued": 0,
                "error": str(exc) or "Scheduled benchmark family history queue failed.",
            }
        await db.commit()
        return {
            **summary,
            "requested_date": requested_date.isoformat(),
            "snapshot_ids": snapshot_ids,
            "history_queue": history_queue,
            "completed_at": datetime.now(UTC).isoformat(),
        }


async def task_run_screener(ctx: dict, screener_id: int):
    """ARQ task: run a screener by ID and persist results."""
    from app.database import AsyncSessionLocal
    from app.models.screener import ScreenerDefinition
    from app.services.screener_engine import queue_python_screener_run, run_screener

    async with AsyncSessionLocal() as db:
        screener = await db.get(ScreenerDefinition, screener_id)
        if screener is None:
            logger.warning(f"run_screener: screener {screener_id} not found")
            return
        if (
            isinstance(screener.conditions, dict)
            and screener.conditions.get("type") == "python_condition"
        ):
            result = await queue_python_screener_run(db, screener)
        else:
            result = await run_screener(db, screener)
        return {"matched": len(result.matched_ids), "duration_ms": result.duration_ms}


async def task_refresh_instrument_data(ctx: dict, instrument_id: int, timeframe: str):
    """ARQ task: refresh recent bars for one instrument/timeframe."""
    from datetime import datetime, timedelta

    from app.database import AsyncSessionLocal
    from app.models.instrument import Instrument
    from app.models.ohlcv import Timeframe
    from app.services.market_data import fetch_ohlcv

    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return
        tf = Timeframe(timeframe)
        start = datetime.now(UTC) - timedelta(days=7)
        bars = await fetch_ohlcv(db, instrument, tf, start)
        return {"bars_fetched": len(bars)}


async def task_bootstrap_core_workstation(ctx: dict):
    """Hydrate the immutable US Top Down universe on a fresh deployment."""

    from app.database import AsyncSessionLocal
    from app.services.workstation_bootstrap import bootstrap_core_workstation_data

    async with AsyncSessionLocal() as db:
        result = await bootstrap_core_workstation_data(db, redis=ctx.get("redis"))
        logger.info(
            "Core workstation bootstrap complete: history=%d holdings=%d skipped=%s",
            sum(
                1
                for item in (result.get("history") or {}).values()
                if item.get("status") in {"loaded", "ready"}
            ),
            sum(
                1
                for item in (result.get("holdings") or {}).values()
                if item.get("status") in {"loaded", "ready"}
            ),
            result.get("skipped", False),
        )
        return result


# ── Scheduled tasks (cron) ───────────────────────────────────────────────────


async def scheduled_alert_check(ctx: dict):
    """Runs alert engine on a schedule via ARQ cron (alternative to APScheduler)."""
    from app.services.alert_engine import _run_async

    await _run_async()


async def scheduled_weekly_seed(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping weekly seed")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import seed_universe_task

    return await seed_universe_task(ctx)


async def scheduled_daily_metadata_sync(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping metadata sync")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import sync_instruments_task

    return await sync_instruments_task(ctx)


async def scheduled_daily_id_bootstrap(ctx: dict):
    if not settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED:
        logger.info("Instrument sync schedule disabled; skipping stable ID bootstrap")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.instrument_sync_tasks import bootstrap_ids_task

    return await bootstrap_ids_task(ctx)


async def scheduled_daily_history_refresh(ctx: dict):
    """Refresh recent canonical OHLCV bars when explicitly enabled."""
    if not settings.MARKET_DATA_REFRESH_SCHEDULE_ENABLED:
        logger.info("Market-data refresh schedule disabled; skipping history refresh")
        return {"skipped": True, "reason": "schedule disabled"}
    from app.tasks.data_tasks import fetch_all_instruments_history

    return await fetch_all_instruments_history(ctx)


async def scheduled_etf_holdings_refresh(ctx: dict):
    from app.tasks.etf_holdings_tasks import refresh_etf_holdings_task

    return await refresh_etf_holdings_task(ctx)


async def scheduled_etf_holdings_sec_backfill(ctx: dict):
    from app.tasks.etf_holdings_tasks import backfill_sec_nport_holdings_task

    return await backfill_sec_nport_holdings_task(ctx)


async def scheduled_etf_holdings_classification_refresh(ctx: dict):
    from app.tasks.etf_holdings_tasks import reconcile_etf_holdings_classifications_task

    return await reconcile_etf_holdings_classifications_task(ctx)


async def scheduled_benchmark_family_holdings_refresh(ctx: dict):
    from app.tasks.etf_holdings_tasks import refresh_benchmark_family_holdings_task

    return await refresh_benchmark_family_holdings_task(ctx)


async def scheduled_core_workstation_bootstrap(ctx: dict):
    if not settings.CORE_WORKSTATION_BOOTSTRAP_ENABLED:
        logger.info("Core workstation bootstrap disabled; skipping")
        return {"skipped": True, "reason": "bootstrap disabled"}
    return await task_bootstrap_core_workstation(ctx)


async def scheduled_daily_provider_availability(ctx: dict):
    if (
        not settings.PROVIDER_AVAILABILITY_MONITOR_ENABLED
        or not settings.PROVIDER_AVAILABILITY_LIVE_ENABLED
    ):
        return {"status": "disabled"}
    from app.database import AsyncSessionLocal
    from app.services.provider_availability import run_availability_probes

    async with AsyncSessionLocal() as db:
        return await run_availability_probes(db, "daily_core", application_version=settings.APP_ENV)


async def scheduled_weekly_provider_availability(ctx: dict):
    if (
        not settings.PROVIDER_AVAILABILITY_MONITOR_ENABLED
        or not settings.PROVIDER_AVAILABILITY_LIVE_ENABLED
    ):
        return {"status": "disabled"}
    from app.database import AsyncSessionLocal
    from app.services.provider_availability import run_availability_probes

    async with AsyncSessionLocal() as db:
        return await run_availability_probes(
            db, "weekly_supported_sweep", application_version=settings.APP_ENV
        )


async def worker_startup(ctx: dict):
    """Queue the first hydration without blocking worker readiness.

    Provider-backed history and holdings can each legitimately spend the configured
    timeout on a cold source. Running that whole sweep inside ARQ's startup hook
    leaves the worker unavailable (and causes restart loops) for the duration of
    the sweep. Queue one idempotent job instead; ARQ can then execute it through
    the normal worker lifecycle while accepting other work.
    """

    if not settings.CORE_WORKSTATION_BOOTSTRAP_ENABLED:
        return
    redis = ctx.get("redis")
    if redis is None:
        logger.warning("Core workstation bootstrap could not be queued: Redis is unavailable")
        return
    job = await redis.enqueue_job(
        "task_bootstrap_core_workstation",
        # Bump this id when bootstrap semantics change so a completed result
        # from an older deployment cannot suppress the corrected sweep.
        _job_id="core-workstation-bootstrap-startup-v4",
        _expires=3600,
    )
    logger.info("Queued core workstation bootstrap at worker startup: job=%s", job)


# ── Worker settings ───────────────────────────────────────────────────────────


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [
        task_bulk_fetch_instrument,
        task_refresh_benchmark_family_history,
        task_refresh_benchmark_family_holdings_run,
        task_refresh_scheduled_benchmark_family_holdings_unit,
        task_run_screener,
        task_refresh_instrument_data,
        task_bootstrap_core_workstation,
        scheduled_weekly_seed,
        scheduled_daily_metadata_sync,
        scheduled_daily_id_bootstrap,
        scheduled_daily_history_refresh,
        scheduled_etf_holdings_refresh,
        scheduled_etf_holdings_sec_backfill,
        scheduled_etf_holdings_classification_refresh,
        scheduled_benchmark_family_holdings_refresh,
        scheduled_daily_provider_availability,
        scheduled_weekly_provider_availability,
    ]
    cron_jobs = (
        [
            cron(scheduled_weekly_seed, weekday=6, hour=2, minute=0),
            cron(scheduled_daily_metadata_sync, hour=3, minute=0),
            cron(scheduled_daily_id_bootstrap, hour=4, minute=0),
            cron(scheduled_daily_history_refresh, hour=5, minute=0),
            cron(scheduled_etf_holdings_refresh, weekday=6, hour=5, minute=0),
            cron(scheduled_etf_holdings_sec_backfill, weekday=6, hour=6, minute=0),
            cron(scheduled_etf_holdings_classification_refresh, weekday=6, hour=7, minute=0),
            cron(scheduled_benchmark_family_holdings_refresh, weekday=6, hour=8, minute=0),
            cron(scheduled_core_workstation_bootstrap, hour=1, minute=0),
            cron(scheduled_daily_provider_availability, hour=2, minute=0),
            cron(scheduled_weekly_provider_availability, weekday=6, hour=3, minute=0),
        ]
        if (
            settings.INSTRUMENT_SYNC_SCHEDULE_ENABLED
            or settings.MARKET_DATA_REFRESH_SCHEDULE_ENABLED
            or settings.ETF_HOLDINGS_REFRESH_ENABLED
            or settings.ETF_HOLDINGS_SEC_BACKFILL_ENABLED
            or settings.ETF_HOLDINGS_CLASSIFICATION_REFRESH_ENABLED
            or settings.BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED
            or settings.CORE_WORKSTATION_BOOTSTRAP_ENABLED
            or settings.PROVIDER_AVAILABILITY_MONITOR_ENABLED
        )
        else []
    )
    on_startup = worker_startup
    max_jobs = 4
    job_timeout = 600  # 10 minutes max per job
    keep_result = 3600  # keep results for 1 hour


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)
