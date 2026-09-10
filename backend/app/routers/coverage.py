"""Canonical local coverage and freshness APIs for workstation tools."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentDatasetState, MarketBarObservation
from app.models.user import User
from app.schemas.coverage import (
    DatasetCoverageStateOut,
    InstrumentCoverageOut,
    LocalCoverageRangeOut,
    OhlcvCoverageOut,
)
from app.services.ohlcv_coverage import (
    assess_observed_ohlcv_cadence,
    assess_ohlcv_coverage,
    reconcile_ohlcv_storage,
    summarize_ohlcv_lineage,
)

router = APIRouter(prefix="/coverage", tags=["coverage"])


@router.get("/instruments/{symbol}/ohlcv", response_model=OhlcvCoverageOut)
async def instrument_ohlcv_coverage(
    symbol: str,
    timeframe: Timeframe = Query(default=Timeframe.D1),
    start: datetime = Query(...),
    end: datetime = Query(...),
    mode: str = Query(default="historical", pattern="^(historical|latest)$"),
    adjusted: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Assess local OHLCV readiness without contacting any provider."""
    if end < start:
        raise HTTPException(
            422,
            detail={"code": "invalid_coverage_range", "message": "end must be on or after start"},
        )
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})

    bars = (
        (
            await db.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(adjusted),
                    OHLCVBar.ts >= start,
                    OHLCVBar.ts <= end,
                )
                .order_by(OHLCVBar.ts)
            )
        )
        .scalars()
        .all()
    )
    assessment = assess_ohlcv_coverage(
        bars,
        timeframe,
        start,
        end,
        mode=mode,
        freshness_seconds=86_400 if timeframe == Timeframe.D1 else None,
        calendar="XNYS" if (instrument.currency or "").upper() == "USD" else None,
    )
    lineage = summarize_ohlcv_lineage(bars, adjusted=adjusted)
    observations = (
        (
            await db.execute(
                select(MarketBarObservation).where(
                    MarketBarObservation.instrument_id == instrument.id,
                    MarketBarObservation.timeframe == timeframe,
                    MarketBarObservation.is_adjusted.is_(adjusted),
                    MarketBarObservation.ts >= start,
                    MarketBarObservation.ts <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    storage_evidence = reconcile_ohlcv_storage(bars, observations)
    observed_cadence = assess_observed_ohlcv_cadence(bars)
    if adjusted:
        provider_source_ids = {
            bar.data_source_id
            for bar in bars
            if bar.is_derived is False and bar.data_source_id is not None
        }
        if lineage.source_lineage == "derived_only":
            state_source_filter = InstrumentDatasetState.data_source_id.is_(None)
        elif provider_source_ids:
            state_source_filter = InstrumentDatasetState.data_source_id.in_(provider_source_ids)
        else:
            # Preserve the legacy provider-state lookup when a fixture or
            # older row has provider lineage but no source identity.
            state_source_filter = InstrumentDatasetState.data_source_id.is_not(None)
        dataset_keys = [f"{timeframe.value}:adj"]
        if lineage.adjustment_provenance.get("source_kind") == "local_split_ratio":
            dataset_keys.insert(0, f"{timeframe.value}:adj:local_split_ratio")
        elif lineage.adjustment_provenance.get("source_kind") == "provider_adjustment_factor":
            dataset_keys.insert(0, f"{timeframe.value}:adj:provider_adjustment_factor")
        dataset_state = (
            await db.execute(
                select(InstrumentDatasetState)
                .where(
                    InstrumentDatasetState.instrument_id == instrument.id,
                    state_source_filter,
                    InstrumentDatasetState.dataset_type == "ohlcv",
                    InstrumentDatasetState.dataset_key.in_(dataset_keys),
                )
                .order_by(
                    InstrumentDatasetState.dataset_key,
                    InstrumentDatasetState.observed_at.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        state_provenance = (
            (dataset_state.extra_data or {}).get("adjustment_provenance")
            if dataset_state is not None
            else None
        )
        if isinstance(state_provenance, dict):
            factor_version = state_provenance.get("factor_version")
            if isinstance(factor_version, str) and factor_version:
                lineage.adjustment_provenance["factor_version"] = factor_version
                lineage.adjustment_provenance["factor_status"] = str(
                    state_provenance.get("factor_status") or "rebuildable_split_factors"
                )
            for key in (
                "factor_observation_count",
                "factor_rebuildable_observation_count",
                "factor_opaque_observation_count",
                "factor_kinds",
            ):
                if key in state_provenance:
                    lineage.adjustment_provenance[key] = state_provenance[key]
    return OhlcvCoverageOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        timeframe=timeframe.value,
        adjusted=adjusted,
        mode=mode,
        requested_start=start,
        requested_end=end,
        status=assessment.status.value,
        covered_start=assessment.covered_start,
        covered_end=assessment.covered_end,
        bar_count=assessment.bar_count,
        missing_slices=[
            {"start": gap_start, "end": gap_end} for gap_start, gap_end in assessment.missing_slices
        ],
        explanation=assessment.explanation,
        lineage={
            "provider_bar_count": lineage.provider_bar_count,
            "derived_bar_count": lineage.derived_bar_count,
            "unknown_bar_count": lineage.unknown_bar_count,
            "source_lineage": lineage.source_lineage,
            "source_timeframes": list(lineage.source_timeframes),
        },
        adjustment_provenance=lineage.adjustment_provenance,
        storage_evidence={
            "status": storage_evidence.status,
            "provider_bar_count": storage_evidence.provider_bar_count,
            "observation_count": storage_evidence.observation_count,
            "matched_observation_count": storage_evidence.matched_observation_count,
            "missing_observation_count": storage_evidence.missing_observation_count,
            "mismatched_observation_count": storage_evidence.mismatched_observation_count,
            "orphan_observation_count": storage_evidence.orphan_observation_count,
        },
        observed_cadence={
            "status": observed_cadence.status,
            "sample_count": observed_cadence.sample_count,
            "median_interval_days": observed_cadence.median_interval_days,
            "min_interval_days": observed_cadence.min_interval_days,
            "max_interval_days": observed_cadence.max_interval_days,
            "semantics": "diagnostic_of_returned_bar_timestamps_only",
        },
    )


@router.get("/instruments/{symbol}", response_model=InstrumentCoverageOut)
async def instrument_coverage(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return only persisted canonical coverage/freshness, never provider routing."""
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})

    aggregate_rows = (
        await db.execute(
            select(
                OHLCVBar.timeframe,
                func.min(OHLCVBar.ts).label("oldest"),
                func.max(OHLCVBar.ts).label("newest"),
                func.count().label("bar_count"),
            )
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.is_adjusted.is_(True))
            .group_by(OHLCVBar.timeframe)
        )
    ).all()
    states = (
        (
            await db.execute(
                select(InstrumentDatasetState)
                .where(InstrumentDatasetState.instrument_id == instrument.id)
                .order_by(InstrumentDatasetState.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return InstrumentCoverageOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        adjustment="split_adjusted",
        local_coverage={
            row.timeframe.value: LocalCoverageRangeOut(
                oldest=row.oldest, newest=row.newest, bar_count=int(row.bar_count)
            )
            for row in aggregate_rows
        },
        dataset_states=[
            DatasetCoverageStateOut(
                dataset_type=state.dataset_type,
                dataset_key=state.dataset_key,
                status=state.status.value,
                coverage_start=state.coverage_start,
                coverage_end=state.coverage_end,
                observed_at=state.observed_at,
                fetched_at=state.fetched_at,
                stale_after=state.stale_after,
                version=state.version,
                extra_data=state.extra_data,
            )
            for state in states
        ],
        refreshed_at=datetime.now(UTC),
    )
