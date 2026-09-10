from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.adjustment_factor import AdjustmentFactorObservation
from app.models.data_source import DataSource
from app.models.instrument_event import EventTimeHint, InstrumentEvent, InstrumentEventType
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentDatasetState
from app.services.adjustment_factors import (
    build_adjustment_factor_snapshot,
    materialize_local_provider_adjusted_view,
    materialize_local_split_adjusted_view,
    persist_adjustment_factor_observations,
    rebuild_provider_adjusted_bars,
    rebuild_split_adjusted_bars,
    summarize_persisted_adjustment_factor_provenance,
)
from tests.unit.conftest import AsyncSessionAdapter


def _event(
    event_type: InstrumentEventType,
    event_time: datetime,
    *,
    source_event_key: str,
    split_ratio: Decimal | None = None,
    dividend_amount: Decimal | None = None,
    adjustment_factor: Decimal | None = None,
) -> InstrumentEvent:
    return InstrumentEvent(
        instrument_id=1,
        event_type=event_type,
        event_time=event_time,
        time_hint=EventTimeHint.UNKNOWN,
        title="fixture event",
        source="fixture-provider",
        source_event_key=source_event_key,
        fetched_at=event_time,
        split_ratio=split_ratio,
        dividend_amount=dividend_amount,
        adjustment_factor=adjustment_factor,
    )


def test_split_factor_snapshot_is_stable_and_order_independent():
    events = [
        _event(
            InstrumentEventType.SPLIT,
            datetime(2024, 6, 10, tzinfo=UTC),
            source_event_key="split:2024-06-10",
            split_ratio=Decimal("2"),
        ),
        _event(
            InstrumentEventType.SPLIT,
            datetime(2020, 1, 2, tzinfo=UTC),
            source_event_key="split:2020-01-02",
            split_ratio=Decimal("1.5"),
        ),
    ]

    first = build_adjustment_factor_snapshot(events)
    second = build_adjustment_factor_snapshot(reversed(events))

    assert first == second
    assert first.status == "rebuildable_split_factors"
    assert first.event_count == 2
    assert first.rebuildable_event_count == 2
    assert first.opaque_event_count == 0
    assert first.factor_kinds == ("split_ratio",)
    assert first.version == "afv1-ca98881ebcfac8db36594c89dddd9ede60ee793928b8f1c7f09cf798cd944dda"


def test_dividend_event_keeps_adjustment_factors_explicitly_opaque():
    snapshot = build_adjustment_factor_snapshot(
        [
            _event(
                InstrumentEventType.DIVIDEND,
                datetime(2024, 6, 10, tzinfo=UTC),
                source_event_key="dividend:2024-06-10",
                dividend_amount=Decimal("0.25"),
            )
        ]
    )

    assert snapshot.version is None
    assert snapshot.status == "provider_native_opaque_incomplete_factor_set"
    assert snapshot.event_count == 1
    assert snapshot.rebuildable_event_count == 0
    assert snapshot.opaque_event_count == 1
    assert snapshot.factor_kinds == ("opaque",)


def test_provider_supplied_dividend_factor_is_rebuildable():
    snapshot = build_adjustment_factor_snapshot(
        [
            _event(
                InstrumentEventType.DIVIDEND,
                datetime(2024, 6, 10, tzinfo=UTC),
                source_event_key="dividend:2024-06-10",
                dividend_amount=Decimal("0.25"),
                adjustment_factor=Decimal("0.9975"),
            )
        ]
    )

    assert snapshot.status == "rebuildable_provider_factors"
    assert snapshot.event_count == 1
    assert snapshot.rebuildable_event_count == 1
    assert snapshot.opaque_event_count == 0
    assert snapshot.factor_kinds == ("provider_supplied",)
    assert snapshot.version is not None and snapshot.version.startswith("afv1-")


