"""Canonical identity bootstrap for the TC2000-style US workstation.

The top-down taxonomy intentionally creates relationships only; it must not
invent instruments.  A fresh deployment nevertheless needs the small,
well-defined workstation universe (benchmarks, sector ETF proxies, and the
first constituent used by the default drill-down) before provider discovery
has completed.  This module owns that boundary.

The registry is an identity bootstrap, not a market-data fixture:

* every field is labelled as curated registry provenance;
* no price, volume, membership, exchange, or holdings facts are fabricated;
* Nasdaq is registered only as a provider-symbol binding for its public EOD
  price-history adapter;
* bars and holdings continue to come from their normal provider services.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.etf_holdings import ensure_etf_profile
from app.services.etf_holdings_refresh import bootstrap_etf_holdings_profile
from app.services.instrument_mastering import ensure_instrument_type, register_provider_symbol
from app.services.market_data import fetch_ohlcv
from app.services.top_down_taxonomy import (
    _BENCHMARKS,
    _INDUSTRY_PROXY_CANDIDATES,
    _SECTORS,
    BENCHMARK_FAMILY_REGISTRY,
    benchmark_family_proxy_symbols,
    seed_top_down_taxonomy,
)

CORE_WORKSTATION_REGISTRY = "curated_workstation_registry_v1"

_BENCHMARK_PROXY_NAMES = {
    str(mapping["symbol"]): f"{mapping.get('label') or symbol}"
    for family in BENCHMARK_FAMILY_REGISTRY
    for role in ("cap_weight", "equal_weight", "value", "growth")
    for mapping in [family.get(role) or {}]
    if (symbol := mapping.get("symbol"))
}

# These are tradable/reference identities needed by the immutable US Top Down
# layout.  SPX remains a logical index identity in taxonomy provenance; it is
# deliberately not created as a tradable instrument here.
CORE_WORKSTATION_INSTRUMENTS: tuple[tuple[str, str, str], ...] = (
    *tuple((symbol, name, "ETF") for symbol, name, _ in _BENCHMARKS),
    *tuple(
        (symbol, _BENCHMARK_PROXY_NAMES.get(symbol, f"{symbol} benchmark/style proxy ETF"), "ETF")
        for symbol in benchmark_family_proxy_symbols()
        if symbol not in {item[0] for item in _BENCHMARKS}
    ),
    *tuple((symbol, name, "ETF") for symbol, name in _SECTORS),
    # Curated industry proxies are part of the supported drill-down universe.
    # They are identities only here; membership remains valid only after the
    # normal holdings adapter proves point-in-time holdings and classification.
    *tuple(
        (symbol, f"{symbol} industry proxy ETF", "ETF")
        for symbol in dict.fromkeys(
            candidate
            for candidates in _INDUSTRY_PROXY_CANDIDATES.values()
            for candidate in candidates
        )
    ),
    ("NVDA", "NVIDIA Corporation", "EQUITY"),
)


async def ensure_core_workstation_identities(db: AsyncSession) -> dict:
    """Materialise the curated core identities and attach the taxonomy.

    The operation is idempotent and safe to run at every API start.  Existing
    canonical names/provenance are never overwritten with registry values;
    the registry is retained as an additional audit entry instead.  The
    provider-symbol binding carries no exchange claim because the Nasdaq
    public endpoint is a US-listed EOD source, not a consolidated exchange
    security master.
    """

    observed_at = datetime.now(UTC)
    by_type = {
        "ETF": await ensure_instrument_type(db, "Equity", "ETF"),
        "EQUITY": await ensure_instrument_type(db, "Equity", "Stock"),
    }
    symbols = tuple(symbol for symbol, _, _ in CORE_WORKSTATION_INSTRUMENTS)
    existing = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }
    created = 0
    provider_bindings = 0
    etf_profiles = 0

    for symbol, name, quote_type in CORE_WORKSTATION_INSTRUMENTS:
        instrument = existing.get(symbol)
        if instrument is None:
            instrument = Instrument(
                symbol=symbol,
                name=name,
                currency="USD",
                instrument_type_id=by_type[quote_type],
                is_active=True,
                field_provenance={
                    "symbol": {
                        "source": CORE_WORKSTATION_REGISTRY,
                        "observed_at": observed_at.isoformat(),
                        "selection_reason": "required by immutable US Top Down layout",
                        "provider_claim": "curated identity only; not an exchange listing assertion",
                    },
                    "name": {
                        "source": CORE_WORKSTATION_REGISTRY,
                        "observed_at": observed_at.isoformat(),
                        "selection_reason": "human-readable product label",
                    },
                },
            )
            db.add(instrument)
            await db.flush()
            existing[symbol] = instrument
            created += 1
        else:
            provenance = dict(instrument.field_provenance or {})
            registry = dict(provenance.get("workstation_registry") or {})
            registry.update(
                {
                    "source": CORE_WORKSTATION_REGISTRY,
                    "observed_at": observed_at.isoformat(),
                    "selection_reason": "required by immutable US Top Down layout",
                }
            )
            provenance["workstation_registry"] = registry
            instrument.field_provenance = provenance
            instrument.is_active = True
            if instrument.instrument_type_id != by_type[quote_type]:
                instrument.instrument_type_id = by_type[quote_type]

        binding_exists = (
            await db.execute(
                select(InstrumentProviderSymbol.id)
                .where(
                    InstrumentProviderSymbol.instrument_id == instrument.id,
                    InstrumentProviderSymbol.provider_symbol == symbol,
                )
                .order_by(InstrumentProviderSymbol.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        await register_provider_symbol(
            db,
            instrument,
            "nasdaq",
            symbol,
            provider_instrument_type=quote_type,
            currency="USD",
            is_primary=False,
            extra_data={
                "source_role": "public_us_eod_price_history",
                "identity_bootstrap": CORE_WORKSTATION_REGISTRY,
                "exchange_claim": "not asserted",
            },
        )
        if binding_exists is None:
            provider_bindings += 1

        if quote_type == "ETF":
            profile_exists = (
                await db.execute(
                    select(ETFProfile).where(ETFProfile.instrument_id == instrument.id)
                )
            ).scalar_one_or_none()
            existing_legal_metadata = profile_exists.legal_metadata if profile_exists else {}
            legal_metadata = {
                **(existing_legal_metadata or {}),
                "identity_bootstrap": CORE_WORKSTATION_REGISTRY,
                "holdings_membership_status": "not_loaded",
            }
            await ensure_etf_profile(
                db,
                instrument,
                legal_metadata=legal_metadata,
            )
            if profile_exists is None:
                etf_profiles += 1

    await seed_top_down_taxonomy(db)
    await db.flush()
    return {
        "registry": CORE_WORKSTATION_REGISTRY,
        "created": created,
        "total": len(CORE_WORKSTATION_INSTRUMENTS),
        "provider_bindings": provider_bindings,
        "etf_profiles": etf_profiles,
        "data_status": "identity_only_until_provider_history_and_holdings_load",
    }


async def queue_core_family_member_history(db: AsyncSession, redis) -> dict:
    """Queue member history after provider-backed core ETF snapshots are committed."""

    if redis is None:
        return {"status": "not_queued", "reason": "Redis worker queue unavailable"}

    from app.services.benchmark_family_history import plan_benchmark_family_history_refresh

    plan = await plan_benchmark_family_history_refresh(db)
    queued = already_queued = 0
    for instrument_id in plan["instrument_ids"]:
        job = await redis.enqueue_job(
            "task_bulk_fetch_instrument",
            instrument_id,
            plan["timeframes"],
            _job_id=(
                f"benchmark-family-bootstrap-history:{instrument_id}:"
                f"{','.join(plan['timeframes'])}"
            ),
        )
        if job is None:
            already_queued += 1
        else:
            queued += 1
    return {
        "status": "queued",
        "queued": queued,
        "already_queued": already_queued,
        "available_instrument_count": plan["available_instrument_count"],
        "selected_instrument_count": plan["selected_instrument_count"],
        "limited": plan["limited"],
        "timeframes": plan["timeframes"],
        "legs": plan["legs"],
    }


async def bootstrap_core_workstation_data(db: AsyncSession, redis=None) -> dict:
    """Hydrate missing core bars and holdings without inventing data.

    This is intentionally a worker task rather than API-startup work.  Each
    symbol is attempted independently, bounded by a timeout, and failures are
    returned as structured per-symbol status.  The existing provider runtime
    decides whether Alpaca/Nasdaq/other entitled sources may answer; no direct
    provider fallback is introduced here.
    """

    if settings.E2E_SEED_MARKET_DATA:
        return {
            "skipped": True,
            "reason": "controlled fixture mode owns workstation data",
        }

    identities = await ensure_core_workstation_identities(db)
    # Identity creation is a durable prerequisite for provider hydration. A
    # later per-symbol rollback must not erase the canonical workstation
    # universe that was just materialised, otherwise all following symbols are
    # silently skipped and a retry can restart the same failure loop.
    await db.commit()
    symbols = tuple(symbol for symbol, _, _ in CORE_WORKSTATION_INSTRUMENTS)
    # Provider calls can rollback this shared session on an individual symbol
    # failure. SQLAlchemy expires loaded ORM attributes on rollback; retaining
    # those instances across iterations then causes MissingGreenlet when the
    # next symbol reads ``instrument.id``. Keep primitive IDs and reload each
    # instrument after every provider attempt instead.
    instrument_ids = {
        symbol.upper(): instrument_id
        for instrument_id, symbol in (
            await db.execute(
                select(Instrument.id, Instrument.symbol).where(Instrument.symbol.in_(symbols))
            )
        ).all()
    }
    history: dict[str, dict] = {}
    holdings: dict[str, dict] = {}
    # A worker bootstrap must be bounded and non-disruptive. Historical backfill
    # remains the responsibility of scheduled/provider maintenance jobs; the
    # startup sweep only hydrates the recent workstation window needed to make
    # the default layout usable without monopolising the API host.
    history_start = datetime.now(UTC) - timedelta(
        days=settings.CORE_WORKSTATION_BOOTSTRAP_LOOKBACK_DAYS
    )

    for symbol in symbols:
        instrument_id = instrument_ids[symbol]
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            history[symbol] = {"status": "error", "error_type": "missing_identity"}
            continue
        existing_bars = (
            await db.execute(
                select(func.count(OHLCVBar.id)).where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                )
            )
        ).scalar_one()
        if existing_bars:
            history[symbol] = {"status": "ready", "bars": int(existing_bars)}
            continue
        try:
            bars = await asyncio.wait_for(
                fetch_ohlcv(db, instrument, Timeframe.D1, history_start),
                timeout=settings.CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS,
            )
            history[symbol] = {"status": "loaded" if bars else "unavailable", "bars": len(bars)}
        except Exception as exc:  # noqa: BLE001 - preserve per-symbol readiness state
            await db.rollback()
            history[symbol] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc)[:300],
            }

    for symbol, _, quote_type in CORE_WORKSTATION_INSTRUMENTS:
        if quote_type != "ETF":
            continue
        instrument_id = instrument_ids[symbol]
        instrument = await db.get(Instrument, instrument_id)
        if instrument is None:
            holdings[symbol] = {"status": "error", "error_type": "missing_identity"}
            continue
        snapshot_count = (
            await db.execute(
                select(func.count(ETFHoldingsSnapshot.id))
                .join(ETFProfile, ETFProfile.id == ETFHoldingsSnapshot.etf_profile_id)
                .where(
                    ETFProfile.instrument_id == instrument.id,
                    ETFHoldingsSnapshot.provenance != "controlled_fixture",
                    ETFHoldingsSnapshot.source_provider != "e2e_reference",
                )
            )
        ).scalar_one()
        if snapshot_count:
            holdings[symbol] = {"status": "ready", "snapshots": int(snapshot_count)}
            continue
        try:
            result = await asyncio.wait_for(
                bootstrap_etf_holdings_profile(db, symbol=symbol, name=instrument.name),
                timeout=settings.CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS,
            )
            holdings[symbol] = {
                "status": "loaded" if result.refresh_succeeded else "unavailable",
                "refresh_attempted": result.refresh_attempted,
                "message": result.message,
            }
        except Exception as exc:  # noqa: BLE001 - preserve per-ETF readiness state
            await db.rollback()
            holdings[symbol] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc)[:300],
            }

    # Once the provider-backed ETF snapshots above are committed, queue the same
    # canonical constituent history jobs used by the explicit maintenance routes.
    # This keeps member bars out of interactive reads while making the opt-in core
    # bootstrap actually useful for the locked top-down universes.
    await db.commit()
    try:
        family_history = await queue_core_family_member_history(db, redis)
    except Exception as exc:  # noqa: BLE001 - retain bounded bootstrap outcome
        family_history = {
            "status": "queue_error",
            "message": str(exc)[:300],
        }
    return {
        "skipped": False,
        "identities": identities,
        "history": history,
        "holdings": holdings,
        "family_history": family_history,
    }
