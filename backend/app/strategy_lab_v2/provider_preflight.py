"""Local-only Provider reader for Strategy capability preflight.

This adapter reads existing canonical identity, MarketSeries, OHLCV and dataset
freshness rows. It never calls a market-data provider or chooses a fallback
series. Unsupported timeframes/venues remain unavailable until an explicit
coverage calendar contract is implemented.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.models.asset_class import AssetClass, InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.ohlcv_coverage import assess_ohlcv_coverage
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    DataSeriesManifest,
    ETFMembershipReference,
    EventGranularity,
    ProductClass,
)
from app.strategy_lab_v2.etf_pit import ETFPointInTimeMembership, resolve_etf_pit_membership
from app.strategy_lab_v2.provider_series_contract import (
    ProviderSeriesCapabilityEvidence,
    provider_coverage_evidence_digest,
)

SessionFactory = Callable[[], Any]

_TIMEFRAMES = {
    "m1": Timeframe.M1,
    "1m": Timeframe.M1,
    "m5": Timeframe.M5,
    "5m": Timeframe.M5,
    "m15": Timeframe.M15,
    "15m": Timeframe.M15,
    "m30": Timeframe.M30,
    "30m": Timeframe.M30,
    "h1": Timeframe.H1,
    "1h": Timeframe.H1,
    "h2": Timeframe.H2,
    "2h": Timeframe.H2,
    "h4": Timeframe.H4,
    "4h": Timeframe.H4,
    "h12": Timeframe.H12,
    "12h": Timeframe.H12,
    "d1": Timeframe.D1,
    "1d": Timeframe.D1,
    "w1": Timeframe.W1,
    "1w": Timeframe.W1,
    "mn": Timeframe.MN,
    "1mo": Timeframe.MN,
    "y1": Timeframe.Y1,
    "1y": Timeframe.Y1,
}
_ADJUSTMENTS = {
    AdjustmentMode.RAW: AdjustmentBasis.RAW,
    AdjustmentMode.SPLIT_ADJUSTED: AdjustmentBasis.SPLIT_ADJUSTED,
    AdjustmentMode.TOTAL_RETURN: AdjustmentBasis.TOTAL_RETURN,
}


class ProviderLocalCapabilityEvidenceReader:
    """Resolve requested OHLCV capability from exact local Provider records."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        execution_models: Sequence[str],
        account_models: Sequence[str],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(session_factory) or not callable(clock):
            raise TypeError("session_factory and clock must be callable")
        self._session_factory = session_factory
        self._execution_models = _host_scopes(execution_models, "execution_models")
        self._account_models = _host_scopes(account_models, "account_models")
        self._clock = clock

    async def resolve_etf_membership(
        self, *, etf_instrument_id: str, decision_time: datetime
    ) -> ETFPointInTimeMembership:
        """Resolve frozen ETF membership from local rows only; no refresh path."""

        if decision_time.tzinfo is None or decision_time.utcoffset() is None:
            raise ValueError("ETF decision_time must be timezone-aware")
        async with self._session_factory() as session:
            return await resolve_etf_pit_membership(
                session,
                etf_instrument_id=etf_instrument_id,
                decision_time=decision_time,
            )

    async def resolve_pinned_etf_membership(
        self, reference: ETFMembershipReference
    ) -> ETFPointInTimeMembership:
        """Re-read exactly the frozen producer snapshot for restart validation."""

        if not isinstance(reference, ETFMembershipReference):
            raise TypeError("reference must be ETFMembershipReference")
        async with self._session_factory() as session:
            return await resolve_etf_pit_membership(
                session,
                etf_instrument_id=reference.etf_instrument_id,
                decision_time=reference.decision_time,
                snapshot_id=reference.snapshot_id,
            )

    async def __call__(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        requirements: Sequence[CapabilityRequirement],
    ) -> tuple[ProviderSeriesCapabilityEvidence, ...]:
        del (
            principal,
            request_id,
            idempotency_key,
        )  # Provider market data is global, not user-owned.
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("Provider preflight clock must return an aware timestamp")
        if any(not isinstance(item, CapabilityRequirement) for item in requirements):
            raise TypeError("requirements must contain CapabilityRequirement values")

        resolved: list[ProviderSeriesCapabilityEvidence] = []
        async with self._session_factory() as session:
            for requirement in requirements:
                evidence = await self._resolve_one(session, requirement, observed_at)
                if evidence is not None:
                    resolved.append(evidence)
        return tuple(resolved)

    async def _resolve_one(
        self,
        session: Any,
        requirement: CapabilityRequirement,
        observed_at: datetime,
    ) -> ProviderSeriesCapabilityEvidence | None:
        if (
            requirement.event_type != "ohlcv"
            or requirement.event_granularity is not EventGranularity.BAR
            or requirement.adjustment not in _ADJUSTMENTS
        ):
            return None
        timeframe = _TIMEFRAMES.get(requirement.timeframe.casefold())
        # Only the XNYS daily calendar is currently proven by the local coverage
        # implementation; other venue/frequency combinations stay unavailable.
        if timeframe is not Timeframe.D1 or requirement.session != "regular":
            return None

        identity_rows = (
            await session.execute(
                select(Instrument, InstrumentType, AssetClass)
                .join(InstrumentType, InstrumentType.id == Instrument.instrument_type_id)
                .join(AssetClass, AssetClass.id == InstrumentType.asset_class_id)
                .where(Instrument.domain_key == requirement.instrument_id)
            )
        ).all()
        if len(identity_rows) != 1:
            return None
        instrument, instrument_type, asset_class = identity_rows[0]
        product_class = _product_class(asset_class.name, instrument_type.name)
        if (
            instrument.identity_status != "resolved"
            or not instrument.is_active
            or instrument.is_synthetic
            or product_class is not requirement.product_class
        ):
            return None

        series_rows = (
            (
                await session.execute(
                    select(MarketSeries).where(
                        MarketSeries.instrument_id == instrument.id,
                        MarketSeries.timeframe == timeframe.value,
                        MarketSeries.session_code == requirement.session,
                        MarketSeries.feed_scope == requirement.feed,
                        MarketSeries.adjustment_basis == _ADJUSTMENTS[requirement.adjustment],
                        MarketSeries.is_active.is_(True),
                        MarketSeries.is_canonical.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(series_rows) != 1:
            return None
        series = series_rows[0]
        if not isinstance(series.data_source_id, int):
            return None
        source = (
            await session.execute(
                select(DataSource).where(
                    DataSource.id == series.data_source_id,
                    DataSource.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if source is None:
            return None
        exchange = (
            (
                await session.execute(select(Exchange).where(Exchange.id == series.exchange_id))
            ).scalar_one_or_none()
            if series.exchange_id is not None
            else None
        )
        if exchange is None or exchange.mic != "XNYS":
            return None

        dataset_key = f"{timeframe.value}:{'raw' if series.adjustment_basis is AdjustmentBasis.RAW else 'adj'}"
        states = (
            (
                await session.execute(
                    select(InstrumentDatasetState).where(
                        InstrumentDatasetState.instrument_id == instrument.id,
                        InstrumentDatasetState.data_source_id == series.data_source_id,
                        InstrumentDatasetState.dataset_type == "ohlcv",
                        InstrumentDatasetState.dataset_key == dataset_key,
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(states) != 1:
            return None
        dataset_state = states[0]
        if dataset_state.status is not DatasetStatus.FRESH:
            return None

        bars = (
            (
                await session.execute(
                    select(OHLCVBar).where(
                        OHLCVBar.instrument_id == instrument.id,
                        OHLCVBar.market_series_id == series.id,
                        OHLCVBar.data_source_id == series.data_source_id,
                        OHLCVBar.timeframe == timeframe,
                        OHLCVBar.session == requirement.session,
                        OHLCVBar.adjustment_basis == series.adjustment_basis.value,
                        OHLCVBar.adjustment_version == series.adjustment_version,
                        OHLCVBar.ts >= requirement.start,
                        OHLCVBar.ts <= requirement.end,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not bars:
            return None
        assessment = assess_ohlcv_coverage(
            bars,
            timeframe,
            requirement.start,
            requirement.end,
            mode="historical",
            now=observed_at,
            calendar="XNYS",
        )
        if assessment.status.value != "ready" or not assessment.bar_count:
            return None

        calendar_digest = content_digest(
            {
                "calendar": "XNYS",
                "policy": "ohlcv-coverage-major-full-day-closures-v1",
                "session": requirement.session,
                "exchange_mic": exchange.mic,
            }
        )
        corporate_action_semantics = (
            "raw_unadjusted"
            if series.adjustment_basis is AdjustmentBasis.RAW
            else (series.provenance or {}).get("corporate_action_semantics")
        )
        if (
            not isinstance(corporate_action_semantics, str)
            or not corporate_action_semantics.strip()
        ):
            return None
        manifest = DataSeriesManifest(
            instrument_id=requirement.instrument_id,
            event_type="ohlcv",
            event_granularity=EventGranularity.BAR,
            timeframe=timeframe.value,
            session=series.session_code,
            feed=series.feed_scope,
            start=requirement.start,
            end=requirement.end,
            adjustment=requirement.adjustment,
            corporate_action_semantics=corporate_action_semantics,
            coverage_evidence_digest=provider_coverage_evidence_digest(
                instrument,
                series,
                assessment,
                calendar_digest=calendar_digest,
            ),
            content_digest=content_digest(
                {
                    "series_id": series.id,
                    "source_id": series.data_source_id,
                    "source_series_key": series.source_series_key,
                    "bars": tuple(
                        {
                            "ts": bar.ts,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                            "vwap": bar.vwap,
                            "adjustment_basis": bar.adjustment_basis,
                            "adjustment_version": bar.adjustment_version,
                            "scope_key": bar.scope_key,
                        }
                        for bar in sorted(bars, key=lambda item: item.ts)
                    ),
                }
            ),
            row_count=assessment.bar_count,
        )
        return ProviderSeriesCapabilityEvidence(
            instrument=instrument,
            series=series,
            manifest=manifest,
            coverage_assessment=assessment,
            dataset_state=dataset_state,
            calendar_digest=calendar_digest,
            evaluated_at=observed_at,
            product_class=product_class,
            execution_models=self._execution_models,
            account_models=self._account_models,
        )


def _host_scopes(values: Sequence[str], field: str) -> frozenset[str]:
    if isinstance(values, str | bytes):
        raise TypeError(f"{field} must be a collection of host-authorized values")
    scopes = frozenset(values)
    if not scopes or any(not isinstance(item, str) or not item.strip() for item in scopes):
        raise ValueError(f"{field} must contain non-empty host-authorized values")
    return scopes


def _product_class(asset_class: str, instrument_type: str) -> ProductClass | None:
    asset = asset_class.strip().casefold()
    kind = instrument_type.strip().casefold()
    if asset == "equity":
        return ProductClass.EQUITY
    if asset == "cryptocurrency":
        return ProductClass.CRYPTO
    if asset == "derivative" and kind == "future":
        return ProductClass.FUTURE
    if asset == "derivative" and kind == "option":
        return ProductClass.OPTION
    if asset == "currency" and kind in {"forex pair", "fx pair"}:
        return ProductClass.FX
    return None


__all__ = ["ProviderLocalCapabilityEvidenceReader"]