def test_missing_split_ratio_does_not_create_a_rebuildable_version():
    snapshot = build_adjustment_factor_snapshot(
        [
            _event(
                InstrumentEventType.SPLIT,
                datetime(2024, 6, 10, tzinfo=UTC),
                source_event_key="split:2024-06-10",
            )
        ]
    )

    assert snapshot.version is None
    assert snapshot.status == "provider_native_opaque_incomplete_factor_set"
    assert snapshot.rebuildable_event_count == 0
    assert snapshot.opaque_event_count == 1


def test_persisted_factor_provenance_requires_one_consistent_rebuildable_version():
    observations = [
        AdjustmentFactorObservation(
            factor_type="split",
            factor=Decimal("2"),
            source_event_key="split:2024-06-10",
            factor_version="afv1-stable",
        ),
        AdjustmentFactorObservation(
            factor_type="split",
            factor=Decimal("1.5"),
            source_event_key="split:2020-01-02",
            factor_version="afv1-stable",
        ),
    ]

    summary = summarize_persisted_adjustment_factor_provenance(observations)

    assert summary.status == "rebuildable_split_factors"
    assert summary.version == "afv1-stable"
    assert summary.observation_count == 2
    assert summary.distinct_versions == ("afv1-stable",)
    assert summary.rebuildable_observation_count == 2
    assert summary.opaque_observation_count == 0
    assert summary.factor_kinds == ("split_ratio",)


def test_persisted_factor_provenance_surfaces_mixed_versions_as_opaque():
    observations = [
        AdjustmentFactorObservation(
            factor_type="split",
            factor=Decimal("2"),
            source_event_key="split:2024-06-10",
            factor_version="afv1-old",
        ),
        AdjustmentFactorObservation(
            factor_type="split",
            factor=Decimal("1.5"),
            source_event_key="split:2020-01-02",
            factor_version="afv1-new",
        ),
    ]

    summary = summarize_persisted_adjustment_factor_provenance(observations)

    assert summary.version is None
    assert summary.status == "provider_native_opaque_inconsistent_factor_set"
    assert summary.distinct_versions == ("afv1-new", "afv1-old")
    assert summary.rebuildable_observation_count == 2
    assert summary.opaque_observation_count == 0


def test_persisted_factor_provenance_does_not_promote_missing_version():
    summary = summarize_persisted_adjustment_factor_provenance(
        [
            AdjustmentFactorObservation(
                factor_type="split",
                factor=Decimal("2"),
                source_event_key="split:2024-06-10",
                factor_version=None,
            )
        ]
    )

    assert summary.version is None
    assert summary.status == "provider_native_opaque_incomplete_factor_set"
    assert summary.rebuildable_observation_count == 0
    assert summary.opaque_observation_count == 1


def test_persisted_provider_dividend_factor_is_rebuildable():
    summary = summarize_persisted_adjustment_factor_provenance(
        [
            AdjustmentFactorObservation(
                factor_type="dividend",
                factor=Decimal("0.9975"),
                factor_kind="provider_supplied",
                amount=Decimal("0.25"),
                source_event_key="dividend:2024-06-10",
                factor_version="afv1-provider-dividend",
            )
        ]
    )

    assert summary.status == "rebuildable_provider_factors"
    assert summary.version == "afv1-provider-dividend"
    assert summary.observation_count == 1
    assert summary.rebuildable_observation_count == 1
    assert summary.opaque_observation_count == 0
    assert summary.factor_kinds == ("provider_supplied",)


def _bar(ts: datetime, *, close: str, volume: str = "100"):
    return type(
        "RawBar",
        (),
        {
            "ts": ts,
            "open": Decimal(str(Decimal(close) - Decimal("1"))),
            "high": Decimal(str(Decimal(close) + Decimal("1"))),
            "low": Decimal(str(Decimal(close) - Decimal("2"))),
            "close": Decimal(close),
            "volume": Decimal(volume),
            "vwap": Decimal(close),
        },
    )()


