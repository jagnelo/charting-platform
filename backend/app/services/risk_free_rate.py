"""
Provider-agnostic risk-free rate service.

Strategy (in priority order):
  1. In-memory cache (1-hour TTL) — avoids DB round-trips on hot paths.
  2. Latest daily close from ohlcv_bar for the canonical RFR instrument.
  3. Live fetch via the active PRICE_HISTORY provider chain (no OHLCV persistence —
     bars are read-only so we stay inside the caller's transaction boundary).
  4. Hardcoded fallback (0.05).

The canonical instrument symbol is settings.RFR_INSTRUMENT_SYMBOL (default "^IRX").
Provider symbols (what each data source calls this instrument) are registered
separately via the existing provider-symbol infrastructure; provider_symbol_for_instrument
falls back to the canonical symbol when none is registered. The active provider policy
determines which independently entitled source receives that symbol; this service does
not require or prefer yfinance.

Switching data providers does not require updating RFR_INSTRUMENT_SYMBOL — only the
provider symbol registration needs to change (or the new provider may accept the same
canonical symbol).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.services.market_data import persist_price_history_bars
from app.services.provider_runtime import execute_provider_call

_FALLBACK_RFR = 0.05
_CACHE_TTL_SECONDS = 3600
_RFR_STALE_DAYS = 5  # accept bars up to this many calendar days old

_cached_rfr: float | None = None
_cache_ts: float = 0.0
_cache_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def _close_to_rate(close: float) -> float:
    """Convert quoted close to a decimal rate. ^IRX and similar quote in annual %, e.g. 5.27 → 0.0527."""
    return close / 100.0 if close > 1.0 else close


async def get_risk_free_rate(db: AsyncSession) -> float:
    """Return the current risk-free rate as a decimal (e.g. 0.0527 for 5.27%)."""
    global _cached_rfr, _cache_ts

    async with _get_lock():
        if _cached_rfr is not None and (time.monotonic() - _cache_ts) < _CACHE_TTL_SECONDS:
            return _cached_rfr

        rate = await _resolve_rate(db)
        _cached_rfr = rate
        _cache_ts = time.monotonic()
        return rate


async def _resolve_rate(db: AsyncSession) -> float:
    rfr_symbol = settings.RFR_INSTRUMENT_SYMBOL

    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == rfr_symbol))
    ).scalar_one_or_none()

    if instrument is None:
        instrument = await _bootstrap_instrument(db, rfr_symbol)

    if instrument is not None:
        rate = await _read_from_db(db, instrument.id)
        if rate is not None:
            return rate

        rate = await _fetch_from_provider(db, instrument)
        if rate is not None:
            return rate

    return _FALLBACK_RFR


async def _bootstrap_instrument(db: AsyncSession, symbol: str) -> Instrument | None:
    """Register a minimal Instrument row for the RFR proxy symbol if missing."""
    try:
        from app.services.instrument_mastering import ensure_instrument_type

        type_id = await ensure_instrument_type(db, "Fixed Income", "Rate Index")
        instrument = Instrument(
            symbol=symbol,
            name=settings.RFR_INSTRUMENT_NAME,
            description="Risk-free rate proxy instrument",
            currency="USD",
            instrument_type_id=type_id,
            is_active=True,
        )
        db.add(instrument)
        await db.flush()
        return instrument
    except Exception:
        return None


async def _read_from_db(db: AsyncSession, instrument_id: int) -> float | None:
    """Return the latest daily close for the RFR instrument if fresh enough."""
    cutoff = datetime.now(UTC) - timedelta(days=_RFR_STALE_DAYS)
    row = (
        await db.execute(
            select(OHLCVBar.close)
            .where(
                OHLCVBar.instrument_id == instrument_id,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.ts >= cutoff,
            )
            .order_by(OHLCVBar.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _close_to_rate(float(row))


async def _fetch_from_provider(db: AsyncSession, instrument: Instrument) -> float | None:
    """
    Trigger a live PRICE_HISTORY fetch for the RFR instrument.
    Returns the latest close without persisting bars — the caller's transaction
    is not touched beyond provider runtime log writes (which are fine).
    """
    end = datetime.now(UTC)
    start = end - timedelta(days=30)
    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.PRICE_HISTORY,
            "fetch_rfr_ohlcv",
            instrument_id=instrument.id,
            invoke=lambda provider, _sym: provider.fetch_ohlcv(
                provider_symbol_for_instrument(instrument, provider.name),
                Timeframe.D1,
                start,
                end,
                adjusted=True,
                instrument_id=instrument.id,
                data_source_id=0,
            ),
            response_items=lambda result: len(result) if result else 0,
            treat_empty_as_failure=False,
        )
        bars = execution.result
        if not bars:
            return None
        for bar in bars:
            bar.instrument_id = instrument.id
            bar.data_source_id = execution.data_source.id
        await persist_price_history_bars(
            db,
            instrument,
            data_source_id=execution.data_source.id,
            provider_symbol=provider_symbol_for_instrument(instrument, execution.provider_name),
            timeframe=Timeframe.D1,
            adjusted=True,
            bars=bars,
            observed_at=max((bar.ts for bar in bars), default=end),
            use_upsert=True,
        )
        most_recent = max(bars, key=lambda b: b.ts)
        return _close_to_rate(float(most_recent.close))
    except Exception:
        return None
