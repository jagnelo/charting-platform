"""Durable owner-scoped preparation requests over the shared refresh queue."""

from __future__ import annotations

import hashlib
import importlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFProfile
from app.models.instrument import Instrument
from app.models.market_data_foundation import MarketRefreshJob, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentProfileSnapshot
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.models.synthetic_constituent import SyntheticConstituent
from app.models.workstation import MarketGroup, MarketGroupMember
from app.schemas.data_preparation import (
    DataEnsureRequest,
    DataEnsureResponse,
    PreparationCoveredRange,
    PreparationDataset,
    PreparationDependencyResponse,
)
from app.services.market_refresh_queue import _acquire_enqueue_lock, enqueue_refresh_job

_TRACKING_CAPABILITY = "data_preparation_request"
_OWNER_TRACKING_ROLE = "owner_request_tracking"
_SYSTEM_TRACKING_ROLE = "system_maintenance_tracking"
_TRACKING_ROLES = frozenset({_OWNER_TRACKING_ROLE, _SYSTEM_TRACKING_ROLE})
_PRIORITY = {"visible": 10, "default": 50, "background": 100}
_DATASET_ENQUEUE_ORDER = {
    PreparationDataset.IDENTITY: 0,
    PreparationDataset.PROFILE: 1,
    PreparationDataset.HISTORY: 2,
    PreparationDataset.HOLDINGS: 3,
    PreparationDataset.FUNDAMENTALS: 4,
}
_PENDING_PREPARATION_JOB_STATUSES = frozenset({"queued", "leased", "retry", "deferred"})


@dataclass(frozen=True)
class _InstrumentPlan:
    instrument_ids: list[int]
    unresolved_symbols: list[str]
    reason_code: str | None = None


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _verified_coverage_ranges(
    jobs: list[MarketRefreshJob], *, timeframe: str
) -> list[PreparationCoveredRange]:
    """Project only completed, contiguous ranges from one unchanged data scope."""

    candidates: list[tuple[datetime, datetime, PreparationCoveredRange, tuple]] = []
    for job in jobs:
        if job.status != "completed" or job.timeframe != timeframe:
            continue
        summary = job.result_summary or {}
        chunk_status = summary.get("chunk_coverage_status") or summary.get("data_status")
        if chunk_status != "ready" or int(summary.get("bars_observed") or 0) <= 0:
            continue
        scopes = summary.get("coverage_scopes") or []
        if len(scopes) != 1:
            continue
        scope = scopes[0]
        required = (
            "covered_start",
            "covered_end",
            "requested_start",
            "requested_end",
        )
        if (
            any(not summary.get(key) for key in required)
            or not scope.get("adjustment_basis")
            or not scope.get("adjustment_version")
        ):
            continue
        requested_start = _as_utc(datetime.fromisoformat(summary["requested_start"]))
        requested_end = _as_utc(datetime.fromisoformat(summary["requested_end"]))
        covered = PreparationCoveredRange(
            start_at=_as_utc(datetime.fromisoformat(summary["covered_start"])),
            end_at=_as_utc(datetime.fromisoformat(summary["covered_end"])),
            data_source_id=scope.get("data_source_id"),
            market_series_id=scope.get("market_series_id"),
            adjustment_basis=str(scope["adjustment_basis"]),
            adjustment_version=str(scope["adjustment_version"]),
            is_adjusted=bool(scope.get("is_adjusted", False)),
        )
        lineage = (
            covered.data_source_id,
            covered.market_series_id,
            covered.adjustment_basis,
            covered.adjustment_version,
            covered.is_adjusted,
        )
        candidates.append((requested_start, requested_end, covered, lineage))

    candidates.sort(key=lambda item: item[0])
    merged: list[tuple[datetime, datetime, PreparationCoveredRange, tuple]] = []
    for requested_start, requested_end, covered, lineage in candidates:
        if (
            merged
            and merged[-1][3] == lineage
            and requested_start <= merged[-1][1] + timedelta(microseconds=1)
        ):
            prior_start, prior_end, prior_covered, prior_lineage = merged[-1]
            merged[-1] = (
                prior_start,
                max(prior_end, requested_end),
                PreparationCoveredRange(
                    start_at=min(prior_covered.start_at, covered.start_at),
                    end_at=max(prior_covered.end_at, covered.end_at),
                    data_source_id=prior_covered.data_source_id,
                    market_series_id=prior_covered.market_series_id,
                    adjustment_basis=prior_covered.adjustment_basis,
                    adjustment_version=prior_covered.adjustment_version,
                    is_adjusted=prior_covered.is_adjusted,
                ),
                prior_lineage,
            )
        else:
            merged.append((requested_start, requested_end, covered, lineage))
    return [item[2] for item in merged]


async def _persisted_derived_coverage_ranges(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: Timeframe,
    adjusted: bool,
    requested_start: datetime | None,
    requested_end: datetime | None,
) -> list[PreparationCoveredRange]:
    """Read the current selected D1-derived series, including later rematerialization."""
    from app.services.market_data import _coverage_calendar
    from app.services.ohlcv_coverage import missing_range_slices

    default_d1 = await db.scalar(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == instrument_id,
            MarketSeriesDefault.timeframe == Timeframe.D1.value,
            MarketSeriesDefault.is_adjusted.is_(adjusted),
        )
    )
    instrument = await db.get(Instrument, instrument_id)
    if instrument is None:
        return []
    calendar = _coverage_calendar(instrument)
    source_series_id = default_d1.market_series_id if default_d1 is not None else None
    series_rows = list(
        (
            await db.execute(
                select(MarketSeries).where(
                    MarketSeries.instrument_id == instrument_id,
                    MarketSeries.timeframe == timeframe.value,
                    MarketSeries.is_active.is_(True),
                )
            )
        ).scalars()
    )
    ranges: list[PreparationCoveredRange] = []
    for series in series_rows:
        provenance = series.provenance or {}
        if provenance.get("derived_from_timeframe") != Timeframe.D1.value:
            continue
        linked_source = provenance.get("derived_from_market_series_id")
        if source_series_id is not None and linked_source != source_series_id:
            continue
        statement = select(OHLCVBar).where(
            OHLCVBar.instrument_id == instrument_id,
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.market_series_id == series.id,
            OHLCVBar.is_adjusted.is_(adjusted),
        )
        if requested_start is not None:
            statement = statement.where(OHLCVBar.ts >= requested_start)
        if requested_end is not None:
            statement = statement.where(OHLCVBar.ts <= requested_end)
        bars = list((await db.execute(statement.order_by(OHLCVBar.ts))).scalars())
        if not bars:
            continue
        start = _as_utc(requested_start) if requested_start else _as_utc(bars[0].ts)
        end = _as_utc(requested_end) if requested_end else _as_utc(bars[-1].ts)
        gaps = missing_range_slices(bars, timeframe, start, end, calendar=calendar)
        timestamps = [_as_utc(bar.ts) for bar in bars]
        previous = timestamps[0]
        segment_timestamps = [timestamps[0]]
        for current in timestamps[1:]:
            separates = any(
                previous < gap_start and current > gap_end for gap_start, gap_end in gaps
            )
            if separates:
                ranges.append(
                    PreparationCoveredRange(
                        start_at=segment_timestamps[0],
                        end_at=segment_timestamps[-1],
                        data_source_id=series.data_source_id,
                        market_series_id=series.id,
                        adjustment_basis=str(
                            getattr(series.adjustment_basis, "value", series.adjustment_basis)
                        ),
                        adjustment_version=series.adjustment_version,
                        is_adjusted=adjusted,
                    )
                )
                segment_timestamps = []
            segment_timestamps.append(current)
            previous = current
        ranges.append(
            PreparationCoveredRange(
                start_at=segment_timestamps[0],
                end_at=segment_timestamps[-1],
                data_source_id=series.data_source_id,
                market_series_id=series.id,
                adjustment_basis=str(
                    getattr(series.adjustment_basis, "value", series.adjustment_basis)
                ),
                adjustment_version=series.adjustment_version,
                is_adjusted=adjusted,
            )
        )
    return sorted(ranges, key=lambda item: (item.start_at, item.market_series_id or 0))


