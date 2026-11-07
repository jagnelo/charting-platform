import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, select

from app.config import settings
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
from app.services.e2e_seed import (
    _E2E_BENCHMARK_PROXY_NAMES,
    _E2E_HOLDINGS,
    _E2E_INDUSTRIES,
    _E2E_INTRADAY_BARS_PER_SESSION,
    _E2E_INTRADAY_HISTORY_BARS,
    _E2E_LONG_RRG_START,
    _E2E_MARKET_NAMES,
    _E2E_MONTHLY_RRG_SYMBOLS,
    _E2E_RECENT_HISTORY_BARS,
    _E2E_RECENT_HISTORY_START,
    seed_e2e_instruments,
    seed_e2e_market_data,
)
from app.services.market_data import _default_series_bar_condition
from app.services.tc_e2e_seed import seed_e2e_large_universe
from app.services.top_down_taxonomy import (
    BENCHMARK_FAMILY_REGISTRY,
    benchmark_family_proxy_symbols,
)

_RECENT_RRG_BAR_DIGESTS = {
    "SPY": "a5ab7b87e93d42e2d53df7aa24dd9bab96cf79b0a4a21fe531d5dfe8cf700d4c",
    "XLB": "6d95aa23d59528ca3625c4506d5f35c706124c69be93c1257f0c0f259b8dbd99",
    "XLC": "af0aad7e238da837ff2a6ab730b0c4784ec7cd46603fcc583185fbed76738e1b",
    "XLE": "4c54df16bf975ebbcc8c7ad853b7eaf57d085a39555a46f74004f8af949f21bd",
    "XLF": "2b5feefdfa7241666fe535c6a2b19704475218ebaa16d41275890530b96e035c",
    "XLI": "304209562dffec80d8bc0fae9499d52204c3a385de255955e3605055696b54a4",
    "XLK": "aa9ccb27afb48d9b8d4262d5d475f8b0f27f1162052f6e0135b72b7c95074beb",
    "XLP": "96af92858218fa157cdb1db7c786e4924ce5de21ec55df6bdb6ba535a93abe5c",
    "XLRE": "e5fc240fdc208bfe5d66a001f21e7d4459580310542c475303c5aa025972b8e3",
    "XLU": "9287590af736c88a3884caf6eee556640b19824df217135d0f31a00226f5336a",
    "XLV": "fcbd82585189ad1ddafba567dac2d12a1f0063f6ea982a32810fe3344420e634",
    "XLY": "a12681f2c9ec8d1938dfab23b1afb20276632be71628b36aeed7b64893ca5b86",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, -1, 10_001])
async def test_large_universe_rejects_unbounded_counts(count):
    with pytest.raises(ValueError, match="between 1 and 10000"):
        await seed_e2e_large_universe(None, count)  # type: ignore[arg-type]


def test_controlled_top_down_fixture_covers_all_select_sector_etfs():
    expected_sectors = {
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    }
    assert expected_sectors <= set(_E2E_HOLDINGS)
    assert all(holdings for holdings in _E2E_HOLDINGS.values())

    fixture_symbols = set(_E2E_MARKET_NAMES)
    holding_symbols = {symbol for holdings in _E2E_HOLDINGS.values() for symbol in holdings}
    assert holding_symbols <= fixture_symbols
    assert holding_symbols <= set(_E2E_INDUSTRIES)


def test_controlled_top_down_fixture_industry_labels_are_deterministic():
    assert _E2E_INDUSTRIES["NVDA"] == "Semiconductors"
    assert _E2E_INDUSTRIES["XOM"] == "Integrated Oil & Gas"
    assert _E2E_INDUSTRIES["JPM"] == "Diversified Banks"
    assert len(_E2E_INDUSTRIES) == len(set(_E2E_INDUSTRIES))


