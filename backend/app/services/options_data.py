from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.bs_greeks import estimate_greeks
from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    OptionChainSnapshot,
    OptionQuotePoint,
)
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.providers.base import OptionContractRecord
from app.services.instrument_mastering import (
    _mark_field_provenance,
    ensure_instrument_type,
    register_provider_symbol,
)
from app.services.provider_runtime import execute_provider_call
from app.services.risk_free_rate import get_risk_free_rate


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _strike_label(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_option_symbol(
    underlying_symbol: str,
    expiry_date: date,
    right: str,
    strike: Decimal,
) -> str:
    right_code = "C" if right.lower().startswith("c") else "P"
    return f"{underlying_symbol.upper()} {expiry_date.isoformat()} {right_code} {_strike_label(strike)}"


def build_option_contract_key(
    underlying: Instrument,
    *,
    expiry_date: date,
    strike: Decimal,
    right: str,
    style: str,
    contract_size: Decimal | None,
    venue_code: str | None,
) -> str:
    underlying_key = underlying.primary_identifier_value or f"instrument:{underlying.id}"
    multiplier = contract_size or Decimal("100")
    return "|".join(
        [
            underlying_key,
            venue_code or "GLOBAL",
            expiry_date.isoformat(),
            _strike_label(strike),
            right.lower(),
            style.lower(),
            _strike_label(multiplier),
        ]
    )


def _snapshot_hash(records: list[OptionContractRecord], expiration: date) -> str:
    payload = [
        {
            "provider_symbol": record.provider_symbol,
            "expiry_date": expiration.isoformat(),
            "strike": str(record.strike),
            "right": record.right,
            "bid": str(record.bid) if record.bid is not None else None,
            "ask": str(record.ask) if record.ask is not None else None,
            "mark": str(record.mark) if record.mark is not None else None,
            "last_price": str(record.last_price) if record.last_price is not None else None,
            "volume": str(record.volume) if record.volume is not None else None,
            "open_interest": str(record.open_interest) if record.open_interest is not None else None,
            "implied_vol": str(record.implied_vol) if record.implied_vol is not None else None,
            "delta": str(record.delta) if record.delta is not None else None,
            "gamma": str(record.gamma) if record.gamma is not None else None,
            "theta": str(record.theta) if record.theta is not None else None,
            "vega": str(record.vega) if record.vega is not None else None,
            "rho": str(record.rho) if record.rho is not None else None,
        }
        for record in sorted(records, key=lambda item: item.provider_symbol)
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


async def _upsert_dataset_state(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int | None,
    dataset_type: str,
    dataset_key: str,
    status: DatasetStatus,
    observed_at: datetime | None,
    fetched_at: datetime | None,
    freshness_seconds: int,
    coverage_start: datetime | None = None,
    coverage_end: datetime | None = None,
    snapshot_hash: str | None = None,
    extra_data: dict | None = None,
) -> None:
    state = (
        await db.execute(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument_id,
                InstrumentDatasetState.data_source_id == data_source_id,
                InstrumentDatasetState.dataset_type == dataset_type,
                InstrumentDatasetState.dataset_key == dataset_key,
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = InstrumentDatasetState(
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            dataset_type=dataset_type,
            dataset_key=dataset_key,
        )
        db.add(state)
    state.status = status
    if coverage_start is not None:
        state.coverage_start = coverage_start
    if coverage_end is not None:
        state.coverage_end = coverage_end
    state.observed_at = observed_at
    state.fetched_at = fetched_at
    state.stale_after = (fetched_at or _now_utc()) + timedelta(seconds=freshness_seconds)
    state.snapshot_hash = snapshot_hash
    state.extra_data = extra_data


async def list_option_expirations(
    db: AsyncSession,
    underlying: Instrument,
    *,
    refresh: bool = False,
) -> list[date]:
    persisted_expirations = (
        await db.execute(
            select(distinct(OptionDetail.expiry_date))
            .where(OptionDetail.underlying_instrument_id == underlying.id)
            .order_by(OptionDetail.expiry_date)
        )
    ).scalars().all()
    if not refresh:
        fresh_states = (
            await db.execute(
                select(InstrumentDatasetState)
                .where(
                    InstrumentDatasetState.instrument_id == underlying.id,
                    InstrumentDatasetState.dataset_type == "option_expirations",
                    InstrumentDatasetState.dataset_key == "all",
                    InstrumentDatasetState.status == DatasetStatus.FRESH,
                    InstrumentDatasetState.stale_after.is_not(None),
                    InstrumentDatasetState.stale_after > _now_utc(),
                )
                .order_by(InstrumentDatasetState.observed_at.desc())
            )
        ).scalars().all()
        for state in fresh_states:
            payload_exps = (state.extra_data or {}).get("expirations")
            if isinstance(payload_exps, list) and payload_exps:
                parsed: list[date] = []
                for item in payload_exps:
                    try:
                        parsed.append(date.fromisoformat(str(item)))
                    except ValueError:
                        continue
                if parsed:
                    return sorted(set(parsed))
        if persisted_expirations:
            return persisted_expirations

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.OPTION_CHAIN,
            "list_option_expirations",
            instrument_id=underlying.id,
            invoke=lambda provider, _provider_symbol: provider.list_option_expirations(
                provider_symbol_for_instrument(underlying, provider.name)
            ),
            response_items=lambda result: len(result),
            treat_empty_as_failure=False,
        )
    except Exception:
        return persisted_expirations
    expirations = sorted(set(execution.result))
    await _upsert_dataset_state(
        db,
        instrument_id=underlying.id,
        data_source_id=execution.data_source.id,
        dataset_type="option_expirations",
        dataset_key="all",
        status=DatasetStatus.FRESH if expirations else DatasetStatus.PENDING,
        observed_at=_now_utc(),
        fetched_at=_now_utc(),
        freshness_seconds=execution.policy.freshness_seconds,
        extra_data={"expirations": [item.isoformat() for item in expirations]},
    )
    await db.flush()
    return expirations


async def ensure_option_contract(
    db: AsyncSession,
    *,
    underlying: Instrument,
    provider_name: str,
    contract: OptionContractRecord,
    observed_at: datetime,
) -> Instrument:
    option_type_id = await ensure_instrument_type(db, "Derivative", "Option")
    venue_code = None
    style = OptionStyle.AMERICAN
    contract_key = build_option_contract_key(
        underlying,
        expiry_date=contract.expiry_date,
        strike=contract.strike,
        right=contract.right,
        style=style.value,
        contract_size=contract.contract_size,
        venue_code=venue_code,
    )
    detail = (
        await db.execute(select(OptionDetail).where(OptionDetail.contract_key == contract_key))
    ).scalar_one_or_none()

    if detail is None:
        instrument = Instrument(
            symbol=_canonical_option_symbol(
                underlying.symbol,
                contract.expiry_date,
                contract.right,
                contract.strike,
            ),
            name=_canonical_option_symbol(
                underlying.symbol,
                contract.expiry_date,
                contract.right,
                contract.strike,
            ),
            description=f"{underlying.symbol} option contract",
            currency=contract.currency or underlying.currency,
            instrument_type_id=option_type_id,
            is_active=True,
        )
        db.add(instrument)
        await db.flush()
        detail = OptionDetail(
            instrument_id=instrument.id,
            underlying_instrument_id=underlying.id,
            right=OptionRight.CALL if contract.right.lower().startswith("c") else OptionRight.PUT,
            style=style,
            contract_key=contract_key,
            venue_code=venue_code,
            strike=contract.strike,
            expiry_date=contract.expiry_date,
            contract_size=contract.contract_size or Decimal("100"),
        )
        db.add(detail)
    else:
        instrument = await db.get(Instrument, detail.instrument_id)
        if instrument is None:
            raise RuntimeError(f"Option detail {detail.id} is missing its instrument row")

    instrument.currency = contract.currency or instrument.currency or underlying.currency
    detail.contract_key = contract_key
    detail.venue_code = venue_code
    detail.contract_size = contract.contract_size or detail.contract_size or Decimal("100")
    detail.implied_vol = contract.implied_vol or detail.implied_vol
    detail.delta = contract.delta or detail.delta
    detail.gamma = contract.gamma or detail.gamma
    detail.theta = contract.theta or detail.theta
    detail.vega = contract.vega or detail.vega
    detail.rho = contract.rho or detail.rho

    for field_name in ["implied_vol", "delta", "gamma", "theta", "vega", "rho"]:
        if getattr(detail, field_name, None) is not None:
            _mark_field_provenance(
                detail,
                field_name,
                source=provider_name,
                fetched_at=observed_at,
                observed_at=observed_at,
                provider_symbol=contract.provider_symbol,
                selection_reason="latest_option_snapshot",
            )

    await register_provider_symbol(
        db,
        instrument,
        provider_name,
        contract.provider_symbol,
        provider_instrument_type="OPTION",
        currency=contract.currency or underlying.currency,
        is_primary=True,
        extra_data={"underlying_symbol": underlying.symbol},
    )
    return instrument


async def sync_option_chain_snapshot(
    db: AsyncSession,
    underlying: Instrument,
    *,
    expiration: date,
    refresh: bool = False,
) -> OptionChainSnapshot | None:
    latest_snapshot = (
        await db.execute(
            select(OptionChainSnapshot)
            .where(
                OptionChainSnapshot.underlying_instrument_id == underlying.id,
                OptionChainSnapshot.expiration_date == expiration,
            )
            .order_by(OptionChainSnapshot.observed_at.desc())
        )
    ).scalars().first()
    if latest_snapshot is not None and not refresh:
        dataset_state = (
            await db.execute(
                select(InstrumentDatasetState).where(
                    InstrumentDatasetState.instrument_id == underlying.id,
                    InstrumentDatasetState.dataset_type == "option_chain",
                    InstrumentDatasetState.dataset_key == expiration.isoformat(),
                    InstrumentDatasetState.status == DatasetStatus.FRESH,
                    InstrumentDatasetState.stale_after.is_not(None),
                    InstrumentDatasetState.stale_after > _now_utc(),
                )
            )
        ).scalar_one_or_none()
        if dataset_state is not None:
            return latest_snapshot

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.OPTION_CHAIN,
            f"fetch_option_chain:{expiration.isoformat()}",
            instrument_id=underlying.id,
            invoke=lambda provider, _provider_symbol: provider.fetch_option_chain(
                provider_symbol_for_instrument(underlying, provider.name),
                expiration=expiration,
            ),
            response_items=lambda result: len(result),
            treat_empty_as_failure=False,
        )
    except Exception:
        return latest_snapshot
    contracts = execution.result
    if not contracts:
        await _upsert_dataset_state(
            db,
            instrument_id=underlying.id,
            data_source_id=execution.data_source.id,
            dataset_type="option_chain",
            dataset_key=expiration.isoformat(),
            status=DatasetStatus.PENDING,
            observed_at=_now_utc(),
            fetched_at=_now_utc(),
            freshness_seconds=execution.policy.freshness_seconds,
            extra_data={"provider": execution.provider_name, "contracts": 0},
        )
        await db.flush()
        return latest_snapshot

    observed_at = max((contract.observed_at for contract in contracts if contract.observed_at), default=_now_utc())
    snapshot_hash = _snapshot_hash(contracts, expiration)
    snapshot = (
        await db.execute(
            select(OptionChainSnapshot).where(
                OptionChainSnapshot.underlying_instrument_id == underlying.id,
                OptionChainSnapshot.data_source_id == execution.data_source.id,
                OptionChainSnapshot.expiration_date == expiration,
                OptionChainSnapshot.snapshot_hash == snapshot_hash,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = OptionChainSnapshot(
            underlying_instrument_id=underlying.id,
            data_source_id=execution.data_source.id,
            provider_symbol=provider_symbol_for_instrument(underlying, execution.provider_name),
            expiration_date=expiration,
            observed_at=observed_at,
            fetched_at=_now_utc(),
            snapshot_hash=snapshot_hash,
            raw_payload={"provider": execution.provider_name, "contract_count": len(contracts)},
        )
        db.add(snapshot)
        await db.flush()

    # Fetch spot and RFR once per expiration snapshot for greek estimation
    spot_row = (
        await db.execute(
            select(OHLCVBar.close)
            .where(OHLCVBar.instrument_id == underlying.id, OHLCVBar.timeframe == Timeframe.D1)
            .order_by(OHLCVBar.ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    spot_f: float | None = float(spot_row) if spot_row is not None else None
    rfr = await get_risk_free_rate(db)
    today = _now_utc().date()

    _ins = pg_insert(OptionQuotePoint)
    for contract in contracts:
        option_instrument = await ensure_option_contract(
            db,
            underlying=underlying,
            provider_name=execution.provider_name,
            contract=contract,
            observed_at=observed_at,
        )

        # Estimate missing greeks via Black-Scholes when provider didn't supply them
        delta = contract.delta
        gamma = contract.gamma
        extra_greeks = dict(contract.extra_greeks or {})
        if (delta is None or gamma is None) and contract.implied_vol is not None and spot_f is not None:
            tte = max(0.0, (contract.expiry_date - today).days / 365.25)
            if tte > 0:
                is_call = contract.right.lower().startswith("c")
                est_delta, est_gamma = estimate_greeks(
                    spot_f,
                    float(contract.strike),
                    tte,
                    float(contract.implied_vol),
                    rfr,
                    is_call=is_call,
                )
                if delta is None:
                    delta = Decimal(str(round(est_delta, 8)))
                if gamma is None:
                    gamma = Decimal(str(round(est_gamma, 8)))
                extra_greeks.update({"greeks_source": "bs_estimated", "rfr_used": rfr, "div_yield_used": 0.0})

        point_values = {
            "option_instrument_id": option_instrument.id,
            "snapshot_id": snapshot.id,
            "data_source_id": execution.data_source.id,
            "provider_symbol": contract.provider_symbol,
            "observed_at": contract.observed_at or observed_at,
            "bid": contract.bid,
            "ask": contract.ask,
            "mark": contract.mark,
            "last": contract.last_price,
            "volume": contract.volume,
            "open_interest": contract.open_interest,
            "implied_vol": contract.implied_vol,
            "delta": delta,
            "gamma": gamma,
            "theta": contract.theta,
            "vega": contract.vega,
            "rho": contract.rho,
            "extra_greeks": extra_greeks or None,
            "raw_payload": contract.raw_payload,
            "observation_hash": hashlib.sha256(
                json.dumps(contract.raw_payload or {}, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        }
        await db.execute(
            _ins.on_conflict_do_update(
                constraint="uq_option_quote_point_observed",
                set_={
                    "snapshot_id": _ins.excluded.snapshot_id,
                    "provider_symbol": _ins.excluded.provider_symbol,
                    "bid": _ins.excluded.bid,
                    "ask": _ins.excluded.ask,
                    "mark": _ins.excluded.mark,
                    "last": _ins.excluded.last,
                    "volume": _ins.excluded.volume,
                    "open_interest": _ins.excluded.open_interest,
                    "implied_vol": _ins.excluded.implied_vol,
                    # COALESCE: real provider greeks win; estimated values survive null re-ingestion
                    "delta": func.coalesce(_ins.excluded.delta, OptionQuotePoint.delta),
                    "gamma": func.coalesce(_ins.excluded.gamma, OptionQuotePoint.gamma),
                    "theta": _ins.excluded.theta,
                    "vega": _ins.excluded.vega,
                    "rho": _ins.excluded.rho,
                    "extra_greeks": _ins.excluded.extra_greeks,
                    "raw_payload": _ins.excluded.raw_payload,
                    "observation_hash": _ins.excluded.observation_hash,
                },
            ),
            [point_values],
        )

    await _upsert_dataset_state(
        db,
        instrument_id=underlying.id,
        data_source_id=execution.data_source.id,
        dataset_type="option_chain",
        dataset_key=expiration.isoformat(),
        status=DatasetStatus.FRESH,
        observed_at=observed_at,
        fetched_at=_now_utc(),
        freshness_seconds=execution.policy.freshness_seconds,
        extra_data={"provider": execution.provider_name, "contracts": len(contracts)},
    )
    await db.flush()
    return snapshot


async def get_option_chain_rows(
    db: AsyncSession,
    underlying: Instrument,
    *,
    expiration: date,
    refresh: bool = False,
) -> tuple[OptionChainSnapshot | None, list[dict]]:
    snapshot = await sync_option_chain_snapshot(db, underlying, expiration=expiration, refresh=refresh)
    if snapshot is None:
        return None, []

    rows = (
        await db.execute(
            select(OptionQuotePoint, Instrument, OptionDetail)
            .join(Instrument, Instrument.id == OptionQuotePoint.option_instrument_id)
            .join(OptionDetail, OptionDetail.instrument_id == Instrument.id)
            .where(OptionQuotePoint.snapshot_id == snapshot.id)
            .order_by(OptionDetail.right, OptionDetail.strike)
        )
    ).all()
    return snapshot, [
        {
            "instrument_id": instrument.id,
            "symbol": instrument.symbol,
            "name": instrument.name,
            "currency": instrument.currency,
            "right": detail.right.value,
            "style": detail.style.value,
            "strike": float(detail.strike),
            "expiry_date": detail.expiry_date,
            "contract_size": float(detail.contract_size) if detail.contract_size is not None else None,
            "contract_key": detail.contract_key,
            "bid": float(point.bid) if point.bid is not None else None,
            "ask": float(point.ask) if point.ask is not None else None,
            "mark": float(point.mark) if point.mark is not None else None,
            "last": float(point.last) if point.last is not None else None,
            "volume": float(point.volume) if point.volume is not None else None,
            "open_interest": float(point.open_interest) if point.open_interest is not None else None,
            "implied_vol": float(point.implied_vol) if point.implied_vol is not None else None,
            "delta": float(point.delta) if point.delta is not None else None,
            "gamma": float(point.gamma) if point.gamma is not None else None,
            "theta": float(point.theta) if point.theta is not None else None,
            "vega": float(point.vega) if point.vega is not None else None,
            "rho": float(point.rho) if point.rho is not None else None,
            "observed_at": point.observed_at,
            "provider_symbol": point.provider_symbol,
            "provenance": detail.field_provenance or {},
        }
        for point, instrument, detail in rows
    ]


async def get_option_contract_summary(db: AsyncSession, instrument_id: int) -> dict | None:
    row = (
        await db.execute(
            select(Instrument, OptionDetail)
            .join(OptionDetail, OptionDetail.instrument_id == Instrument.id)
            .where(Instrument.id == instrument_id)
        )
    ).first()
    if row is None:
        return None
    instrument, detail = row
    return {
        "id": instrument.id,
        "symbol": instrument.symbol,
        "name": instrument.name,
        "currency": instrument.currency,
        "contract_key": detail.contract_key,
        "right": detail.right.value,
        "style": detail.style.value,
        "strike": float(detail.strike),
        "expiry_date": detail.expiry_date,
        "contract_size": float(detail.contract_size) if detail.contract_size is not None else None,
        "underlying_instrument_id": detail.underlying_instrument_id,
        "provenance": detail.field_provenance or {},
    }


async def sync_option_quote_history(
    db: AsyncSession,
    option_instrument: Instrument,
    *,
    start: datetime,
    end: datetime,
    refresh: bool = False,
) -> None:
    dataset_key = "default"
    if not refresh:
        fresh_state = (
            await db.execute(
                select(InstrumentDatasetState).where(
                    InstrumentDatasetState.instrument_id == option_instrument.id,
                    InstrumentDatasetState.dataset_type == "option_quote_history",
                    InstrumentDatasetState.dataset_key == dataset_key,
                    InstrumentDatasetState.status == DatasetStatus.FRESH,
                    InstrumentDatasetState.stale_after.is_not(None),
                    InstrumentDatasetState.stale_after > _now_utc(),
                    InstrumentDatasetState.coverage_start.is_not(None),
                    InstrumentDatasetState.coverage_end.is_not(None),
                    InstrumentDatasetState.coverage_start <= start,
                    InstrumentDatasetState.coverage_end >= end,
                )
            )
        ).scalar_one_or_none()
        if fresh_state is not None:
            return

    try:
        execution = await execute_provider_call(
            db,
            ProviderCapability.OPTION_QUOTE_HISTORY,
            "fetch_option_quote_history",
            instrument_id=option_instrument.id,
            invoke=lambda provider, _provider_symbol: provider.fetch_option_quote_history(
                provider_symbol_for_instrument(option_instrument, provider.name),
                start=start,
                end=end,
            ),
            response_items=lambda result: len(result),
            treat_empty_as_failure=False,
        )
    except Exception:
        return

    points = execution.result
    fetched_at = _now_utc()
    if not points:
        await _upsert_dataset_state(
            db,
            instrument_id=option_instrument.id,
            data_source_id=execution.data_source.id,
            dataset_type="option_quote_history",
            dataset_key=dataset_key,
            status=DatasetStatus.PENDING,
            observed_at=fetched_at,
            fetched_at=fetched_at,
            freshness_seconds=execution.policy.freshness_seconds,
            coverage_start=start,
            coverage_end=end,
            extra_data={"provider": execution.provider_name, "points": 0},
        )
        await db.flush()
        return

    for point in points:
        raw_payload = point.raw_payload or {}
        observation_hash = hashlib.sha256(
            json.dumps(raw_payload or {
                "observed_at": point.observed_at.isoformat(),
                "bid": str(point.bid) if point.bid is not None else None,
                "ask": str(point.ask) if point.ask is not None else None,
                "mark": str(point.mark) if point.mark is not None else None,
                "last": str(point.last) if point.last is not None else None,
                "volume": str(point.volume) if point.volume is not None else None,
                "open_interest": str(point.open_interest) if point.open_interest is not None else None,
                "implied_vol": str(point.implied_vol) if point.implied_vol is not None else None,
                "delta": str(point.delta) if point.delta is not None else None,
                "gamma": str(point.gamma) if point.gamma is not None else None,
                "theta": str(point.theta) if point.theta is not None else None,
                "vega": str(point.vega) if point.vega is not None else None,
                "rho": str(point.rho) if point.rho is not None else None,
            }, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        _hist_ins = pg_insert(OptionQuotePoint)
        await db.execute(
            _hist_ins.on_conflict_do_update(
                constraint="uq_option_quote_point_observed",
                set_={
                    "snapshot_id": None,
                    "provider_symbol": _hist_ins.excluded.provider_symbol,
                    "bid": _hist_ins.excluded.bid,
                    "ask": _hist_ins.excluded.ask,
                    "mark": _hist_ins.excluded.mark,
                    "last": _hist_ins.excluded.last,
                    "volume": _hist_ins.excluded.volume,
                    "open_interest": _hist_ins.excluded.open_interest,
                    "implied_vol": _hist_ins.excluded.implied_vol,
                    "delta": func.coalesce(_hist_ins.excluded.delta, OptionQuotePoint.delta),
                    "gamma": func.coalesce(_hist_ins.excluded.gamma, OptionQuotePoint.gamma),
                    "theta": _hist_ins.excluded.theta,
                    "vega": _hist_ins.excluded.vega,
                    "rho": _hist_ins.excluded.rho,
                    "extra_greeks": _hist_ins.excluded.extra_greeks,
                    "raw_payload": _hist_ins.excluded.raw_payload,
                    "observation_hash": _hist_ins.excluded.observation_hash,
                },
            ),
            [
                {
                    "option_instrument_id": option_instrument.id,
                    "snapshot_id": None,
                    "data_source_id": execution.data_source.id,
                    "provider_symbol": point.provider_symbol,
                    "observed_at": point.observed_at,
                    "bid": point.bid,
                    "ask": point.ask,
                    "mark": point.mark,
                    "last": point.last,
                    "volume": point.volume,
                    "open_interest": point.open_interest,
                    "implied_vol": point.implied_vol,
                    "delta": point.delta,
                    "gamma": point.gamma,
                    "theta": point.theta,
                    "vega": point.vega,
                    "rho": point.rho,
                    "extra_greeks": point.extra_greeks,
                    "raw_payload": raw_payload,
                    "observation_hash": observation_hash,
                }
            ],
        )

    await _upsert_dataset_state(
        db,
        instrument_id=option_instrument.id,
        data_source_id=execution.data_source.id,
        dataset_type="option_quote_history",
        dataset_key=dataset_key,
        status=DatasetStatus.FRESH,
        observed_at=max(point.observed_at for point in points),
        fetched_at=fetched_at,
        freshness_seconds=execution.policy.freshness_seconds,
        coverage_start=start,
        coverage_end=end,
        extra_data={"provider": execution.provider_name, "points": len(points)},
    )
    await db.flush()


async def get_option_quote_history(
    db: AsyncSession,
    instrument_id: int,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    refresh: bool = False,
) -> list[dict]:
    option_instrument = await db.get(Instrument, instrument_id)
    if option_instrument is None:
        return []

    effective_start = start or (_now_utc() - timedelta(days=30))
    effective_end = end or _now_utc()
    await sync_option_quote_history(
        db,
        option_instrument,
        start=effective_start,
        end=effective_end,
        refresh=refresh,
    )

    stmt = (
        select(OptionQuotePoint)
        .where(OptionQuotePoint.option_instrument_id == instrument_id)
        .order_by(OptionQuotePoint.observed_at)
    )
    if effective_start is not None:
        stmt = stmt.where(OptionQuotePoint.observed_at >= effective_start)
    if effective_end is not None:
        stmt = stmt.where(OptionQuotePoint.observed_at <= effective_end)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "observed_at": row.observed_at,
            "bid": float(row.bid) if row.bid is not None else None,
            "ask": float(row.ask) if row.ask is not None else None,
            "mark": float(row.mark) if row.mark is not None else None,
            "last": float(row.last) if row.last is not None else None,
            "volume": float(row.volume) if row.volume is not None else None,
            "open_interest": float(row.open_interest) if row.open_interest is not None else None,
            "implied_vol": float(row.implied_vol) if row.implied_vol is not None else None,
            "delta": float(row.delta) if row.delta is not None else None,
            "gamma": float(row.gamma) if row.gamma is not None else None,
            "theta": float(row.theta) if row.theta is not None else None,
            "vega": float(row.vega) if row.vega is not None else None,
            "rho": float(row.rho) if row.rho is not None else None,
            "provider_symbol": row.provider_symbol,
        }
        for row in rows
    ]