async def _resolve_symbol(db: AsyncSession, symbol: str) -> tuple[int | None, str | None]:
    rows = list(
        (
            await db.execute(
                select(Instrument.id).where(
                    Instrument.symbol == symbol,
                    Instrument.is_active.is_(True),
                    Instrument.is_synthetic.is_(False),
                )
            )
        ).scalars()
    )
    if len(rows) == 1:
        return int(rows[0]), None
    if len(rows) > 1:
        return None, "selection_required"
    return None, "identity_not_resolved"


async def _resolve_requested_instruments(
    db: AsyncSession, request: DataEnsureRequest
) -> _InstrumentPlan:
    target = request.target
    ids: list[int] = []
    unresolved_symbols: list[str] = []
    group: MarketGroup | None = None

    async def include_symbol(symbol: str) -> str | None:
        instrument_id, reason = await _resolve_symbol(db, symbol)
        if instrument_id is not None:
            ids.append(instrument_id)
        elif reason == "identity_not_resolved":
            unresolved_symbols.append(symbol.upper())
        return reason

    if target.kind == "instrument":
        if target.instrument_id is not None:
            row = await db.get(Instrument, target.instrument_id)
            if row is None or not row.is_active:
                return _InstrumentPlan([], [], "instrument_not_found")
            ids.append(row.id)
        elif target.symbol:
            reason = await include_symbol(target.symbol)
            if reason not in {None, "identity_not_resolved"}:
                return _InstrumentPlan(list(dict.fromkeys(ids)), [], reason)
    else:
        group_key = target.group_key if target.kind == "market_group" else target.family_key
        group = (
            await db.execute(select(MarketGroup).where(MarketGroup.stable_key == group_key))
        ).scalar_one_or_none()
        if group is None:
            return _InstrumentPlan([], [], "group_not_found")
        if target.kind == "family" and group.group_type != "benchmark_family":
            return _InstrumentPlan([], [], "family_not_found")
        ids.extend(
            int(value)
            for value in (
                await db.execute(
                    select(MarketGroupMember.instrument_id)
                    .join(Instrument, Instrument.id == MarketGroupMember.instrument_id)
                    .where(
                        MarketGroupMember.market_group_id == group.id,
                        Instrument.is_active.is_(True),
                    )
                    .order_by(MarketGroupMember.position, MarketGroupMember.instrument_id)
                )
            ).scalars()
        )

    if request.analysis and request.analysis.kind == "ratio":
        for leg in request.analysis.legs or []:
            if leg.instrument_id is not None:
                row = await db.get(Instrument, leg.instrument_id)
                if row is None or not row.is_active:
                    return _InstrumentPlan(list(dict.fromkeys(ids)), [], "ratio_leg_not_found")
                ids.append(row.id)
            elif leg.symbol:
                reason = await include_symbol(leg.symbol)
                if reason not in {None, "identity_not_resolved"}:
                    return _InstrumentPlan(list(dict.fromkeys(ids)), [], reason)

    if request.analysis and request.analysis.kind == "rrg":
        benchmark_symbol = request.analysis.benchmark_symbol
        if benchmark_symbol is None and target.kind == "family":
            mappings = (group.provenance or {}).get("proxy_mappings") or {}
            cap_weight = mappings.get("cap_weight") or {}
            benchmark_symbol = cap_weight.get("symbol")
        if benchmark_symbol:
            reason = await include_symbol(benchmark_symbol)
            if reason not in {None, "identity_not_resolved"}:
                return _InstrumentPlan(list(dict.fromkeys(ids)), [], reason)

    # Synthetic instruments depend on every canonical constituent. Do not
    # create a constituent or infer one from the synthetic expression here.
    for instrument_id in list(dict.fromkeys(ids)):
        ids.extend(
            int(value)
            for value in (
                await db.execute(
                    select(SyntheticConstituent.constituent_instrument_id).where(
                        SyntheticConstituent.synthetic_instrument_id == instrument_id
                    )
                )
            ).scalars()
        )
    return _InstrumentPlan(list(dict.fromkeys(ids)), list(dict.fromkeys(unresolved_symbols)), None)


async def _instrument_is_etf(db: AsyncSession, instrument_id: int) -> bool:
    profile_id = (
        await db.execute(
            select(ETFProfile.id).where(ETFProfile.instrument_id == instrument_id).limit(1)
        )
    ).scalar_one_or_none()
    if profile_id is not None:
        return True
    names = (
        await db.execute(
            select(InstrumentType.name, AssetClass.name)
            .join(AssetClass, AssetClass.id == InstrumentType.asset_class_id)
            .join(Instrument, Instrument.instrument_type_id == InstrumentType.id)
            .where(Instrument.id == instrument_id)
        )
    ).one_or_none()
    if names is None:
        return False
    instrument_type, asset_class = (
        str(value or "").strip().casefold().replace("-", "_").replace(" ", "_") for value in names
    )
    # Explicit ETF type is enough to plan the dataset.  The actual issuer
    # handler still owns profile/identity checks before any holdings fetch.
    return instrument_type in {"etf", "exchange_traded_fund"} or (
        instrument_type == "exchange_traded_vehicle"
        and asset_class == "exchange_traded_product"
        and profile_id is not None
    )


async def _default_datasets(
    db: AsyncSession, instrument_ids: list[int]
) -> list[PreparationDataset]:
    datasets = [
        PreparationDataset.IDENTITY,
        PreparationDataset.PROFILE,
        PreparationDataset.HISTORY,
    ]
    if any([await _instrument_is_etf(db, instrument_id) for instrument_id in instrument_ids]):
        datasets.append(PreparationDataset.HOLDINGS)
    return datasets


def _profile_payload_has_field(provider_name: str, payload: dict, field_name: str) -> bool:
    extra = payload.get("extra") if isinstance(payload, dict) else None
    extra = extra if isinstance(extra, dict) else {}
    direct = payload.get(field_name) if isinstance(payload, dict) else None
    if direct is None:
        direct = extra.get(field_name)
    if isinstance(direct, str) and direct.strip():
        return True
    if field_name == "industry" and provider_name.strip().lower() == "massive":
        # Massive's SIC description is an actual source field. It can satisfy
        # an industry request only with its matching SIC code and is labelled
        # SEC_SIC during profile reconciliation; it is never treated as GICS.
        sic_code = extra.get("sic_code")
        return bool(
            isinstance(sic_code, str | int)
            and not isinstance(sic_code, bool)
            and str(sic_code).strip()
            and isinstance(extra.get("sic_description"), str)
            and extra.get("sic_description", "").strip()
        )
    return False