def test_controlled_fixture_covers_every_benchmark_family_leg():
    """The browser fixture must exercise the same universal source matrix as production."""

    configured_symbols = set(benchmark_family_proxy_symbols())
    assert configured_symbols <= set(_E2E_BENCHMARK_PROXY_NAMES)

    for family in BENCHMARK_FAMILY_REGISTRY:
        for role in ("cap_weight", "equal_weight", "value", "growth"):
            mapping = family.get(role) or {}
            symbol = mapping.get("symbol")
            if symbol:
                assert symbol in _E2E_HOLDINGS, (family["logical_key"], role, symbol)
                assert _E2E_HOLDINGS[symbol]
        derived_equal = family.get("derived_equal_weight") or {}
        cap_symbol = (family.get("cap_weight") or {}).get("symbol")
        if derived_equal.get("allowed"):
            assert cap_symbol in _E2E_HOLDINGS


@pytest.mark.asyncio
async def test_market_data_seed_performs_no_database_io_when_disabled(db, monkeypatch):
    from tests.unit.conftest import AsyncSessionAdapter

    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    statements = []
    engine = db.get_bind()

    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        await seed_e2e_market_data(AsyncSessionAdapter(db))
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert statements == []


@pytest.mark.asyncio
async def test_monthly_rrg_fixture_extends_only_controlled_top_down_history(db, monkeypatch):
    from app.models.data_source import DataSource
    from app.models.instrument import Instrument
    from app.models.ohlcv import OHLCVBar, Timeframe
    from app.models.provider_observation import InstrumentDatasetState
    from app.routers.analysis import _rotation_metrics
    from tests.unit.conftest import AsyncSessionAdapter

    class AsyncFixtureSession(AsyncSessionAdapter):
        async def scalar(self, *args, **kwargs):
            return self._session.scalar(*args, **kwargs)

    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", True)
    fixture_db = AsyncFixtureSession(db)
    await seed_e2e_instruments(fixture_db)

    # Reproduce the deployed reused-volume state: earlier E2E seeding inherited
    # the ORM's RAW basis default for adjusted bars, leaving canonical coarse
    # series that the adjusted read predicate must correctly reject.
    source = db.scalar(select(DataSource).where(DataSource.name == "e2e_reference"))
    if source is None:
        source = DataSource(
            name="e2e_reference",
            base_url="controlled://e2e",
            config={"controlled_fixture": True},
            supported_capabilities=["ohlcv", "etf_holdings"],
        )
        db.add(source)
        db.flush()
    spy = db.scalar(select(Instrument).where(Instrument.symbol == "SPY"))
    assert spy is not None
    stale_raw_series: dict[Timeframe, int] = {}
    for timeframe in (Timeframe.W1, Timeframe.MN):
        series = MarketSeries(
            instrument_id=spy.id,
            data_source_id=source.id,
            feed_scope=f"derived-d1-{source.id}",
            session_code="regular",
            timeframe=timeframe.value,
            adjustment_basis=AdjustmentBasis.RAW,
            adjustment_version="legacy",
            is_canonical=True,
            is_active=True,
        )
        db.add(series)
        db.flush()
        stale_raw_series[timeframe] = series.id
        db.add(
            OHLCVBar(
                instrument_id=spy.id,
                data_source_id=source.id,
                market_series_id=series.id,
                timeframe=timeframe,
                ts=datetime(2018, 12, 3 if timeframe == Timeframe.W1 else 1, tzinfo=UTC),
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("100"),
                is_adjusted=True,
                adjustment_basis=AdjustmentBasis.RAW,
                adjustment_version="legacy",
                is_derived=True,
                source_timeframe=Timeframe.D1.value,
                derivation_method="d1-aggregate-v1",
                scope_key=f"series:{series.id}:regular",
            )
        )
    db.flush()
    await seed_e2e_market_data(fixture_db)

    source = db.scalar(select(DataSource).where(DataSource.name == "e2e_reference"))
    assert source is not None
    assert source.config["controlled_fixture"] is True
    assert spy.identity_status == "resolved"
    assert spy.domain_key == "e2e:instrument:SPY"
    assert spy.field_provenance["controlled_fixture"] is True
    assert spy.field_provenance["identity"]["source"] == "e2e_reference"
    spy_listing = db.scalar(
        select(InstrumentListing).where(
            InstrumentListing.instrument_id == spy.id,
            InstrumentListing.ticker == "SPY",
            InstrumentListing.is_active.is_(True),
            InstrumentListing.is_primary.is_(True),
        )
    )
    assert spy_listing is not None
    assert spy_listing.currency == "USD"
    assert spy_listing.source == "e2e_reference"
    assert spy_listing.provenance["controlled_fixture"] is True
    daily_default = db.scalar(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == spy.id,
            MarketSeriesDefault.timeframe == Timeframe.D1.value,
            MarketSeriesDefault.is_adjusted.is_(True),
        )
    )
    assert daily_default is not None
    daily_series = db.get(MarketSeries, daily_default.market_series_id)
    assert daily_series is not None
    assert daily_series.data_source_id == source.id
    assert daily_series.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
    assert daily_series.adjustment_version == "e2e-split-adjusted-v1"
    assert daily_series.provenance["controlled_fixture"] is True
    original_rows = (
        db.query(OHLCVBar)
        .filter(OHLCVBar.market_series_id == daily_series.id)
        .order_by(OHLCVBar.ts)
        .all()
    )
    original_ids = [row.id for row in original_rows]
    original_values = [(row.ts, row.close) for row in original_rows]
    assert len(original_rows) > _E2E_RECENT_HISTORY_BARS

    intraday_default = db.scalar(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == spy.id,
            MarketSeriesDefault.timeframe == Timeframe.M15.value,
            MarketSeriesDefault.is_adjusted.is_(True),
        )
    )
    assert intraday_default is not None
    intraday_series = db.get(MarketSeries, intraday_default.market_series_id)
    assert intraday_series is not None
    assert intraday_default.market_series_id == intraday_series.id
    assert intraday_series.instrument_id == spy.id
    assert intraday_series.exchange_id == spy_listing.exchange_id
    assert intraday_series.data_source_id == source.id
    assert intraday_series.feed_scope == "e2e-reference"
    assert intraday_series.session_code == "regular"
    assert intraday_series.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
    assert intraday_series.adjustment_version == "e2e-split-adjusted-v1"
    assert intraday_series.provenance["controlled_fixture"] is True
    assert intraday_series.provenance["listing"] == {
        "listing_id": spy_listing.id,
        "ticker": "SPY",
        "exchange_id": spy_listing.exchange_id,
        "currency": "USD",
        "source": "e2e_reference",
    }
    intraday_rows = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.market_series_id == intraday_series.id,
            OHLCVBar.timeframe == Timeframe.M15,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(False),
        )
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert len(intraday_rows) == _E2E_INTRADAY_HISTORY_BARS
    intraday_times = [
        row.ts.replace(tzinfo=UTC) if row.ts.tzinfo is None else row.ts.astimezone(UTC)
        for row in intraday_rows
    ]
    assert intraday_times == sorted(set(intraday_times))
    local_times = [stamp.astimezone(ZoneInfo("America/New_York")) for stamp in intraday_times]
    assert all(
        (stamp.hour, stamp.minute) >= (9, 30)
        and (stamp.hour, stamp.minute) <= (15, 45)
        and stamp.minute % 15 == 0
        and stamp.second == 0
        for stamp in local_times
    )
    assert set(Counter(stamp.date() for stamp in local_times).values()) == {
        _E2E_INTRADAY_BARS_PER_SESSION
    }
    assert all(
        row.open.is_finite()
        and row.high.is_finite()
        and row.low.is_finite()
        and row.close.is_finite()
        and row.volume.is_finite()
        and row.low > 0
        and row.high >= max(row.open, row.close)
        and row.low <= min(row.open, row.close)
        and row.volume > 0
        and row.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
        and row.adjustment_version == "e2e-split-adjusted-v1"
        and row.market_series_id == intraday_series.id
        for row in intraday_rows
    )
    intraday_ids = [row.id for row in intraday_rows]
    intraday_values = [
        (row.ts, row.open, row.high, row.low, row.close, row.volume) for row in intraday_rows
    ]
    intraday_state = db.scalar(
        select(InstrumentDatasetState).where(
            InstrumentDatasetState.instrument_id == spy.id,
            InstrumentDatasetState.data_source_id == source.id,
            InstrumentDatasetState.dataset_key == "M15:adj",
        )
    )
    assert intraday_state is not None
    assert intraday_state.extra_data["controlled_fixture"] is True
    assert intraday_state.extra_data["listing_id"] == spy_listing.id
    assert intraday_state.extra_data["market_series_id"] == intraday_series.id
    assert intraday_state.extra_data["bar_count"] == _E2E_INTRADAY_HISTORY_BARS

    # Re-running controlled startup retains existing rows without deletion or
    # duplicate insertion, including the same canonical series mapping.
    await seed_e2e_market_data(fixture_db)
    repeated_rows = (
        db.query(OHLCVBar)
        .filter(OHLCVBar.market_series_id == daily_series.id)
        .order_by(OHLCVBar.ts)
        .all()
    )
    assert [row.id for row in repeated_rows] == original_ids
    assert [(row.ts, row.close) for row in repeated_rows] == original_values
    repeated_intraday = (
        db.query(OHLCVBar)
        .filter(OHLCVBar.market_series_id == intraday_series.id)
        .order_by(OHLCVBar.ts)
        .all()
    )
    repeated_intraday_default = db.scalar(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == spy.id,
            MarketSeriesDefault.timeframe == Timeframe.M15.value,
            MarketSeriesDefault.is_adjusted.is_(True),
        )
    )
    assert repeated_intraday_default is not None
    assert repeated_intraday_default.market_series_id == intraday_series.id
    assert [row.id for row in repeated_intraday] == intraday_ids
    assert [
        (row.ts, row.open, row.high, row.low, row.close, row.volume) for row in repeated_intraday
    ] == intraday_values
    assert set(_E2E_MONTHLY_RRG_SYMBOLS) == set(_RECENT_RRG_BAR_DIGESTS)
    assert _E2E_LONG_RRG_START < _E2E_RECENT_HISTORY_START

    series_by_symbol: dict[str, dict[Timeframe, list[OHLCVBar]]] = {}
    recent_start = datetime.combine(_E2E_RECENT_HISTORY_START, datetime.min.time(), tzinfo=UTC)
    for symbol in _E2E_MONTHLY_RRG_SYMBOLS:
        instrument = db.scalar(select(Instrument).where(Instrument.symbol == symbol))
        assert instrument is not None
        recent = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.data_source_id == source.id,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.ts >= recent_start,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(False),
            )
            .order_by(OHLCVBar.ts)
            .all()
        )
        assert len(recent) == _E2E_RECENT_HISTORY_BARS

        def fixed(value: Decimal) -> str:
            return format(value.quantize(Decimal("0.00000001")), "f")

        recent_rows = [
            [
                (bar.ts if bar.ts.tzinfo else bar.ts.replace(tzinfo=UTC)).isoformat(),
                fixed(bar.open),
                fixed(bar.high),
                fixed(bar.low),
                fixed(bar.close),
                str(int(bar.volume)),
            ]
            for bar in recent
        ]
        digest = hashlib.sha256(
            json.dumps(recent_rows, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        assert digest == _RECENT_RRG_BAR_DIGESTS[symbol]

        full_daily = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.data_source_id == source.id,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(False),
            )
            .order_by(OHLCVBar.ts)
            .all()
        )
        full_daily_count = len(full_daily)
        assert full_daily_count > _E2E_RECENT_HISTORY_BARS
        assert all(
            bar.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
            and bar.adjustment_version == "e2e-split-adjusted-v1"
            for bar in full_daily
        )

        monthly = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.MN,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(True),
                _default_series_bar_condition(instrument.id, Timeframe.MN, True),
            )
            .order_by(OHLCVBar.ts)
            .all()
        )
        assert len(monthly) >= 60
        assert monthly[0].source_timeframe == Timeframe.D1.value
        assert monthly[0].data_source_id == source.id
        assert monthly[0].ts.year == _E2E_LONG_RRG_START.year
        assert all(
            row.source_timeframe == Timeframe.D1.value and row.data_source_id == source.id
            for row in monthly
        )

        weekly = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.W1,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(True),
                _default_series_bar_condition(instrument.id, Timeframe.W1, True),
            )
            .order_by(OHLCVBar.ts)
            .all()
        )
        assert len(weekly) > len(monthly)
        assert weekly[0].source_timeframe == Timeframe.D1.value
        assert all(row.data_source_id == source.id for row in weekly)
        for timeframe, derived_rows in ((Timeframe.W1, weekly), (Timeframe.MN, monthly)):
            selected = db.scalar(
                select(MarketSeriesDefault).where(
                    MarketSeriesDefault.instrument_id == instrument.id,
                    MarketSeriesDefault.timeframe == timeframe.value,
                    MarketSeriesDefault.is_adjusted.is_(True),
                )
            )
            assert selected is not None, (symbol, timeframe)
            assert {row.market_series_id for row in derived_rows} == {selected.market_series_id}
            selected_series = db.get(MarketSeries, selected.market_series_id)
            assert selected_series is not None
            assert selected_series.data_source_id == source.id
            assert selected_series.is_canonical is True
            assert selected_series.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
            assert selected_series.adjustment_version == "e2e-split-adjusted-v1"

            # This is the same selected-series and adjustment predicate used
            # by canonical local reads, with the fixture's source isolation.
            visible_rows = (
                db.query(OHLCVBar)
                .filter(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(True),
                    OHLCVBar.data_source_id == source.id,
                    _default_series_bar_condition(instrument.id, timeframe, True),
                )
                .order_by(OHLCVBar.ts)
                .all()
            )
            assert [row.id for row in visible_rows] == [row.id for row in derived_rows]
        if symbol == "SPY":
            for timeframe, series_id in stale_raw_series.items():
                legacy_series = db.get(MarketSeries, series_id)
                assert legacy_series is not None
                assert legacy_series.adjustment_basis == AdjustmentBasis.RAW
                legacy_row = db.query(OHLCVBar).filter(OHLCVBar.market_series_id == series_id).one()
                assert legacy_row.is_adjusted is True
                assert legacy_row.adjustment_basis == AdjustmentBasis.RAW
        series_by_symbol[symbol] = {
            Timeframe.D1: full_daily,
            Timeframe.W1: weekly,
            Timeframe.MN: monthly,
        }

        state = db.scalar(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.data_source_id == source.id,
                InstrumentDatasetState.dataset_key == "D1:adj",
            )
        )
        assert state is not None
        assert state.extra_data["controlled_fixture"] is True
        assert state.extra_data["extended_monthly_rrg_history"] is True
        assert state.extra_data["bar_count"] == full_daily_count

    benchmark_by_timeframe = {
        timeframe: {bar.ts: bar.close for bar in series_by_symbol["SPY"][timeframe]}
        for timeframe in (Timeframe.D1, Timeframe.W1, Timeframe.MN)
    }
    for timeframe in (Timeframe.D1, Timeframe.W1, Timeframe.MN):
        benchmark = benchmark_by_timeframe[timeframe]
        for symbol in _E2E_MONTHLY_RRG_SYMBOLS[1:]:
            aligned = [
                (bar.ts, float(bar.close / benchmark[bar.ts]))
                for bar in series_by_symbol[symbol][timeframe]
                if bar.ts in benchmark and benchmark[bar.ts] != 0
            ]
            # Default 20-period trend and momentum windows yield ten tail
            # observations only once at least 50 aligned points are present.
            assert len(aligned) >= 50, (symbol, timeframe, len(aligned))
            metrics, tail, _, warnings = _rotation_metrics(
                aligned, sampling=1, lookback=20, tail_length=10
            )
            assert metrics is not None, (symbol, timeframe, warnings)
            assert len(tail) == 10
            assert all(
                math.isfinite(point.trend) and math.isfinite(point.momentum) for point in tail
            )
            assert all(
                math.isfinite(float(metrics[key]))
                for key in ("trend", "momentum", "heading", "distance", "velocity")
            )

    nvda = db.scalar(select(Instrument).where(Instrument.symbol == "NVDA"))
    assert nvda is not None
    nvda_daily = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == nvda.id,
            OHLCVBar.data_source_id == source.id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(False),
        )
        .count()
    )
    nvda_monthly = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == nvda.id,
            OHLCVBar.timeframe == Timeframe.MN,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(True),
        )
        .count()
    )
    assert nvda_daily == _E2E_RECENT_HISTORY_BARS
    assert nvda_monthly == 0