def test_rebuild_split_adjusted_bars_scales_pre_event_prices_and_volume():
    event = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("2"),
        factor_kind="split_ratio",
        source_event_key="split:2024-06-10",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-split",
    )
    result = rebuild_split_adjusted_bars(
        [
            _bar(datetime(2024, 6, 7, 21, tzinfo=UTC), close="100"),
            _bar(datetime(2024, 6, 10, 21, tzinfo=UTC), close="50"),
        ],
        [event],
    )

    assert result.status == "applied"
    assert result.factor_version == "afv1-split"
    assert result.event_count == 1
    assert result.applied_event_count == 1
    before, after = result.bars
    assert before.open == Decimal("49.5")
    assert before.high == Decimal("50.5")
    assert before.low == Decimal("49")
    assert before.close == Decimal("50")
    assert before.volume == Decimal("200")
    assert before.vwap == Decimal("50")
    assert after.close == Decimal("50")
    assert after.volume == Decimal("100")
    assert before.is_adjusted is True and before.is_derived is True


def test_rebuild_split_adjusted_bars_rejects_incomplete_or_mixed_versions():
    incomplete = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("2"),
        source_event_key="split:missing-version",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
    )
    result = rebuild_split_adjusted_bars(
        [_bar(datetime(2024, 6, 7, 21, tzinfo=UTC), close="100")],
        [incomplete],
    )
    assert result.status == "provider_native_opaque_incomplete_factor_set"
    assert result.bars == ()

    first = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("2"),
        source_event_key="split:one",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-one",
    )
    second = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("3"),
        source_event_key="split:two",
        effective_at=datetime(2024, 6, 11, tzinfo=UTC),
        factor_version="afv1-two",
    )
    result = rebuild_split_adjusted_bars([], [first, second])
    assert result.status == "provider_native_opaque_inconsistent_factor_set"
    assert result.bars == ()


def test_rebuild_split_adjusted_bars_does_not_infer_dividend_convention():
    dividend = AdjustmentFactorObservation(
        factor_type="dividend",
        factor=Decimal("0.9975"),
        factor_kind="provider_supplied",
        source_event_key="dividend:2024-06-10",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-provider",
    )
    result = rebuild_split_adjusted_bars(
        [_bar(datetime(2024, 6, 7, 21, tzinfo=UTC), close="100")],
        [dividend],
    )
    assert result.status == "unsupported_dividend_factors"
    assert result.reason == "dividend_adjustment_convention_requires_provider_semantics"
    assert result.bars == ()


def test_rebuild_split_adjusted_bars_requires_split_ratio_orientation():
    provider_factor = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("0.5"),
        factor_kind="provider_supplied",
        source_event_key="split:provider-factor",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-provider",
    )
    result = rebuild_split_adjusted_bars([], [provider_factor])
    assert result.status == "unsupported_provider_factors"
    assert result.reason == "provider_factor_orientation_requires_source_contract"
    assert result.bars == ()


def test_rebuild_provider_adjusted_bars_applies_explicit_dividend_multiplier():
    dividend = AdjustmentFactorObservation(
        factor_type="dividend",
        factor=Decimal("0.9975"),
        factor_kind="provider_supplied",
        source_event_key="dividend:2024-06-10",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-provider-dividend",
    )
    result = rebuild_provider_adjusted_bars(
        [
            _bar(datetime(2024, 6, 7, 21, tzinfo=UTC), close="100"),
            _bar(datetime(2024, 6, 10, 21, tzinfo=UTC), close="100"),
        ],
        [dividend],
    )

    assert result.status == "applied"
    assert result.factor_version == "afv1-provider-dividend"
    assert result.event_count == 1
    assert result.applied_event_count == 1
    before, after = result.bars
    assert before.close == Decimal("99.750000")
    assert before.volume == Decimal("100.2506265664160401002506266")
    assert before.vwap == Decimal("99.750000")
    assert before.derivation_method == "provider_adjustment_factor"
    assert after.close == Decimal("100")
    assert after.volume == Decimal("100")