async def _profile_is_fresh(
    db: AsyncSession,
    instrument_id: int,
    *,
    now: datetime,
    required_profile_fields: list[str] | tuple[str, ...] = (),
) -> bool:
    rows = (
        await db.execute(
            select(
                InstrumentProfileSnapshot.fetched_at,
                InstrumentProfileSnapshot.payload,
                DataSource.name,
                ProviderPolicy.freshness_seconds,
            )
            .join(
                ProviderPolicy,
                ProviderPolicy.data_source_id == InstrumentProfileSnapshot.data_source_id,
            )
            .join(DataSource, DataSource.id == InstrumentProfileSnapshot.data_source_id)
            .where(
                InstrumentProfileSnapshot.instrument_id == instrument_id,
                ProviderPolicy.capability == ProviderCapability.INSTRUMENT_METADATA,
                ProviderPolicy.is_enabled.is_(True),
            )
            .order_by(InstrumentProfileSnapshot.fetched_at.desc())
        )
    ).all()
    required = tuple(str(field).strip().lower() for field in required_profile_fields)
    for fetched_at, payload, provider_name, freshness_seconds in rows:
        if fetched_at is None or not freshness_seconds:
            continue
        observed = fetched_at if fetched_at.tzinfo else fetched_at.replace(tzinfo=UTC)
        payload = payload if isinstance(payload, dict) else {}
        has_fields = all(
            _profile_payload_has_field(provider_name, payload, field) for field in required
        )
        if has_fields and now - observed.astimezone(UTC) <= timedelta(
            seconds=int(freshness_seconds)
        ):
            return True
    return False


def _etf_holdings_preparer():
    """Load the released ETF queue hook only when its module is installed."""
    module = importlib.import_module("app.services.etf_holdings_preparation")
    return getattr(module, "prepare_etf_holdings", None)


async def _append_parent_ref(db: AsyncSession, job: MarketRefreshJob, ref: dict) -> None:
    payload = deepcopy(job.metadata_payload or {})
    child = deepcopy(payload.get("data_preparation_child") or {})
    refs = list(child.get("parent_refs") or [])
    if ref not in refs:
        refs.append(ref)
    child["parent_refs"] = refs
    payload["data_preparation_child"] = child
    job.metadata_payload = payload
    await db.flush()


async def _existing_parent_refs(db: AsyncSession, request_key: str) -> list[dict]:
    existing = (
        await db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key)
        )
    ).scalar_one_or_none()
    if existing is None:
        return []
    child = (existing.metadata_payload or {}).get("data_preparation_child") or {}
    return list(child.get("parent_refs") or [])


async def _lock_parent_for_update(db: AsyncSession, parent_id: int) -> MarketRefreshJob | None:
    """Serialize parent-graph writes and refresh any identity-map copy first."""

    await _acquire_enqueue_lock(db, f"data-preparation-parent:{parent_id}")
    result = await db.execute(
        select(MarketRefreshJob)
        .where(MarketRefreshJob.id == parent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _dataset_initial_state(
    db: AsyncSession,
    instrument_id: int,
    dataset: PreparationDataset,
    *,
    now: datetime,
    required_profile_fields: list[str] | tuple[str, ...] = (),
) -> tuple[str, str | None]:
    instrument = await db.get(Instrument, instrument_id)
    if instrument is None:
        return "unavailable", "instrument_not_found"
    if dataset is PreparationDataset.IDENTITY:
        if instrument.identity_status == "resolved" and instrument.domain_key:
            return "ready", None
        return "unavailable", "canonical_identity_unqualified"
    if dataset is PreparationDataset.PROFILE:
        if await _profile_is_fresh(
            db,
            instrument_id,
            now=now,
            required_profile_fields=required_profile_fields,
        ):
            return "ready", None
        return "waiting", "profile_refresh_pending"
    if dataset is PreparationDataset.HOLDINGS:
        if not await _instrument_is_etf(db, instrument_id):
            return "unavailable", "not_applicable"
        if _etf_holdings_preparer() is None:
            return "unavailable", "etf_preparation_handler_not_registered"
        return "queued", None
    if dataset is PreparationDataset.FUNDAMENTALS:
        return "unavailable", "fundamentals_preparation_handler_unavailable"
    return "queued", None


async def _enqueue_identity_profile_job(
    db: AsyncSession,
    *,
    parent_job_id: int,
    request_id: str,
    symbol: str,
    instrument_id: int | None,
    refresh_profile: bool = False,
    required_profile_fields: list[str] | tuple[str, ...] = (),
    owner_user_id: int | None,
    priority: int,
    now: datetime,
) -> MarketRefreshJob:
    # Identity/profile work is shared by canonical target and freshness scope;
    # every owner request remains separately tracked in parent_refs.
    key = "prep-identity:" + _digest(
        [
            symbol.upper(),
            instrument_id,
            refresh_profile,
            sorted(set(required_profile_fields)),
            now.strftime("%Y-%m-%dT%H"),
        ]
    )
    await _acquire_enqueue_lock(db, key)
    prior_refs = await _existing_parent_refs(db, key)
    job = await enqueue_refresh_job(
        db,
        request_key=key,
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        instrument_id=instrument_id,
        priority=priority,
        metadata_payload={
            "data_preparation_child": {
                "kind": "identity_profile",
                "symbol": symbol.upper(),
                "instrument_id": instrument_id,
                "refresh_profile": refresh_profile,
                "required_profile_fields": sorted(set(required_profile_fields)),
                "parent_refs": prior_refs,
            }
        },
        now=now,
        preserve_deferred_deadline=True,
    )
    for ref in [
        *prior_refs,
        {"parent_job_id": parent_job_id, "owner_user_id": owner_user_id, "request_id": request_id},
    ]:
        await _append_parent_ref(db, job, ref)
    return job


async def _enqueue_etf_holdings_job(
    db: AsyncSession,
    *,
    parent_job_id: int,
    request_id: str,
    dependency_id: str,
    instrument_id: int,
    request: DataEnsureRequest,
    priority: int,
    now: datetime,
) -> MarketRefreshJob:
    freshness_scope = now.strftime("%Y-%m-%dT%H")
    request_key = "prep-holdings:" + _digest([instrument_id, freshness_scope])
    await _acquire_enqueue_lock(db, request_key)
    prior_refs = await _existing_parent_refs(db, request_key)
    job = await enqueue_refresh_job(
        db,
        request_key=request_key,
        capability="etf_holdings_preparation",
        instrument_id=instrument_id,
        timeframe=Timeframe.D1.value,
        priority=priority,
        metadata_payload={
            "data_preparation_child": {
                "kind": "etf_holdings",
                "instrument_id": instrument_id,
                "request_id": f"data-preparation-holdings:{instrument_id}:{freshness_scope}",
                "dependency_id": f"shared-holdings:{instrument_id}:{freshness_scope}",
                "freshness_scope": freshness_scope,
                "parent_refs": prior_refs,
            }
        },
        now=now,
        preserve_deferred_deadline=True,
    )
    for ref in [
        *prior_refs,
        {"parent_job_id": parent_job_id, "request_id": request_id, "dependency_id": dependency_id},
    ]:
        await _append_parent_ref(db, job, ref)
    return job


def _history_request_key(
    instrument_id: int,
    timeframe: Timeframe,
    adjusted: bool,
    start_at: datetime | None,
    end_at: datetime | None,
    *,
    refresh_bucket: str,
) -> str:
    return "prep-history:" + _digest(
        [instrument_id, timeframe.value, adjusted, start_at, end_at, refresh_bucket]
    )


def _analysis_required_start(request: DataEnsureRequest, *, now: datetime) -> datetime | None:
    """Return a scheduling floor for the first useful analysis window.

    This controls queue priority only; actual coverage remains determined by
    persisted bars and the provider's reviewed history bounds.
    """
    if request.analysis is None:
        return None
    count = request.analysis.required_raw_bars
    timeframe = request.timeframe
    if timeframe is Timeframe.MN:
        month_index = now.year * 12 + now.month - 1 - (count - 1)
        year, month_zero = divmod(month_index, 12)
        return now.replace(
            year=year, month=month_zero + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    if timeframe is Timeframe.W1:
        return now - timedelta(weeks=count - 1)
    if timeframe is Timeframe.D1:
        return now - timedelta(days=count - 1)
    from app.models.ohlcv import TIMEFRAME_SECONDS

    return now - timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * (count - 1))


async def _enqueue_history_dependency(
    db: AsyncSession,
    *,
    parent_job_id: int,
    request_id: str,
    dependency_id: str,
    instrument_id: int,
    request: DataEnsureRequest,
    priority: int,
    timeframe: Timeframe,
    wait_for_job_ids: list[int] | None = None,
    derived_only: bool = False,
    now: datetime,
) -> MarketRefreshJob:
    range_mode = "deepest_admitted" if request.start_at is None else "bounded"
    refresh_bucket = (
        now.strftime("%Y-%m-%dT%H")
        if request.end_at is None and request.start_at is None
        else "fixed"
    )
    request_key = _history_request_key(
        instrument_id,
        timeframe,
        request.adjusted,
        request.start_at,
        request.end_at,
        refresh_bucket=refresh_bucket,
    )
    await _acquire_enqueue_lock(db, request_key)
    prior_refs = await _existing_parent_refs(db, request_key)
    existing_job = (
        await db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key)
        )
    ).scalar_one_or_none()
    existing_child = (
        (existing_job.metadata_payload or {}).get("data_preparation_child") or {}
        if existing_job is not None
        else {}
    )
    job = await enqueue_refresh_job(
        db,
        request_key=request_key,
        capability="price_history",
        instrument_id=instrument_id,
        timeframe=timeframe.value,
        start_at=request.start_at,
        end_at=request.end_at,
        priority=priority,
        metadata_payload={
            "data_preparation_child": {
                "dataset": PreparationDataset.HISTORY.value,
                "instrument_id": instrument_id,
                "adjusted": request.adjusted,
                "range_mode": range_mode,
                "range_start": request.start_at.isoformat() if request.start_at else None,
                "range_end": request.end_at.isoformat() if request.end_at else None,
                "analysis_required_start": (
                    request.start_at.isoformat()
                    if request.start_at is not None
                    else (
                        _analysis_required_start(request, now=request.end_at or now).isoformat()
                        if request.analysis is not None
                        else None
                    )
                ),
                "derive_coarse_timeframes": (
                    timeframe is Timeframe.D1 and request.timeframe in {Timeframe.W1, Timeframe.MN}
                ),
                # If a visible exact-range request promotes a queued automatic
                # chunk, retain that chunk's feed pin rather than silently
                # changing source identity during deduplication.
                "source_provider": existing_child.get("source_provider"),
                "wait_for_job_ids": wait_for_job_ids or [],
                "derived_only": derived_only,
                "parent_refs": [
                    *prior_refs,
                    {"parent_job_id": parent_job_id, "dependency_id": dependency_id},
                ],
            }
        },
        now=now,
        preserve_deferred_deadline=True,
    )
    job_payload = deepcopy(job.metadata_payload or {})
    child_payload = deepcopy(job_payload.get("data_preparation_child") or {})
    refs = list(child_payload.get("parent_refs") or prior_refs)
    ref = {"parent_job_id": parent_job_id, "dependency_id": dependency_id}
    if ref not in refs:
        refs.append(ref)
    child_payload["parent_refs"] = refs
    job_payload["data_preparation_child"] = child_payload
    job.metadata_payload = job_payload
    await db.flush()
    return job


