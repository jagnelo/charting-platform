"""
Bulk historical data fetcher.

Pulls the maximum available OHLCV history for an instrument from the configured
provider and stores it in the local DB for all supported timeframes.

Design principles:
  - Source-agnostic: provider-specific history windows come from reviewed
    machine-readable entitlement constraints, never generic assumptions.
  - Providers without an explicit history bound receive an epoch sentinel and
    are rejected by runtime admission; the source is never asked to act as an
    undocumented unlimited-history provider.
  - If a source returns nothing for a timeframe after coarser timeframes have
    returned data, we record that fact and stop asking, accepting the source
    simply doesn't provide that resolution that far back.
  - Progress is tracked in Redis so the frontend can surface meaningful UX.
  - Timeframes are processed one at a time with a configurable inter-request
    delay to respect data-source rate limits.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.providers.alpaca import estimate_ohlcv_request_count
from app.providers.binance import estimate_ohlcv_request_weight
from app.providers.crypto_market_data import (
    estimate_coinbase_ohlcv_request_count,
    estimate_kraken_ohlcv_request_count,
)
from app.providers.errors import bounded_redact_provider_message
from app.providers.ibkr import estimate_ibkr_ohlcv_request_count
from app.providers.massive import (
    estimate_ohlcv_request_count as estimate_massive_ohlcv_request_count,
)
from app.providers.optional_market_data import (
    estimate_marketdata_app_ohlcv_credit_count,
    estimate_marketstack_ohlcv_request_count,
    estimate_twelve_data_ohlcv_request_count,
)
from app.services.distributed_locks import (
    DistributedLockError,
    redis_distributed_lock,
    shared_redis_lock_client,
)
from app.services.market_data import (
    _attach_provider_series,
    _default_series_bar_condition,
    _record_bar_observations,
    _touch_ohlcv_dataset_state,
)
from app.services.provider_runtime import execute_provider_call

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# The earliest timestamp we will ever request.  The data source returns whatever
# it actually has; we never assume a fixed lookback window.
EPOCH_START = datetime(1970, 1, 1, tzinfo=UTC)

# Ordered coarsest→finest.  Coarser TFs are fetched first because they carry
# deeper history and their emptiness is a reliable signal that finer TFs will
# also be empty for a given period.
BULK_FETCH_TIMEFRAMES: list[Timeframe] = [
    Timeframe.MN,
    Timeframe.W1,
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M30,
    Timeframe.M15,
    Timeframe.M5,
    # M1 excluded: virtually every public source has a tiny 1m lookback window,
    # so bulk-fetching it would be near-useless.  Fetched on-demand instead.
]

# Seconds between consecutive timeframe requests within one bulk fetch job.
INTER_TF_DELAY_SECONDS: float = 1.5

# Redis keys / TTL
_REDIS_PROGRESS_KEY = "bulk_fetch:progress:{instrument_id}"
_REDIS_CANCEL_KEY = "watchlist-history:cancel:{run_id}"
_REDIS_TTL_SECONDS = 86_400  # 24 h


def _provider_bulk_history_start(provider_name: str, end: datetime) -> datetime:
    """Return the reviewed earliest request bound for one provider.

    A bulk refresh must not send the epoch to every adapter: the runtime's
    entitlement check needs the same requested start that the adapter will
    actually receive.  Bounds come from the machine-readable provider
    entitlement seed.  An absent or malformed bound deliberately returns the
    epoch, which makes the provider fail closed in ``resolve_provider_chain``
    rather than inventing an unlimited history entitlement.

    The seed is only a conservative request bound.  An operator may narrow a
    provider entitlement in the database; the runtime admission check still
    applies that persisted policy before the request is sent.
    """

    normalized_end = _normalize_fetch_end(end)
    provider_seed = settings.PROVIDER_ENTITLEMENT_SEEDS.get(str(provider_name).strip().lower())
    if not isinstance(provider_seed, dict):
        return EPOCH_START

    # Capability-level reviews override the provider-wide entitlement.  This
    # matters for providers such as Finnhub whose free plan may expose price
    # history only after a separate endpoint entitlement is reviewed.
    capability_seed = provider_seed.get("capabilities", {}).get("price_history")
    if isinstance(capability_seed, dict):
        provider_seed = {**provider_seed, **capability_seed}
    quota_policy = provider_seed.get("quota_policy")
    constraints = quota_policy.get("history_constraints") if isinstance(quota_policy, dict) else None
    if not isinstance(constraints, dict):
        return EPOCH_START

    raw_years = constraints.get("max_lookback_years")
    raw_days = constraints.get("max_lookback_days")
    if (raw_years is None) == (raw_days is None):
        return EPOCH_START
    raw_value = raw_years if raw_years is not None else raw_days
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value <= 0:
        return EPOCH_START
    if raw_years is not None:
        try:
            return normalized_end.replace(year=normalized_end.year - raw_value)
        except ValueError:
            # Preserve the runtime entitlement check's conservative leap-day
            # convention instead of requesting one day beyond the reviewed
            # calendar-year boundary.
            return normalized_end.replace(year=normalized_end.year - raw_value, month=2, day=28)
    return normalized_end - timedelta(days=raw_value)


# ── Public API ────────────────────────────────────────────────────────────────


async def bulk_fetch_instrument(
    db: AsyncSession,
    instrument: Instrument,
    timeframes: list[Timeframe] | None = None,
    adjusted: bool = True,
    redis=None,  # optional arq Redis pool for progress reporting
    cancel_key: str | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """
    Fetch the maximum available history for *instrument* across all timeframes.

    Returns a summary dict mapping timeframe value to one of:
      int        — number of new bars inserted (0 is valid; source was empty for TF)
      "skipped"  — skipped because coarser TF already showed source has no data
      "error:…"  — exception message
    """
    if timeframes is None:
        timeframes = BULK_FETCH_TIMEFRAMES

    ticker_sym = instrument.symbol
    summary: dict[str, Any] = {}
    fetch_end = _normalize_fetch_end(end)

    if await _is_cancel_requested(redis, cancel_key):
        await _publish_progress(redis, instrument.id, "canceled", timeframes, summary)
        return summary

    await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)

    # Track whether any coarser daily+ TF returned data.  If none did, there is
    # no point querying intraday TFs at all.
    any_daily_or_coarser_returned_data = False

    for tf in timeframes:
        if await _is_cancel_requested(redis, cancel_key):
            await _publish_progress(redis, instrument.id, "canceled", timeframes, summary)
            logger.info("Bulk fetch canceled for %s", ticker_sym)
            return summary
        is_intraday = _is_intraday(tf)

        # If all daily/weekly/monthly TFs returned nothing, skip intraday ones.
        if is_intraday and not any_daily_or_coarser_returned_data:
            summary[tf.value] = "skipped"
            logger.info(
                f"Skipping {ticker_sym} {tf.value}: "
                "no daily+ data found; source unlikely to have intraday history"
            )
            await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)
            continue

        result = await _fetch_one_timeframe(
            db=db,
            instrument=instrument,
            ticker_sym=ticker_sym,
            timeframe=tf,
            adjusted=adjusted,
            end=fetch_end,
            redis=redis,
        )
        summary[tf.value] = result

        if isinstance(result, int):
            if result > 0 and not is_intraday:
                any_daily_or_coarser_returned_data = True
            logger.info(f"Bulk fetch {ticker_sym} {tf.value}: {result} bars")
        else:
            logger.info(f"Bulk fetch {ticker_sym} {tf.value}: {result}")

        await _publish_progress(redis, instrument.id, "in_progress", timeframes, summary)
        await asyncio.sleep(INTER_TF_DELAY_SECONDS)

    if await _is_cancel_requested(redis, cancel_key):
        await _publish_progress(redis, instrument.id, "canceled", timeframes, summary)
        logger.info("Bulk fetch canceled for %s", ticker_sym)
        return summary

    await _publish_progress(redis, instrument.id, "complete", timeframes, summary)
    logger.info(f"Bulk fetch complete for {ticker_sym}: {summary}")
    return summary


async def get_fetch_progress(instrument_id: int, redis) -> dict | None:
    """
    Return the current bulk-fetch progress for an instrument from Redis,
    or None if no fetch has been recorded (or Redis is unavailable).
    """
    if redis is None:
        return None
    try:
        key = _REDIS_PROGRESS_KEY.format(instrument_id=instrument_id)
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(
            "Could not read fetch progress from Redis: %s", bounded_redact_provider_message(e)
        )
        return None


def refresh_cancel_key(run_id: int) -> str:
    """Return the Redis cancellation marker for a durable refresh run."""

    return _REDIS_CANCEL_KEY.format(run_id=run_id)


async def _is_cancel_requested(redis, cancel_key: str | None) -> bool:
    if redis is None or cancel_key is None:
        return False
    try:
        value = await redis.get(cancel_key)
        return value not in (None, b"", "", b"0", "0", False)
    except Exception as exc:  # noqa: BLE001 - cancellation must not break fetches.
        logger.warning(
            "Could not read history refresh cancellation marker: %s",
            bounded_redact_provider_message(exc),
        )
        return False


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _fetch_one_timeframe(
    db: AsyncSession,
    instrument: Instrument,
    ticker_sym: str,
    timeframe: Timeframe,
    adjusted: bool,
    end: datetime,
    redis=None,
) -> int | str:
    try:
        distributed_redis = None
        if settings.OHLCV_DISTRIBUTED_LOCK_ENABLED:
            distributed_redis = redis or shared_redis_lock_client()
        if distributed_redis is None:
            return await _do_fetch_and_store(
                db=db,
                instrument=instrument,
                ticker_sym=ticker_sym,
                timeframe=timeframe,
                adjusted=adjusted,
                end=end,
            )
        async with redis_distributed_lock(
            distributed_redis,
            namespace="ohlcv-bulk-refresh",
            identity=repr((instrument.id, timeframe.value, end, adjusted)),
            ttl_seconds=settings.OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS,
            blocking_timeout_seconds=settings.OHLCV_DISTRIBUTED_LOCK_WAIT_SECONDS,
            retry_interval_seconds=settings.OHLCV_DISTRIBUTED_LOCK_RETRY_SECONDS,
        ):
            return await _do_fetch_and_store(
                db=db,
                instrument=instrument,
                ticker_sym=ticker_sym,
                timeframe=timeframe,
                adjusted=adjusted,
                end=end,
            )
    except DistributedLockError:
        raise
    except Exception as e:
        safe_error = bounded_redact_provider_message(e)
        logger.error("Bulk fetch failed for %s %s: %s", ticker_sym, timeframe.value, safe_error)
        return f"error:{safe_error}"


async def _do_fetch_and_store(
    db: AsyncSession,
    instrument: Instrument,
    ticker_sym: str,
    timeframe: Timeframe,
    adjusted: bool,
    end: datetime,
) -> int:
    """Request the reviewed maximum history and upsert all returned bars.

    Providers with an explicit plan lookback receive that provider-specific
    lower bound. Providers without a machine-readable bound receive the epoch
    sentinel and are rejected by runtime history admission; that is safer than
    silently treating an unknown plan as unlimited history.
    """
    provider_history_starts = {
        provider_name: _provider_bulk_history_start(provider_name, end)
        for provider_name in settings.PROVIDER_ENTITLEMENT_SEEDS
    }

    def history_start(provider_name: str) -> datetime:
        return provider_history_starts.get(provider_name, EPOCH_START)

    alpaca_start = history_start("alpaca")
    binance_start = history_start("binance")
    coinbase_start = history_start("coinbase")
    kraken_start = history_start("kraken")
    massive_start = history_start("massive")
    marketstack_start = history_start("marketstack")
    marketdata_app_start = history_start("marketdata_app")
    twelve_data_start = history_start("twelve_data")
    ibkr_start = history_start("ibkr")

    alpaca_cost = estimate_ohlcv_request_count(timeframe, alpaca_start, end)
    binance_cost = estimate_ohlcv_request_weight(timeframe, binance_start, end)
    coinbase_cost = estimate_coinbase_ohlcv_request_count(timeframe, coinbase_start, end)
    kraken_cost = estimate_kraken_ohlcv_request_count(timeframe, kraken_start, end)
    massive_cost = estimate_massive_ohlcv_request_count(timeframe, massive_start, end)
    marketstack_cost = estimate_marketstack_ohlcv_request_count(
        timeframe, marketstack_start, end
    )
    marketdata_app_cost = estimate_marketdata_app_ohlcv_credit_count(
        timeframe, marketdata_app_start, end
    )
    twelve_data_cost = estimate_twelve_data_ohlcv_request_count(
        timeframe, twelve_data_start, end
    )
    ibkr_cost = estimate_ibkr_ohlcv_request_count(timeframe, ibkr_start, end)
    operation_cost_overrides = {
        **({"alpaca": alpaca_cost} if alpaca_cost is not None else {}),
        **({"binance": binance_cost} if binance_cost is not None else {}),
        **({"coinbase": coinbase_cost} if coinbase_cost is not None else {}),
        **({"kraken": kraken_cost} if kraken_cost is not None else {}),
        **({"massive": massive_cost} if massive_cost is not None else {}),
        **({"marketstack": marketstack_cost} if marketstack_cost is not None else {}),
        **({"marketdata_app": marketdata_app_cost} if marketdata_app_cost is not None else {}),
        **({"twelve_data": twelve_data_cost} if twelve_data_cost is not None else {}),
        **({"ibkr": ibkr_cost} if ibkr_cost is not None else {}),
    }
    execution = await execute_provider_call(
        db,
        ProviderCapability.PRICE_HISTORY,
        f"bulk_fetch:{timeframe.value}",
        instrument_id=instrument.id,
        usage_identity=lambda provider_name: provider_symbol_for_instrument(instrument, provider_name),
        operation_cost_overrides=operation_cost_overrides or None,
        adjusted=adjusted,
        history_start=history_start,
        invoke=lambda provider, _provider_symbol: provider.fetch_ohlcv(
            provider_symbol_for_instrument(instrument, provider.name),
            timeframe,
            history_start(provider.name),
            end,
            adjusted=adjusted,
            instrument_id=instrument.id,
            data_source_id=0,
        ),
        response_items=lambda result: len(result),
        treat_empty_as_failure=False,
    )
    bars = _bars_through_end(execution.result, end)
    if not bars:
        await _touch_ohlcv_dataset_state(
            db,
            instrument,
            data_source_id=execution.data_source.id,
            timeframe=timeframe,
            adjusted=adjusted,
            bars=[],
        )
        await db.commit()
        return 0

    bars = await _attach_provider_series(
        db,
        instrument,
        timeframe,
        adjusted,
        execution,
        bars=bars,
    )
    existing_ts = await _existing_timestamps(db, instrument.id, timeframe, adjusted)

    new_bars: list[OHLCVBar] = []
    for bar in bars:
        ts_utc = _to_utc(bar.ts)
        if ts_utc in existing_ts:
            continue
        bar.instrument_id = instrument.id
        bar.data_source_id = execution.data_source.id
        bar.ts = ts_utc
        new_bars.append(bar)

    for bar in bars:
        bar.instrument_id = instrument.id
        bar.data_source_id = execution.data_source.id
        bar.ts = _to_utc(bar.ts)

    await _record_bar_observations(
        db,
        bars,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol_for_instrument(instrument, execution.provider_name),
    )
    await _touch_ohlcv_dataset_state(
        db,
        instrument,
        data_source_id=execution.data_source.id,
        timeframe=timeframe,
        adjusted=adjusted,
        bars=bars,
    )

    if new_bars:
        db.add_all(new_bars)
    await db.commit()

    return len(new_bars)


def _normalize_fetch_end(value: datetime | None) -> datetime:
    """Return a timezone-aware UTC provider bound for reproducible refreshes."""

    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bars_through_end(bars: list[Any], end: datetime) -> list[Any]:
    """Defensively remove provider rows beyond the requested evaluation end."""

    return [bar for bar in bars if _to_utc(bar.ts) <= end]


async def _existing_timestamps(
    db: AsyncSession, instrument_id: int, timeframe: Timeframe, adjusted: bool
) -> set[datetime]:
    stmt = select(OHLCVBar.ts).where(
        OHLCVBar.instrument_id == instrument_id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted == adjusted,
        _default_series_bar_condition(instrument_id, timeframe, adjusted),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {_to_utc(ts) for ts in rows}


def _to_utc(ts: Any) -> datetime:
    """Coerce any timestamp-like value to a timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return datetime.fromtimestamp(float(ts), tz=UTC)


def _is_intraday(tf: Timeframe) -> bool:
    """True for timeframes strictly finer than one day."""
    return tf in {
        Timeframe.M1,
        Timeframe.M5,
        Timeframe.M15,
        Timeframe.M30,
        Timeframe.H1,
        Timeframe.H2,
        Timeframe.H4,
        Timeframe.H12,
    }


async def _publish_progress(
    redis,
    instrument_id: int,
    status: str,
    timeframes: list[Timeframe],
    summary: dict,
) -> None:
    """Write current progress to Redis.  Silently ignored if Redis is unavailable."""
    if redis is None:
        return
    try:
        key = _REDIS_PROGRESS_KEY.format(instrument_id=instrument_id)
        payload = json.dumps(
            {
                "instrument_id": instrument_id,
                "status": status,  # "in_progress" | "complete"
                "timeframes": [tf.value for tf in timeframes],
                "results": summary,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        await redis.set(key, payload, ex=_REDIS_TTL_SECONDS)
    except Exception as e:
        logger.warning(
            "Could not write fetch progress to Redis: %s", bounded_redact_provider_message(e)
        )
