"""
Background data tasks — bulk historical fetches.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.providers.errors import bounded_redact_provider_message
from app.services.market_data import fetch_ohlcv
from app.services.market_data_monitoring import build_shadow_report
from app.services.market_refresh_queue import (
    RefreshLeaseLostError,
    claim_refresh_jobs,
    complete_refresh_job,
    enqueue_refresh_job,
    retry_refresh_job,
)
from app.services.market_universe import reconcile_us_universe, record_core_daily_coverage

logger = logging.getLogger(__name__)

# Timeframes to refresh nightly (recent bars only, not full re-fetch)
NIGHTLY_REFRESH_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
]


async def _get_newest_bar_ts(db, instrument_id: int, tf: Timeframe) -> datetime | None:
    from sqlalchemy import func

    result = await db.execute(
        select(func.max(OHLCVBar.ts)).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == tf,
            OHLCVBar.is_adjusted.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def fetch_instrument_history(ctx: dict, instrument_id: int) -> dict:
    """Legacy entry-point — delegates to bulk_fetch_instrument."""
    async with AsyncSessionLocal() as db:
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            return {"error": f"Instrument {instrument_id} not found"}

        from app.services.bulk_fetch import bulk_fetch_instrument

        results = await bulk_fetch_instrument(db, instrument, redis=ctx.get("redis"))
        return {"instrument_id": instrument_id, "symbol": instrument.symbol, "results": results}


async def fetch_all_instruments_history(ctx: dict) -> dict:
    """
    Refresh OHLCV data for all active instruments in the DB.
    Intended to be run as a nightly scheduled task.
    Only fetches recent data (not full history) for efficiency.
    """
    async with AsyncSessionLocal() as db:
        instruments = (
            (
                await db.execute(
                    __import__("sqlalchemy", fromlist=["select"])
                    .select(Instrument)
                    .where(Instrument.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )

        logger.info(f"Refreshing data for {len(instruments)} instruments")
        total_bars = 0

        for instrument in instruments:
            for tf in NIGHTLY_REFRESH_TIMEFRAMES:
                try:
                    newest = await _get_newest_bar_ts(db, instrument.id, tf)
                    if newest is None:
                        # No data for this TF yet — bulk fetch handles this, skip
                        continue
                    # Small overlap buffer to catch any late-arriving bars
                    start = newest - timedelta(hours=1)
                    bars = await fetch_ohlcv(db, instrument, tf, start, redis=ctx.get("redis"))
                    total_bars += len(bars)
                except Exception as e:
                    logger.error(
                        "Refresh failed %s %s: %s",
                        instrument.symbol,
                        tf.value,
                        bounded_redact_provider_message(e),
                    )

        return {"instruments_refreshed": len(instruments), "total_bars": total_bars}


async def enqueue_core_refresh_jobs(ctx: dict) -> dict:
    """Queue whole-universe D1 work without doing provider I/O in an evaluator."""

    async with AsyncSessionLocal() as db:
        instruments = (
            (await db.execute(select(Instrument).where(Instrument.is_active.is_(True))))
            .scalars()
            .all()
        )
        for instrument in instruments:
            await enqueue_refresh_job(
                db,
                request_key=f"d1:{instrument.id}",
                capability="price_history",
                instrument_id=instrument.id,
                timeframe=Timeframe.D1.value,
                priority=100,
                metadata_payload={"schedule": "core_session_daily"},
            )
        await db.commit()
        return {"queued": len(instruments), "mode": "enqueue_only"}


async def process_refresh_jobs(ctx: dict, limit: int = 50) -> dict:
    """Process queued requests with lease/retry telemetry and bounded fan-out."""

    async with AsyncSessionLocal() as db:
        jobs = await claim_refresh_jobs(db, limit=max(1, min(limit, 500)))
        completed = 0
        retried = 0
        lease_lost = 0
        for job in jobs:
            try:
                if job.instrument_id is None or not job.timeframe:
                    raise ValueError("refresh job has no instrument/timeframe")
                instrument = await db.get(Instrument, job.instrument_id)
                if instrument is None:
                    raise ValueError(f"instrument {job.instrument_id} no longer exists")
                timeframe = Timeframe(job.timeframe)
                start = job.start_at or (datetime.now(UTC) - timedelta(days=7))
                await fetch_ohlcv(
                    db,
                    instrument,
                    timeframe,
                    start,
                    end=job.end_at,
                    redis=ctx.get("redis"),
                )
                await complete_refresh_job(db, job)
                completed += 1
            except RefreshLeaseLostError as exc:
                # Another worker owns this job now (or its lease expired).
                # Never retry or overwrite that worker's state from this
                # stale execution; the durable queue will expose/reclaim it.
                logger.info(
                    "Refresh job %s lease no longer owned: %s",
                    job.id,
                    bounded_redact_provider_message(exc),
                )
                lease_lost += 1
            except Exception as exc:
                try:
                    await retry_refresh_job(
                        db,
                        job,
                        str(exc),
                        retry_at=getattr(exc, "retry_at", None),
                    )
                except RefreshLeaseLostError as lease_exc:
                    logger.info(
                        "Refresh job %s lease lost during retry: %s",
                        job.id,
                        bounded_redact_provider_message(lease_exc),
                    )
                    lease_lost += 1
                else:
                    retried += 1
        await db.commit()
        return {
            "claimed": len(jobs),
            "completed": completed,
            "retried": retried,
            "lease_lost": lease_lost,
        }


async def run_market_data_shadow_report(ctx: dict) -> dict:
    """Produce the daily operator report without changing routing behavior."""

    async with AsyncSessionLocal() as db:
        report = await build_shadow_report(db)
        logger.info(
            "market-data shadow report: observations=%s discrepancies=%s rate=%.4f",
            report["observations"],
            report["discrepancies"],
            report["discrepancy_rate"],
        )
        return report


async def reconcile_market_universe(ctx: dict) -> dict:
    """Reconcile complete US discovery feeds, then record core D1 coverage."""

    async with AsyncSessionLocal() as db:
        reconciliation = await reconcile_us_universe(db)
        coverage = await record_core_daily_coverage(db)
        await db.commit()
        return {"reconciliation": reconciliation, "coverage": coverage}


async def refresh_market_events(ctx: dict) -> dict:
    """Persist one bounded forward market-event window when enabled."""

    from app.config import settings
    from app.services.market_events import refresh_market_events as _refresh_market_events

    if not settings.MARKET_EVENTS_REFRESH_ENABLED:
        return {"skipped": True, "reason": "market-events refresh disabled"}

    today = datetime.now(UTC).date()
    lookahead_days = max(1, int(settings.MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS))
    max_providers = max(1, int(settings.MARKET_EVENTS_REFRESH_MAX_PROVIDERS))
    async with AsyncSessionLocal() as db:
        return await _refresh_market_events(
            db,
            start=today,
            end=today + timedelta(days=lookahead_days),
            max_providers=max_providers,
        )


async def materialize_market_event_prelisting(ctx: dict) -> dict:
    """Materialize a bounded future-listing candidate set when enabled."""

    from app.config import settings
    from app.services.market_event_prelisting import (
        materialize_prelisting_candidates,
        promote_prelisting_candidates,
    )

    if not settings.MARKET_EVENTS_PRELISTING_ENABLED:
        return {"skipped": True, "reason": "pre-listing materialization disabled"}
    today = datetime.now(UTC).date()
    lookahead_days = max(1, int(settings.MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS))
    max_events = max(1, int(settings.MARKET_EVENTS_PRELISTING_MAX_EVENTS))
    async with AsyncSessionLocal() as db:
        materialized = await materialize_prelisting_candidates(
            db,
            start=today,
            end=today + timedelta(days=lookahead_days),
            max_events=max_events,
        )
        promoted = await promote_prelisting_candidates(db, max_candidates=max_events)
        await db.commit()
        return {"materialized": materialized, "promoted": promoted}


async def refresh_edgar_ipo_pipeline_for_issuer_universe(ctx: dict) -> dict:
    """Scan a durable bounded batch of known SEC issuers for filing candidates."""

    from app.config import settings
    from app.services.market_event_edgar_scan import (
        refresh_edgar_ipo_pipeline_for_issuer_universe as _refresh_edgar_ipo_pipeline_for_issuer_universe,
    )

    if not settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED:
        return {"skipped": True, "reason": "EDGAR issuer-universe scan disabled"}
    today = datetime.now(UTC).date()
    lookback_days = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS))
    max_issuers = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_ISSUERS))
    max_events = max(
        1,
        int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_EVENTS_PER_ISSUER),
    )
    async with AsyncSessionLocal() as db:
        return await _refresh_edgar_ipo_pipeline_for_issuer_universe(
            db,
            start=today - timedelta(days=lookback_days),
            end=today,
            max_issuers=max_issuers,
            max_events_per_issuer=max_events,
        )


async def refresh_tokenized_asset_prices(ctx: dict) -> dict:
    """Refresh a bounded tokenized quote batch through durable provider routing."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_prices

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_prices(
            db,
            max_assets=settings.TOKENIZED_ASSET_REFRESH_MAX_ASSETS,
        )


async def refresh_tokenized_corporate_actions(ctx: dict) -> dict:
    """Persist bounded tokenized corporate-action feeds as market events."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_events

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_events(
            db,
            max_providers=settings.TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS,
            page_size=settings.TOKENIZED_EVENT_REFRESH_PAGE_SIZE,
        )
