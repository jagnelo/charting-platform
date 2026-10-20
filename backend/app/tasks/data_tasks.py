"""
Background data tasks — bulk historical fetches.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
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
    core_refresh_request_key,
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

    scheduled_at = datetime.now(UTC)
    run_date = scheduled_at.date()
    async with AsyncSessionLocal() as db:
        instruments = (
            (await db.execute(select(Instrument).where(Instrument.is_active.is_(True))))
            .scalars()
            .all()
        )
        for instrument in instruments:
            await enqueue_refresh_job(
                db,
                request_key=core_refresh_request_key(instrument.id, run_date=run_date),
                capability="price_history",
                instrument_id=instrument.id,
                timeframe=Timeframe.D1.value,
                priority=100,
                metadata_payload={
                    "schedule": "core_session_daily",
                    "run_date": run_date.isoformat(),
                },
                now=scheduled_at,
            )
        await db.commit()
        return {"queued": len(instruments), "mode": "enqueue_only"}


def _refresh_queue_batch_limit(limit: int | None = None) -> int:
    """Return a bounded queue batch size for one worker tick."""

    configured = (
        limit
        if limit is not None
        else getattr(settings, "MARKET_DATA_REFRESH_QUEUE_BATCH_SIZE", 100)
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = 100
    return max(1, min(parsed, 500))


async def process_refresh_jobs(ctx: dict, limit: int | None = None) -> dict:
    """Process queued requests with lease/retry telemetry and bounded fan-out."""

    async with AsyncSessionLocal() as db:
        jobs = await claim_refresh_jobs(db, limit=_refresh_queue_batch_limit(limit))
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
                bars = await fetch_ohlcv(
                    db,
                    instrument,
                    timeframe,
                    start,
                    end=job.end_at,
                    redis=ctx.get("redis"),
                )
                await complete_refresh_job(
                    db,
                    job,
                    result_summary={
                        "instrument_id": instrument.id,
                        "timeframe": timeframe.value,
                        "requested_start": start.isoformat(),
                        "requested_end": job.end_at.isoformat() if job.end_at else None,
                        "bars_observed": len(bars),
                        "data_status": "observed" if bars else "empty",
                    },
                )
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


async def refresh_provider_account_usage_snapshots(ctx: dict) -> dict:
    """Refresh explicitly configured provider-native account counters.

    Account introspection is provider traffic and is therefore never inferred
    from a generic schedule. Deployments must enable this task and name each
    provider explicitly; the service still applies that provider's credential,
    quota, entitlement, and circuit-breaker gates before making a request.
    """

    from app.config import settings
    from app.services.provider_account_usage import (
        refresh_provider_account_usage,
    )

    if not settings.PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED:
        return {"skipped": True, "reason": "provider account-usage refresh disabled"}
    configured = getattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", [])
    providers = tuple(
        dict.fromkeys(
            str(provider).strip()
            for provider in (configured if isinstance(configured, list) else [])
            if str(provider).strip()
        )
    )
    if not providers:
        return {"skipped": True, "reason": "no provider account-usage refresh providers configured"}

    async with AsyncSessionLocal() as db:
        results = []
        for provider in providers:
            try:
                results.append(await refresh_provider_account_usage(db, provider_name=provider))
            except Exception as exc:  # noqa: BLE001 - keep one provider failure from suppressing others.
                results.append(
                    {
                        "status": "failed",
                        "providers": [],
                        "observations": [],
                        "failures": [
                            {
                                "provider": provider,
                                "error": bounded_redact_provider_message(exc, max_length=500),
                            }
                        ],
                    }
                )
    return {"providers": list(providers), "results": results}


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
    if settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED:
        return {
            "skipped": True,
            "reason": "EDGAR issuer and SEC directory scans are mutually exclusive",
        }
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


async def refresh_edgar_ipo_pipeline_for_sec_directory(ctx: dict) -> dict:
    """Scan one durable page of SEC ticker associations after policy gates."""

    from app.config import settings
    from app.services.market_event_edgar_scan import (
        refresh_edgar_ipo_pipeline_for_sec_directory as _refresh_edgar_ipo_pipeline_for_sec_directory,
    )

    if not settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED:
        return {"skipped": True, "reason": "EDGAR SEC directory scan disabled"}
    if settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED:
        return {
            "skipped": True,
            "reason": "EDGAR issuer and SEC directory scans are mutually exclusive",
        }
    max_submissions_requests = int(
        settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_SUBMISSIONS_REQUESTS
    )
    if max_submissions_requests <= 0:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget not reviewed",
        }
    if max_submissions_requests > 500:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget must be at most 500",
        }
    configured_max_issuers = int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS)
    if not 1 <= configured_max_issuers <= 500:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory max issuers must be between 1 and 500",
        }
    if configured_max_issuers > max_submissions_requests:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory submissions request budget is below max issuers",
        }
    today = datetime.now(UTC).date()
    lookback_days = max(1, int(settings.MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS))
    max_issuers = configured_max_issuers
    max_events = max(
        1,
        int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER),
    )
    materialization_mode = (
        str(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ISSUER_MATERIALIZATION_MODE).strip().lower()
    )
    if materialization_mode not in {"disabled", "create_missing"}:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory issuer materialization mode is invalid",
        }
    reviewed_cycle_count = int(settings.MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_REVIEWED_CYCLE_COUNT)
    if reviewed_cycle_count < 0:
        return {
            "skipped": True,
            "reason": "EDGAR SEC directory reviewed cycle count must be non-negative",
        }
    async with AsyncSessionLocal() as db:
        return await _refresh_edgar_ipo_pipeline_for_sec_directory(
            db,
            start=today - timedelta(days=lookback_days),
            end=today,
            max_issuers=max_issuers,
            max_events_per_issuer=max_events,
            max_submissions_requests=max_submissions_requests,
            issuer_materialization_mode=materialization_mode,
            issuer_materialization_reviewed_cycle_count=reviewed_cycle_count,
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


async def refresh_tokenized_asset_catalog(ctx: dict) -> dict:
    """Discover a bounded tokenized catalogue through durable provider routing."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_assets

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_assets(
            db,
            max_pages=settings.TOKENIZED_CATALOG_REFRESH_MAX_PAGES,
            page_size=settings.TOKENIZED_CATALOG_REFRESH_PAGE_SIZE,
        )


async def refresh_tokenized_historical_asset_prices(ctx: dict) -> dict:
    """Persist a bounded tokenized aggregate-history batch."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_historical_prices

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_historical_prices(
            db,
            max_assets=settings.TOKENIZED_HISTORICAL_REFRESH_MAX_ASSETS,
            timespan=settings.TOKENIZED_HISTORICAL_REFRESH_TIMESPAN,
        )


async def refresh_tokenized_corporate_actions(ctx: dict) -> dict:
    """Persist bounded tokenized corporate-action feeds as market events."""

    from app.config import settings
    from app.services.tokenized_assets import refresh_tokenized_events

    async with AsyncSessionLocal() as db:
        return await refresh_tokenized_events(
            db,
            max_providers=settings.TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS,
            max_pages=settings.TOKENIZED_EVENT_REFRESH_MAX_PAGES,
            page_size=settings.TOKENIZED_EVENT_REFRESH_PAGE_SIZE,
        )