def test_rebuild_provider_adjusted_bars_rejects_mixed_or_incomplete_inputs():
    provider = AdjustmentFactorObservation(
        factor_type="dividend",
        factor=Decimal("0.9975"),
        factor_kind="provider_supplied",
        source_event_key="dividend:provider",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-provider",
    )
    split = AdjustmentFactorObservation(
        factor_type="split",
        factor=Decimal("2"),
        factor_kind="split_ratio",
        source_event_key="split:ratio",
        effective_at=datetime(2024, 6, 11, tzinfo=UTC),
        factor_version="afv1-provider",
    )
    mixed = rebuild_provider_adjusted_bars([], [provider, split])
    assert mixed.status == "provider_native_opaque_mixed_factor_kinds"
    assert mixed.bars == ()

    incomplete = AdjustmentFactorObservation(
        factor_type="dividend",
        factor_kind="provider_supplied",
        source_event_key="dividend:missing-factor",
        effective_at=datetime(2024, 6, 10, tzinfo=UTC),
        factor_version="afv1-provider",
    )
    result = rebuild_provider_adjusted_bars([], [incomplete])
    assert result.status == "provider_native_opaque_incomplete_factor_set"
    assert result.bars == ()


@pytest.mark.asyncio
async def test_persist_normalizes_factor_events_and_reuses_the_natural_key(db, instrument):
    source = DataSource(name="factor-observation-provider")
    db.add(source)
    db.flush()
    event_time = datetime(2024, 6, 10, tzinfo=UTC)
    event = _event(
        InstrumentEventType.SPLIT,
        event_time,
        source_event_key="split:2024-06-10",
        split_ratio=Decimal("2"),
    )
    event.instrument_id = instrument.id
    event.source = source.name

    session = AsyncSessionAdapter(db)
    assert (
        await persist_adjustment_factor_observations(
            session,
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            events=[event],
        )
        == 1
    )
    event.raw_payload = '{"ratio": 2}'
    assert (
        await persist_adjustment_factor_observations(
            session,
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="TEST",
            events=[event],
        )
        == 1
    )

    rows = db.query(AdjustmentFactorObservation).all()
    assert len(rows) == 1
    assert rows[0].factor_type == "split"
    assert rows[0].factor == Decimal("2.000000000000")
    assert rows[0].factor_version.startswith("afv1-")
    assert rows[0].raw_payload == '{"ratio": 2}'


@pytest.mark.asyncio
async def test_persist_stores_provider_supplied_dividend_factor(db, instrument):
    source = DataSource(name="provider-dividend-factor")
    db.add(source)
    db.flush()
    event_time = datetime(2024, 6, 10, tzinfo=UTC)
    event = _event(
        InstrumentEventType.DIVIDEND,
        event_time,
        source_event_key="dividend:2024-06-10",
        dividend_amount=Decimal("0.25"),
        adjustment_factor=Decimal("0.9975"),
    )
    event.instrument_id = instrument.id
    event.source = source.name
    event.raw_payload = '{"adjustment_factor": 0.9975, "amount": 0.25}'

    persisted = await persist_adjustment_factor_observations(
        AsyncSessionAdapter(db),
        instrument_id=instrument.id,
        data_source_id=source.id,
        provider_symbol="TEST",
        events=[event],
    )

    assert persisted == 1
    row = db.query(AdjustmentFactorObservation).one()
    assert row.factor == Decimal("0.997500000000")
    assert row.factor_kind == "provider_supplied"
    assert row.amount == Decimal("0.250000000000")
    assert row.factor_version.startswith("afv1-")