async def create_data_preparation_request(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    request: DataEnsureRequest,
    idempotency_key: str | None = None,
    priority: str = "visible",
    system_maintenance: bool = False,
    now: datetime | None = None,
) -> MarketRefreshJob:
    """Persist owner or internal maintenance work without provider I/O."""

    if system_maintenance != (owner_user_id is None):
        raise ValueError("system maintenance requests must not have an owner user id")

    now = _as_utc(now or datetime.now(UTC))
    normalized = request.model_dump(mode="json")
    fingerprint = _digest(normalized)
    request_id = str(uuid4())
    idempotency_hash = _digest(idempotency_key.strip()) if idempotency_key else None
    request_key = (
        f"data-preparation:{'maintenance' if system_maintenance else owner_user_id}:{idempotency_hash}"
        if idempotency_hash
        else f"data-preparation:{request_id}"
    )
    tracking_role = _SYSTEM_TRACKING_ROLE if system_maintenance else _OWNER_TRACKING_ROLE
    await _acquire_enqueue_lock(db, request_key)
    existing = (
        await db.execute(
            select(MarketRefreshJob).where(MarketRefreshJob.request_key == request_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        prior = (existing.metadata_payload or {}).get("data_preparation") or {}
        if (
            prior.get("owner_user_id") != owner_user_id
            or prior.get("role") != tracking_role
            or prior.get("fingerprint") != fingerprint
        ):
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        return existing

    instrument_plan = await _resolve_requested_instruments(db, request)
    instrument_ids = instrument_plan.instrument_ids
    unresolved_symbols = instrument_plan.unresolved_symbols
    resolution_reason = instrument_plan.reason_code
    datasets = request.datasets or await _default_datasets(db, instrument_ids)
    required_profile_fields = (
        request.required_profile_fields if PreparationDataset.PROFILE in datasets else []
    )
    parent = MarketRefreshJob(
        request_key=request_key,
        capability=_TRACKING_CAPABILITY,
        priority=_PRIORITY.get(priority, _PRIORITY["visible"]),
        status="tracking",
        attempts=0,
        next_attempt_at=now,
        metadata_payload={
            "data_preparation": {
                "role": tracking_role,
                "owner_user_id": owner_user_id,
                "request_id": request_id,
                "fingerprint": fingerprint,
                "normalized_request": normalized,
                "target": normalized["target"],
                "status": "waiting" if resolution_reason else "queued",
                "reason_code": resolution_reason,
                "version": 1,
                "last_progress_at": now.isoformat(),
                "dependencies": [],
            }
        },
    )
    db.add(parent)
    await db.flush()

    if resolution_reason:
        parent_data = deepcopy((parent.metadata_payload or {})["data_preparation"])
        parent_data["status"] = (
            "waiting"
            if resolution_reason in {"selection_required", "identity_not_resolved"}
            else "unavailable"
        )
        parent.metadata_payload = {"data_preparation": parent_data}
        await db.flush()
        return parent

    dependencies: list[dict] = []
    # Every transaction acquires shared child locks in one global order.
    # The request's ratio-leg order stays in normalized_request; only lock
    # acquisition is sorted to avoid opposite-leg PostgreSQL deadlocks.
    for symbol in sorted(set(unresolved_symbols), key=str.upper):
        identity_job = await _enqueue_identity_profile_job(
            db,
            parent_job_id=parent.id,
            request_id=request_id,
            symbol=symbol,
            instrument_id=None,
            required_profile_fields=required_profile_fields,
            owner_user_id=owner_user_id,
            priority=parent.priority,
            now=now,
        )
        identity_dependency_id = str(uuid4())
        dependencies.append(
            {
                "dependency_id": identity_dependency_id,
                "depends_on": [],
                "instrument_id": None,
                "symbol": symbol,
                "dataset": PreparationDataset.IDENTITY.value,
                "status": "queued",
                "reason_code": None,
                "requested_start": None,
                "requested_end": None,
                "covered_start": None,
                "covered_end": None,
                "retry_at": None,
                "job_ids": [identity_job.id],
                "updated_at": now.isoformat(),
            }
        )
        if PreparationDataset.PROFILE in datasets:
            dependencies.append(
                {
                    "dependency_id": str(uuid4()),
                    "depends_on": [identity_dependency_id],
                    "instrument_id": None,
                    "symbol": symbol,
                    "dataset": PreparationDataset.PROFILE.value,
                    "status": "queued",
                    "reason_code": None,
                    "requested_start": None,
                    "requested_end": None,
                    "covered_start": None,
                    "covered_end": None,
                    "retry_at": None,
                    "job_ids": [identity_job.id],
                    "updated_at": now.isoformat(),
                }
            )
        if PreparationDataset.HISTORY in datasets:
            dependencies.append(
                {
                    "dependency_id": str(uuid4()),
                    "depends_on": [identity_dependency_id],
                    "instrument_id": None,
                    "symbol": symbol,
                    "dataset": PreparationDataset.HISTORY.value,
                    "status": "waiting",
                    "reason_code": "identity_dependency_pending",
                    "requested_start": request.start_at.isoformat() if request.start_at else None,
                    "requested_end": request.end_at.isoformat() if request.end_at else None,
                    "covered_start": None,
                    "covered_end": None,
                    "retry_at": None,
                    "job_ids": [],
                    "updated_at": now.isoformat(),
                }
            )

    ordered_datasets = sorted(datasets, key=lambda item: _DATASET_ENQUEUE_ORDER[item])
    for instrument_id in sorted(set(instrument_ids)):
        instrument = await db.get(Instrument, instrument_id)
        identity_job = None
        identity_is_qualified = bool(
            instrument is not None
            and instrument.identity_status == "resolved"
            and instrument.domain_key
            and instrument.primary_identifier_type not in {None, "internal", "cik"}
            and instrument.primary_identifier_value
        )
        profile_is_fresh = (
            await _profile_is_fresh(
                db,
                instrument_id,
                now=now,
                required_profile_fields=required_profile_fields,
            )
            if instrument is not None
            else False
        )
        if instrument is not None and (
            not identity_is_qualified
            or PreparationDataset.PROFILE in datasets
            and not profile_is_fresh
        ):
            identity_job = await _enqueue_identity_profile_job(
                db,
                parent_job_id=parent.id,
                request_id=request_id,
                symbol=instrument.symbol,
                instrument_id=instrument_id,
                refresh_profile=PreparationDataset.PROFILE in datasets and not profile_is_fresh,
                required_profile_fields=required_profile_fields,
                owner_user_id=owner_user_id,
                priority=parent.priority,
                now=now,
            )
        for dataset in ordered_datasets:
            dependency_id = str(uuid4())
            current_status, reason = await _dataset_initial_state(
                db,
                instrument_id,
                dataset,
                now=now,
                required_profile_fields=required_profile_fields,
            )
            status = current_status
            job_ids: list[int] = []
            if identity_job and dataset in {
                PreparationDataset.IDENTITY,
                PreparationDataset.PROFILE,
            }:
                status, reason = "queued", None
                job_ids.append(identity_job.id)
            dependency = {
                "dependency_id": dependency_id,
                "depends_on": [],
                "instrument_id": instrument_id,
                "symbol": instrument.symbol if instrument is not None else None,
                "dataset": dataset.value,
                "status": status,
                "reason_code": reason,
                "requested_start": request.start_at.isoformat() if request.start_at else None,
                "requested_end": request.end_at.isoformat() if request.end_at else None,
                "covered_start": None,
                "covered_end": None,
                "retry_at": None,
                "job_ids": job_ids,
                "updated_at": now.isoformat(),
            }
            if dataset is PreparationDataset.HISTORY:
                warmup_job: MarketRefreshJob | None = None
                prerequisite_job_ids = [identity_job.id] if identity_job else []
                if request.timeframe in {Timeframe.W1, Timeframe.MN}:
                    warmup_job = await _enqueue_history_dependency(
                        db,
                        parent_job_id=parent.id,
                        request_id=request_id,
                        dependency_id=dependency_id,
                        instrument_id=instrument_id,
                        request=request,
                        priority=parent.priority,
                        timeframe=Timeframe.D1,
                        wait_for_job_ids=prerequisite_job_ids or None,
                        now=now,
                    )
                    dependency["depends_on"] = [f"history:{instrument_id}:D1"]
                    dependency["job_ids"].append(warmup_job.id)
                    prerequisite_job_ids.append(warmup_job.id)
                history_job = await _enqueue_history_dependency(
                    db,
                    parent_job_id=parent.id,
                    request_id=request_id,
                    dependency_id=dependency_id,
                    instrument_id=instrument_id,
                    request=request,
                    priority=parent.priority,
                    timeframe=request.timeframe,
                    wait_for_job_ids=prerequisite_job_ids or None,
                    derived_only=warmup_job is not None,
                    now=now,
                )
                dependency["job_ids"].append(history_job.id)
                dependency["status"] = "queued"
                dependency["reason_code"] = None
            elif dataset is PreparationDataset.HOLDINGS and status == "queued":
                holdings_job = await _enqueue_etf_holdings_job(
                    db,
                    parent_job_id=parent.id,
                    request_id=request_id,
                    dependency_id=dependency_id,
                    instrument_id=instrument_id,
                    request=request,
                    priority=parent.priority,
                    now=now,
                )
                dependency["job_ids"].append(holdings_job.id)
            dependencies.append(dependency)

    data = deepcopy((parent.metadata_payload or {})["data_preparation"])
    data["dependencies"] = dependencies
    data["last_progress_at"] = now.isoformat()
    data["status"] = _aggregate_status(dependencies)
    parent.metadata_payload = {"data_preparation": data}
    await db.flush()
    return parent


async def create_maintenance_data_preparation_request(
    db: AsyncSession,
    *,
    request: DataEnsureRequest,
    idempotency_key: str,
    priority: str = "background",
    now: datetime | None = None,
) -> MarketRefreshJob:
    """Queue non-owner system maintenance through the same durable planner."""

    return await create_data_preparation_request(
        db,
        owner_user_id=None,
        request=request,
        idempotency_key=idempotency_key,
        priority=priority,
        system_maintenance=True,
        now=now,
    )


async def expand_resolved_identity_dependency(
    db: AsyncSession,
    *,
    identity_job: MarketRefreshJob,
    instrument_id: int,
    parent_job_id: int | None = None,
    now: datetime | None = None,
) -> None:
    """Replace a provisional symbol dependency with canonical shared work."""

    preparation = (identity_job.metadata_payload or {}).get("data_preparation_child") or {}
    refs = list(preparation.get("parent_refs") or [])
    if parent_job_id is not None:
        refs = [ref for ref in refs if int(ref.get("parent_job_id") or 0) == parent_job_id]
    elif not refs and preparation.get("parent_job_id") is not None:
        refs = [{"parent_job_id": preparation["parent_job_id"]}]
    if not refs:
        return
    for parent_ref in refs:
        await _expand_parent_identity_dependency(
            db,
            identity_job=identity_job,
            instrument_id=instrument_id,
            parent_id=int(parent_ref["parent_job_id"]),
            now=now,
        )


async def _expand_parent_identity_dependency(
    db: AsyncSession,
    *,
    identity_job: MarketRefreshJob,
    instrument_id: int,
    parent_id: int,
    now: datetime | None = None,
) -> None:
    parent = await db.get(MarketRefreshJob, parent_id)
    if parent is None:
        return
    source = (parent.metadata_payload or {}).get("data_preparation") or {}
    if source.get("role") not in _TRACKING_ROLES:
        return
    data = deepcopy(source)
    request = DataEnsureRequest.model_validate(data["normalized_request"])
    updated_at = now or datetime.now(UTC)
    dependencies = list(data.get("dependencies") or [])
    matching_identity_dependency_ids = {
        str(dependency["dependency_id"])
        for dependency in dependencies
        if dependency.get("dataset") == PreparationDataset.IDENTITY.value
        and identity_job.id in [int(value) for value in dependency.get("job_ids", [])]
    }
    pending_history = [
        deepcopy(dependency)
        for dependency in dependencies
        if dependency.get("dataset") == PreparationDataset.HISTORY.value
        and dependency.get("reason_code") == "identity_dependency_pending"
        and matching_identity_dependency_ids.intersection(
            str(value) for value in (dependency.get("depends_on") or [])
        )
    ]

    # Acquire child dataset locks before the parent lock. Other graph writers
    # follow the same child-then-parent order, avoiding advisory-lock cycles.
    history_updates: dict[str, tuple[list[int], list[str]]] = {}
    for dependency in pending_history:
        dependency_id = str(dependency["dependency_id"])
        history_ids: list[int] = []
        new_dependencies: list[str] = []
        if request.timeframe in {Timeframe.W1, Timeframe.MN}:
            daily_job = await _enqueue_history_dependency(
                db,
                parent_job_id=parent_id,
                request_id=str(data["request_id"]),
                dependency_id=dependency_id,
                instrument_id=instrument_id,
                request=request,
                priority=parent.priority,
                timeframe=Timeframe.D1,
                wait_for_job_ids=[identity_job.id],
                now=updated_at,
            )
            history_ids.append(daily_job.id)
            new_dependencies.append(f"history:{instrument_id}:D1")
        history_job = await _enqueue_history_dependency(
            db,
            parent_job_id=parent_id,
            request_id=str(data["request_id"]),
            dependency_id=dependency_id,
            instrument_id=instrument_id,
            request=request,
            priority=parent.priority,
            timeframe=request.timeframe,
            wait_for_job_ids=history_ids[-1:] or [identity_job.id],
            derived_only=request.timeframe in {Timeframe.W1, Timeframe.MN},
            now=updated_at,
        )
        history_ids.append(history_job.id)
        history_updates[dependency_id] = (history_ids, new_dependencies)

    requested_datasets = data.get("normalized_request", {}).get("datasets")
    instrument = await db.get(Instrument, instrument_id)
    is_etf = instrument is not None and await _instrument_is_etf(db, instrument_id)
    wants_holdings = PreparationDataset.HOLDINGS.value in (requested_datasets or []) or (
        requested_datasets is None and is_etf
    )
    has_instrument_holdings = any(
        item.get("dataset") == PreparationDataset.HOLDINGS.value
        and item.get("instrument_id") == instrument_id
        for item in dependencies
    )
    holdings_addition: dict | None = None
    if wants_holdings and not has_instrument_holdings:
        if not is_etf:
            holdings_state, reason = "unavailable", "not_applicable"
        else:
            holdings_state, reason = await _dataset_initial_state(
                db, instrument_id, PreparationDataset.HOLDINGS, now=updated_at
            )
        holdings_addition = {
            "dependency_id": str(uuid4()),
            "depends_on": [f"profile:{instrument_id}"],
            "instrument_id": instrument_id,
            "symbol": instrument.symbol if instrument is not None else None,
            "dataset": PreparationDataset.HOLDINGS.value,
            "status": holdings_state,
            "reason_code": reason,
            "requested_start": request.start_at.isoformat() if request.start_at else None,
            "requested_end": request.end_at.isoformat() if request.end_at else None,
            "covered_start": None,
            "covered_end": None,
            "retry_at": None,
            "job_ids": [],
            "updated_at": updated_at.isoformat(),
        }
        if holdings_state == "queued":
            holdings_job = await _enqueue_etf_holdings_job(
                db,
                parent_job_id=parent_id,
                request_id=str(data["request_id"]),
                dependency_id=str(holdings_addition["dependency_id"]),
                instrument_id=instrument_id,
                request=request,
                priority=parent.priority,
                now=updated_at,
            )
            holdings_addition["job_ids"].append(holdings_job.id)

    # Reload after taking the per-parent lock: another identity worker may have
    # committed its own leg while this worker was enqueueing the child jobs.
    parent = await _lock_parent_for_update(db, parent_id)
    if parent is None:
        return
    current_source = (parent.metadata_payload or {}).get("data_preparation") or {}
    if current_source.get("role") not in _TRACKING_ROLES:
        return
    data = deepcopy(current_source)
    dependencies = list(data.get("dependencies") or [])
    for dependency in dependencies:
        references_identity = identity_job.id in [
            int(value) for value in dependency.get("job_ids", [])
        ]
        if references_identity and dependency.get("dataset") in {
            PreparationDataset.IDENTITY.value,
            PreparationDataset.PROFILE.value,
        }:
            dependency["instrument_id"] = instrument_id
            dependency["status"] = "queued"
            dependency["reason_code"] = None
            dependency["updated_at"] = updated_at.isoformat()
        dependency_id = str(dependency.get("dependency_id"))
        history_update = history_updates.get(dependency_id)
        if (
            history_update is not None
            and dependency.get("dataset") == PreparationDataset.HISTORY.value
            and dependency.get("reason_code") == "identity_dependency_pending"
        ):
            history_ids, new_dependencies = history_update
            dependency.update(
                {
                    "instrument_id": instrument_id,
                    "status": "queued",
                    "reason_code": None,
                    "depends_on": new_dependencies,
                    "job_ids": list(
                        dict.fromkeys([*(dependency.get("job_ids") or []), *history_ids])
                    ),
                    "updated_at": updated_at.isoformat(),
                }
            )
    if holdings_addition is not None and not any(
        item.get("dataset") == PreparationDataset.HOLDINGS.value
        and item.get("instrument_id") == instrument_id
        for item in dependencies
    ):
        dependencies.append(holdings_addition)
    data["dependencies"] = dependencies
    data["status"] = _aggregate_status(dependencies)
    data["version"] = int(data.get("version") or 1) + 1
    data["last_progress_at"] = updated_at.isoformat()
    parent.metadata_payload = {**deepcopy(parent.metadata_payload or {}), "data_preparation": data}
    await db.flush()


async def record_identity_preparation_outcome(
    db: AsyncSession,
    *,
    identity_job: MarketRefreshJob,
    status: str,
    reason_code: str | None,
    retry_at: datetime | None = None,
    parent_job_id: int | None = None,
    dataset_filter: PreparationDataset | None = None,
    now: datetime | None = None,
) -> None:
    """Persist a terminal/waiting identity outcome without hiding other data."""

    preparation = (identity_job.metadata_payload or {}).get("data_preparation_child") or {}
    refs = list(preparation.get("parent_refs") or [])
    if parent_job_id is not None:
        refs = [ref for ref in refs if int(ref.get("parent_job_id") or 0) == parent_job_id]
    elif not refs and preparation.get("parent_job_id") is not None:
        refs = [{"parent_job_id": preparation["parent_job_id"]}]
    for ref in refs:
        await _record_parent_identity_outcome(
            db,
            identity_job=identity_job,
            parent_id=int(ref["parent_job_id"]),
            status=status,
            reason_code=reason_code,
            retry_at=retry_at,
            dataset_filter=dataset_filter,
            now=now,
        )


async def _record_parent_identity_outcome(
    db: AsyncSession,
    *,
    identity_job: MarketRefreshJob,
    parent_id: int,
    status: str,
    reason_code: str | None,
    retry_at: datetime | None = None,
    dataset_filter: PreparationDataset | None = None,
    now: datetime | None = None,
) -> None:
    parent = await _lock_parent_for_update(db, parent_id)
    if parent is None:
        return
    source = (parent.metadata_payload or {}).get("data_preparation") or {}
    data = deepcopy(source)
    current = now or datetime.now(UTC)
    dependency_status = "waiting" if status == "held" else "unavailable"
    if status == "failed":
        dependency_status = "failed"
    dependencies = list(data.get("dependencies") or [])
    matching_identity_dependency_ids = {
        str(dependency["dependency_id"])
        for dependency in dependencies
        if dependency.get("dataset") == PreparationDataset.IDENTITY.value
        and identity_job.id in [int(value) for value in dependency.get("job_ids", [])]
    }
    for dependency in dependencies:
        if dataset_filter is not None and dependency.get("dataset") != dataset_filter.value:
            continue
        references_job = identity_job.id in [int(value) for value in dependency.get("job_ids", [])]
        waiting_for_identity = dependency.get(
            "reason_code"
        ) == "identity_dependency_pending" and bool(
            matching_identity_dependency_ids.intersection(
                str(value) for value in (dependency.get("depends_on") or [])
            )
        )
        if references_job or waiting_for_identity:
            dependency["status"] = dependency_status
            dependency["reason_code"] = reason_code or "identity_not_resolved"
            dependency["retry_at"] = retry_at.isoformat() if retry_at else None
            dependency["updated_at"] = current.isoformat()
    data["dependencies"] = dependencies
    data["status"] = _aggregate_status(dependencies)
    data["version"] = int(data.get("version") or 1) + 1
    data["last_progress_at"] = current.isoformat()
    parent.metadata_payload = {**deepcopy(parent.metadata_payload or {}), "data_preparation": data}
    await db.flush()


def _aggregate_status(dependencies: list[dict]) -> str:
    if not dependencies:
        return "unavailable"
    statuses = [str(item.get("status") or "waiting") for item in dependencies]
    if all(status == "ready" for status in statuses):
        return "ready"
    if any(status == "ready" for status in statuses):
        return "partial"
    if any(status == "running" for status in statuses):
        return "running"
    if any(status == "queued" for status in statuses):
        return "queued"
    if any(status == "waiting" for status in statuses):
        return "waiting"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "partial" for status in statuses):
        return "partial"
    return "unavailable"


def _deferred_job_reason(jobs: list[MarketRefreshJob]) -> str:
    """Return the persisted safe hold reason for a deferred child, if present."""

    for job in jobs:
        payload = job.metadata_payload or {}
        reason = payload.get("defer_reason")
        if reason:
            return str(reason)
        summary = job.result_summary or {}
        reason = summary.get("reason_code")
        if reason:
            return str(reason)
    return "provider_capacity_deferred"


def _history_wait_projection(
    jobs: list[MarketRefreshJob], *, useful_coverage: bool
) -> tuple[str, str, datetime | None]:
    """Project runnable work ahead of quota waits; expose the earliest wait only
    when every remaining child is time-gated.
    """

    if any(job.status == "failed" for job in jobs):
        return ("partial" if useful_coverage else "failed", "history_backfill_failed", None)
    if any(job.status in {"queued", "leased"} for job in jobs):
        if any(job.status == "leased" for job in jobs):
            status = "partial" if useful_coverage else "running"
        else:
            status = "partial" if useful_coverage else "queued"
        return status, "history_backfill_pending", None

    timed_jobs = [job for job in jobs if job.status in {"deferred", "retry"}]
    if timed_jobs:
        retry_at = min(
            (_as_utc(job.next_attempt_at) for job in timed_jobs if job.next_attempt_at is not None),
            default=None,
        )
        return (
            "partial" if useful_coverage else "waiting",
            _deferred_job_reason(timed_jobs),
            retry_at,
        )
    return ("partial" if useful_coverage else "queued", "history_backfill_pending", None)


def _has_useful_history_output(jobs: list[MarketRefreshJob]) -> bool:
    return any(
        int((job.result_summary or {}).get("bars_observed") or 0) > 0
        or (job.result_summary or {}).get("data_status") in {"ready", "partial"}
        or (job.result_summary or {}).get("chunk_coverage_status") == "ready"
        or (job.result_summary or {}).get("range_coverage_status") in {"ready", "partial"}
        for job in jobs
        if job.status == "completed"
    )


async def get_data_preparation_response(
    db: AsyncSession, *, parent: MarketRefreshJob, owner_user_id: int
) -> DataEnsureResponse:
    data = (parent.metadata_payload or {}).get("data_preparation") or {}
    if data.get("owner_user_id") != owner_user_id or data.get("role") != "owner_request_tracking":
        raise HTTPException(status_code=404, detail={"code": "preparation_request_not_found"})
    dependencies = list(data.get("dependencies") or [])
    job_ids = sorted(
        {
            int(job_id)
            for dependency in dependencies
            for job_id in [
                *(dependency.get("job_ids") or []),
                *(dependency.get("background_job_ids") or []),
            ]
            if job_id is not None
        }
    )
    jobs_by_id: dict[int, MarketRefreshJob] = {}
    if job_ids:
        jobs_by_id = {
            job.id: job
            for job in (
                await db.execute(select(MarketRefreshJob).where(MarketRefreshJob.id.in_(job_ids)))
            ).scalars()
        }
    dependency_responses = []
    for dependency in dependencies:
        foreground_ids = [int(value) for value in dependency.get("job_ids", [])]
        background_ids = [int(value) for value in dependency.get("background_job_ids", [])]
        child_jobs = [
            jobs_by_id[int(job_id)] for job_id in foreground_ids if int(job_id) in jobs_by_id
        ]
        background_jobs = [jobs_by_id[job_id] for job_id in background_ids if job_id in jobs_by_id]
        item_status = dependency.get("status", "waiting")
        reason = dependency.get("reason_code")
        retry_at = dependency.get("retry_at")
        updated_at = _as_utc(datetime.fromisoformat(dependency["updated_at"]))
        if background_jobs and child_jobs and all(job.status == "completed" for job in child_jobs):
            updated_at = max(
                (_as_utc(job.updated_at) for job in [*child_jobs, *background_jobs]),
                default=updated_at,
            )
            remaining_background = [job for job in background_jobs if job.status != "completed"]
            if remaining_background:
                item_status, reason, retry_at = _history_wait_projection(
                    remaining_background,
                    useful_coverage=(
                        dependency.get("status") in {"ready", "partial"}
                        or _has_useful_history_output(child_jobs)
                        or _has_useful_history_output(background_jobs)
                    ),
                )
            else:
                final_outcome = background_jobs[-1].result_summary or {}
                if final_outcome.get("range_coverage_status") == "ready":
                    item_status, reason = "ready", None
                else:
                    item_status, reason = (
                        "partial",
                        (final_outcome.get("reason_code") or "history_coverage_partial"),
                    )
        elif child_jobs:
            child_statuses = {job.status for job in child_jobs}
            if child_statuses <= {"completed"}:
                outcomes = [job.result_summary or {} for job in child_jobs]
                preparation_statuses = {outcome.get("preparation_status") for outcome in outcomes}
                if "held" in preparation_statuses:
                    item_status, reason = (
                        "waiting",
                        next(
                            (
                                outcome.get("reason_code")
                                for outcome in outcomes
                                if outcome.get("reason_code")
                            ),
                            "provider_admission_held",
                        ),
                    )
                    retry_at = next(
                        (
                            outcome.get("retry_at")
                            for outcome in outcomes
                            if outcome.get("retry_at")
                        ),
                        retry_at,
                    )
                elif "failed" in preparation_statuses:
                    item_status, reason = "failed", "preparation_job_failed"
                elif preparation_statuses & {"unavailable", "no_match", "identity_conflict"}:
                    item_status, reason = (
                        "unavailable",
                        next(
                            (
                                outcome.get("reason_code")
                                for outcome in outcomes
                                if outcome.get("reason_code")
                            ),
                            "identity_not_resolved",
                        ),
                    )
                elif preparation_statuses & {"waiting", "held"}:
                    item_status, reason = (
                        "waiting",
                        next(
                            (
                                outcome.get("reason_code")
                                for outcome in outcomes
                                if outcome.get("reason_code")
                            ),
                            "preparation_waiting",
                        ),
                    )
                elif "partial" in preparation_statuses:
                    item_status, reason = (
                        "partial",
                        next(
                            (
                                outcome.get("reason_code")
                                for outcome in outcomes
                                if outcome.get("reason_code")
                            ),
                            "preparation_coverage_partial",
                        ),
                    )
                elif any(outcome.get("data_status") == "empty" for outcome in outcomes):
                    item_status, reason = "unavailable", "source_returned_no_data"
                elif any(outcome.get("data_status") == "partial" for outcome in outcomes):
                    item_status, reason = (
                        "partial",
                        next(
                            (
                                outcome.get("reason_code")
                                for outcome in outcomes
                                if outcome.get("reason_code")
                            ),
                            "history_coverage_partial",
                        ),
                    )
                else:
                    item_status, reason = "ready", None
            elif child_statuses & {"queued", "leased", "deferred", "retry", "failed"}:
                item_status, reason, retry_at = _history_wait_projection(
                    child_jobs,
                    useful_coverage=(
                        dependency.get("status") in {"ready", "partial"}
                        or _has_useful_history_output(child_jobs)
                    ),
                )
            else:
                item_status, reason = "queued", None
            updated_at = max((_as_utc(job.updated_at) for job in child_jobs), default=updated_at)
        coverage_ranges: list[PreparationCoveredRange] = []
        covered_start = dependency.get("covered_start")
        covered_end = dependency.get("covered_end")
        if dependency.get("dataset") == PreparationDataset.HISTORY.value and (
            child_jobs or background_jobs
        ):
            normalized_request = data.get("normalized_request") or {}
            timeframe = str(normalized_request.get("timeframe") or Timeframe.D1.value)
            timeframe_enum = Timeframe(timeframe)
            if timeframe_enum in {Timeframe.W1, Timeframe.MN}:
                coverage_ranges = await _persisted_derived_coverage_ranges(
                    db,
                    instrument_id=int(dependency.get("instrument_id") or 0),
                    timeframe=timeframe_enum,
                    adjusted=bool(normalized_request.get("adjusted", True)),
                    requested_start=(
                        _as_utc(datetime.fromisoformat(normalized_request["start_at"]))
                        if normalized_request.get("start_at")
                        else None
                    ),
                    requested_end=(
                        _as_utc(datetime.fromisoformat(normalized_request["end_at"]))
                        if normalized_request.get("end_at")
                        else None
                    ),
                )
            else:
                coverage_ranges = _verified_coverage_ranges(
                    [*child_jobs, *background_jobs], timeframe=timeframe
                )
            if len(coverage_ranges) == 1:
                covered_start = coverage_ranges[0].start_at
                covered_end = coverage_ranges[0].end_at
            else:
                # A singular interval must not bridge a gap or combine different
                # source/adjustment lineages.
                covered_start = covered_end = None
        dependency_responses.append(
            PreparationDependencyResponse(
                dependency_id=str(dependency["dependency_id"]),
                depends_on=list(dependency.get("depends_on") or []),
                instrument_id=dependency.get("instrument_id"),
                symbol=dependency.get("symbol"),
                dataset=PreparationDataset(dependency["dataset"]),
                status=item_status,
                requested_start=dependency.get("requested_start"),
                requested_end=dependency.get("requested_end"),
                covered_start=covered_start,
                covered_end=covered_end,
                reason_code=reason,
                retry_at=retry_at,
                updated_at=updated_at,
                covered_ranges=coverage_ranges,
            )
        )
    dep_statuses = [item.status for item in dependency_responses]
    status = _aggregate_status([{"status": value} for value in dep_statuses])
    if not dependencies:
        status = str(data.get("status") or "unavailable")
    created_at = _as_utc(parent.created_at or datetime.now(UTC))
    updated_at = max(
        (item.updated_at for item in dependency_responses),
        default=_as_utc(parent.updated_at or created_at),
    )
    progress_at = _as_utc(
        datetime.fromisoformat(data.get("last_progress_at") or created_at.isoformat())
    )
    return DataEnsureResponse(
        request_id=str(data["request_id"]),
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        version=int(data.get("version") or 1),
        target=dict(data.get("target") or {}),
        dependencies=dependency_responses,
        completed=sum(
            item.status in {"ready", "partial", "unavailable", "failed"}
            for item in dependency_responses
        ),
        total=len(dependency_responses),
        last_progress_at=progress_at,
        has_pending_work=any(
            job.status in _PENDING_PREPARATION_JOB_STATUSES for job in jobs_by_id.values()
        ),
    )


async def load_owner_request(
    db: AsyncSession, *, request_id: str, owner_user_id: int
) -> MarketRefreshJob:
    parent = (
        await db.execute(
            select(MarketRefreshJob).where(
                MarketRefreshJob.capability == _TRACKING_CAPABILITY,
                MarketRefreshJob.metadata_payload["data_preparation"]["request_id"].as_string()
                == request_id,
            )
        )
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail={"code": "preparation_request_not_found"})
    data = (parent.metadata_payload or {}).get("data_preparation") or {}
    if data.get("owner_user_id") != owner_user_id:
        raise HTTPException(status_code=404, detail={"code": "preparation_request_not_found"})
    return parent
