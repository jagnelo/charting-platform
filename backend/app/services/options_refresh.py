"""Bounded scheduled refresh of option chains and active-contract quote history.

Option contracts are materialised as ordinary ``Instrument`` rows (type
"Option") by ``sync_option_chain_snapshot``, but nothing used to revisit them:
the durable refresh queue only schedules stock/ETF-style OHLCV work, and the
contract rows would otherwise be swept into the discovered-universe D1 planner
(see ``exclude_option_contracts`` there). This module is the dedicated driver.

Design constraints (all enforced here, not left to the caller):

* Work is selected, never enumerated: at most ``max_underlyings`` underlyings
  and ``max_contracts`` contracts per *calendar day* (UTC). The daily ledger is
  derived from ``InstrumentDatasetState.fetched_at``, so a re-run, a crash
  resume or a second worker cannot multiply provider volume, and a completed
  day is a no-op.
* Selection is rotation by staleness (never-fetched first, then oldest), so a
  small daily cap still covers the whole candidate set over time.
* Only active contracts expire-date >= today and inside the configured horizon
  are refreshed; expired contracts are deactivated and never selected.
* All provider I/O goes through ``options_data`` which uses
  ``execute_provider_call``; quota admission, the ledger and response-priced
  cost bounds (``MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS``) stay authoritative.
  A provider rate-limit/quota signal stops the whole run immediately.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.asset_class import InstrumentType
from app.models.instrument import Instrument, OptionDetail
from app.models.provider_observation import InstrumentDatasetState
from app.models.watchlist import WatchlistItem
from app.providers.errors import ProviderNotConfiguredError, ProviderRateLimitError
from app.services.options_data import (
    list_option_expirations,
    sync_option_chain_snapshot,
    sync_option_quote_history,
)
from app.services.provider_runtime import ProviderQuotaUnknownError

logger = logging.getLogger(__name__)

EXPIRATIONS_DATASET = "option_expirations"
QUOTE_HISTORY_DATASET = "option_quote_history"
# Stock/ETF identities are the only underlyings with listed US options that the
# catalogue models; indices/futures options need their own provider mapping.
OPTION_UNDERLYING_TYPES = ("Stock", "ETF")
_MAX_CONSECUTIVE_FAILURES = 3


def _day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _last_fetch_subquery(dataset_type: str):
    return (
        select(
            InstrumentDatasetState.instrument_id.label("instrument_id"),
            func.max(InstrumentDatasetState.fetched_at).label("last_fetched"),
        )
        .where(InstrumentDatasetState.dataset_type == dataset_type)
        .group_by(InstrumentDatasetState.instrument_id)
        .subquery()
    )


async def _fetched_since(db: AsyncSession, dataset_type: str, since: datetime) -> int:
    return int(
        (
            await db.execute(
                select(func.count(func.distinct(InstrumentDatasetState.instrument_id))).where(
                    InstrumentDatasetState.dataset_type == dataset_type,
                    InstrumentDatasetState.fetched_at >= since,
                )
            )
        ).scalar_one()
        or 0
    )


async def deactivate_expired_option_contracts(db: AsyncSession, *, today: date) -> int:
    """Deactivate contracts past expiry so no sweep or refresh picks them up."""

    expired = (
        select(OptionDetail.instrument_id).where(OptionDetail.expiry_date < today).scalar_subquery()
    )
    result = await db.execute(
        update(Instrument)
        .where(Instrument.id.in_(expired), Instrument.is_active.is_(True))
        .values(is_active=False)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


async def select_option_underlyings(
    db: AsyncSession, *, limit: int, now: datetime, core_symbols: set[str] | frozenset[str]
) -> list[Instrument]:
    """Pick the stalest eligible underlyings that have not been fetched today.

    Eligible: active, non-synthetic Stock/ETF that is a core workstation
    identity, sits on a saved watchlist, or already has persisted contracts.
    """

    if limit <= 0:
        return []
    last = _last_fetch_subquery(EXPIRATIONS_DATASET)
    watched = select(WatchlistItem.instrument_id).scalar_subquery()
    has_contracts = exists().where(OptionDetail.underlying_instrument_id == Instrument.id)
    day_start = _day_start(now)
    query = (
        select(Instrument)
        .join(InstrumentType, InstrumentType.id == Instrument.instrument_type_id)
        .outerjoin(last, last.c.instrument_id == Instrument.id)
        .where(
            Instrument.is_active.is_(True),
            Instrument.is_synthetic.is_(False),
            InstrumentType.name.in_(OPTION_UNDERLYING_TYPES),
            (Instrument.symbol.in_(sorted(core_symbols)))
            | Instrument.id.in_(watched)
            | has_contracts,
            (last.c.last_fetched.is_(None)) | (last.c.last_fetched < day_start),
        )
        .order_by(
            case((last.c.last_fetched.is_(None), 0), else_=1),
            last.c.last_fetched.asc(),
            Instrument.id.asc(),
        )
        .limit(limit)
    )
    return list((await db.execute(query)).scalars().all())


async def select_active_option_contracts(
    db: AsyncSession, *, limit: int, now: datetime, horizon_days: int
) -> list[Instrument]:
    """Pick the stalest non-expired contracts inside the horizon, not fetched today."""

    if limit <= 0:
        return []
    today = now.astimezone(UTC).date()
    last = _last_fetch_subquery(QUOTE_HISTORY_DATASET)
    query = (
        select(Instrument)
        .join(OptionDetail, OptionDetail.instrument_id == Instrument.id)
        .outerjoin(last, last.c.instrument_id == Instrument.id)
        .where(
            Instrument.is_active.is_(True),
            OptionDetail.expiry_date >= today,
            OptionDetail.expiry_date <= today + timedelta(days=max(0, horizon_days)),
            (last.c.last_fetched.is_(None)) | (last.c.last_fetched < _day_start(now)),
        )
        .order_by(
            case((last.c.last_fetched.is_(None), 0), else_=1),
            last.c.last_fetched.asc(),
            OptionDetail.expiry_date.asc(),
            Instrument.id.asc(),
        )
        .limit(limit)
    )
    return list((await db.execute(query)).scalars().all())


def _is_quota_stop(exc: BaseException) -> bool:
    return isinstance(exc, ProviderRateLimitError | ProviderQuotaUnknownError)


async def refresh_options_data(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    max_underlyings: int | None = None,
    expirations_per_underlying: int | None = None,
    max_contracts: int | None = None,
    quote_lookback_days: int | None = None,
    horizon_days: int | None = None,
    time_budget_seconds: float | None = None,
    core_symbols: set[str] | frozenset[str] | None = None,
) -> dict:
    """Run one bounded options pass; returns counters, never raises on provider errors."""

    from app.services.workstation_bootstrap import CORE_WORKSTATION_INSTRUMENTS

    current = now or datetime.now(UTC)
    day_start = _day_start(current)
    cap_underlyings = max(
        0, settings.OPTIONS_REFRESH_MAX_UNDERLYINGS if max_underlyings is None else max_underlyings
    )
    per_underlying = max(
        1,
        settings.OPTIONS_REFRESH_EXPIRATIONS_PER_UNDERLYING
        if expirations_per_underlying is None
        else expirations_per_underlying,
    )
    cap_contracts = max(
        0, settings.OPTIONS_REFRESH_MAX_CONTRACTS if max_contracts is None else max_contracts
    )
    lookback = max(
        1,
        settings.OPTIONS_REFRESH_QUOTE_LOOKBACK_DAYS
        if quote_lookback_days is None
        else quote_lookback_days,
    )
    horizon = max(
        1, settings.OPTION_CHAIN_REFRESH_HORIZON_DAYS if horizon_days is None else horizon_days
    )
    budget = (
        settings.OPTIONS_REFRESH_TIME_BUDGET_SECONDS
        if time_budget_seconds is None
        else time_budget_seconds
    )
    deadline = time.monotonic() + float(budget)
    symbols = (
        core_symbols
        if core_symbols is not None
        else {symbol.upper() for symbol, _name, _kind in CORE_WORKSTATION_INSTRUMENTS}
    )
    today = current.astimezone(UTC).date()

    summary: dict = {
        "deactivated_expired": 0,
        "underlyings_selected": 0,
        "underlyings_refreshed": 0,
        "chains_synced": 0,
        "contracts_selected": 0,
        "contracts_refreshed": 0,
        "failed": 0,
        "stopped": None,
    }
    summary["deactivated_expired"] = await deactivate_expired_option_contracts(db, today=today)
    await db.commit()

    failures = 0

    def _out_of_time() -> bool:
        return time.monotonic() >= deadline

    # Phase 1: expirations + nearest active chains for the stalest underlyings.
    remaining = cap_underlyings - await _fetched_since(db, EXPIRATIONS_DATASET, day_start)
    underlyings = await select_option_underlyings(
        db, limit=remaining, now=current, core_symbols=symbols
    )
    summary["underlyings_selected"] = len(underlyings)
    for underlying in underlyings:
        if _out_of_time():
            summary["stopped"] = "time_budget"
            break
        try:
            expirations = await list_option_expirations(db, underlying, refresh=True)
            window_end = today + timedelta(days=horizon)
            active = sorted(e for e in set(expirations) if today <= e <= window_end)
            for expiration in active[:per_underlying]:
                if _out_of_time():
                    break
                if await sync_option_chain_snapshot(db, underlying, expiration=expiration):
                    summary["chains_synced"] += 1
            await db.commit()
            summary["underlyings_refreshed"] += 1
            failures = 0
        except ProviderNotConfiguredError:
            await db.rollback()
            summary["stopped"] = "provider_not_configured"
            break
        except Exception as exc:  # noqa: BLE001 - one bad underlying must not stop the pass
            await db.rollback()
            if _is_quota_stop(exc):
                summary["stopped"] = "quota"
                logger.warning("Options refresh stopped by provider quota: %s", exc)
                break
            summary["failed"] += 1
            failures += 1
            logger.warning("Options chain refresh failed for %s: %s", underlying.symbol, exc)
            if failures >= _MAX_CONSECUTIVE_FAILURES:
                summary["stopped"] = "consecutive_failures"
                break

    # Phase 2: daily quote/greeks/OI history for stalest active contracts.
    if summary["stopped"] in (None, "time_budget") and not _out_of_time():
        remaining = cap_contracts - await _fetched_since(db, QUOTE_HISTORY_DATASET, day_start)
        contracts = await select_active_option_contracts(
            db, limit=remaining, now=current, horizon_days=horizon
        )
        summary["contracts_selected"] = len(contracts)
        failures = 0
        for contract in contracts:
            if _out_of_time():
                summary["stopped"] = "time_budget"
                break
            try:
                await sync_option_quote_history(
                    db, contract, start=current - timedelta(days=lookback), end=current
                )
                await db.commit()
                summary["contracts_refreshed"] += 1
                failures = 0
            except ProviderNotConfiguredError:
                await db.rollback()
                summary["stopped"] = "provider_not_configured"
                break
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                if _is_quota_stop(exc):
                    summary["stopped"] = "quota"
                    logger.warning("Options quote refresh stopped by provider quota: %s", exc)
                    break
                summary["failed"] += 1
                failures += 1
                logger.warning("Option quote refresh failed for %s: %s", contract.symbol, exc)
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    summary["stopped"] = "consecutive_failures"
                    break
    return summary