@pytest.mark.asyncio
async def test_materialize_local_split_view_persists_lineage_and_preserves_provider_rows(
    db, instrument
):
    source = DataSource(name="raw-price-provider")
    db.add(source)
    db.flush()
    before = datetime(2024, 6, 7, 21, tzinfo=UTC)
    after = datetime(2024, 6, 10, 21, tzinfo=UTC)
    db.add_all(
        [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=before,
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                vwap=Decimal("100"),
                is_adjusted=False,
                is_derived=False,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=after,
                open=Decimal("49"),
                high=Decimal("51"),
                low=Decimal("48"),
                close=Decimal("50"),
                volume=Decimal("200"),
                vwap=Decimal("50"),
                is_adjusted=False,
                is_derived=False,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=after,
                open=Decimal("49"),
                high=Decimal("51"),
                low=Decimal("48"),
                close=Decimal("50"),
                volume=Decimal("200"),
                vwap=Decimal("50"),
                is_adjusted=True,
                is_derived=False,
            ),
        ]
    )
    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            factor_type="split",
            effective_at=datetime(2024, 6, 10, tzinfo=UTC),
            factor=Decimal("2"),
            factor_kind="split_ratio",
            source_event_key="split:2024-06-10",
            observed_at=datetime(2024, 6, 11, tzinfo=UTC),
            factor_version="afv1-local-split",
        )
    )
    db.flush()

    result = await materialize_local_split_adjusted_view(
        AsyncSessionAdapter(db), instrument_id=instrument.id
    )

    assert result.status == "applied"
    assert result.raw_bar_count == 2
    assert result.persisted_bar_count == 1
    assert result.updated_bar_count == 0
    assert result.skipped_provider_bar_count == 1
    derived = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(True),
        )
        .one()
    )
    assert derived.ts.replace(tzinfo=UTC) == before
    assert derived.close == Decimal("50.00000000")
    assert derived.volume == Decimal("200.0000")
    assert derived.source_timeframe == "D1"
    assert derived.derivation_method == "local_split_ratio"
    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "D1:adj:local_split_ratio",
        )
        .one()
    )
    assert state.extra_data["source_kind"] == "local_split_ratio"
    assert state.extra_data["adjustment_provenance"]["factor_version"] == "afv1-local-split"


@pytest.mark.asyncio
async def test_materialize_local_provider_view_applies_factor_and_preserves_provider_rows(
    db, instrument
):
    source = DataSource(name="provider-factor-price-provider")
    db.add(source)
    db.flush()
    before = datetime(2024, 6, 7, 21, tzinfo=UTC)
    after = datetime(2024, 6, 10, 21, tzinfo=UTC)
    db.add_all(
        [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=before,
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                vwap=Decimal("100"),
                is_adjusted=False,
                is_derived=False,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                timeframe=Timeframe.D1,
                ts=after,
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                vwap=Decimal("100"),
                is_adjusted=False,
                is_derived=False,
            ),
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=after,
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("99"),
                close=Decimal("101"),
                volume=Decimal("100"),
                vwap=Decimal("101"),
                is_adjusted=True,
                is_derived=False,
            ),
        ]
    )
    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            factor_type="dividend",
            effective_at=after,
            factor=Decimal("0.9975"),
            factor_kind="provider_supplied",
            amount=Decimal("0.25"),
            source_event_key="dividend:2024-06-10",
            observed_at=datetime(2024, 6, 11, tzinfo=UTC),
            factor_version="afv1-provider-dividend",
        )
    )
    db.flush()

    result = await materialize_local_provider_adjusted_view(
        AsyncSessionAdapter(db), instrument_id=instrument.id
    )

    assert result.status == "applied"
    assert result.raw_bar_count == 2
    assert result.persisted_bar_count == 1
    assert result.updated_bar_count == 0
    assert result.skipped_provider_bar_count == 1
    derived = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(True),
        )
        .one()
    )
    assert derived.ts.replace(tzinfo=UTC) == before
    assert derived.close == Decimal("99.75000000")
    assert derived.volume == Decimal("100.2506")
    assert derived.derivation_method == "provider_adjustment_factor"
    state = (
        db.query(InstrumentDatasetState)
        .filter(
            InstrumentDatasetState.instrument_id == instrument.id,
            InstrumentDatasetState.data_source_id.is_(None),
            InstrumentDatasetState.dataset_key == "D1:adj:provider_adjustment_factor",
        )
        .one()
    )
    assert state.extra_data["source_kind"] == "provider_adjustment_factor"
    assert state.extra_data["adjustment_provenance"]["factor_status"] == (
        "rebuildable_provider_factors"
    )
    assert state.extra_data["adjustment_provenance"]["factor_version"] == ("afv1-provider-dividend")
