import hashlib
import json
import math
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.services.e2e_seed import (
    _E2E_BENCHMARK_PROXY_NAMES,
    _E2E_HOLDINGS,
    _E2E_INDUSTRIES,
    _E2E_LONG_RRG_START,
    _E2E_MARKET_NAMES,
    _E2E_MONTHLY_RRG_SYMBOLS,
    _E2E_RECENT_HISTORY_BARS,
    _E2E_RECENT_HISTORY_START,
    seed_e2e_instruments,
    seed_e2e_market_data,
)
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
async def test_monthly_rrg_fixture_extends_only_controlled_top_down_history(db):
    from app.models.data_source import DataSource
    from app.models.instrument import Instrument
    from app.models.ohlcv import OHLCVBar, Timeframe
    from app.models.provider_observation import InstrumentDatasetState
    from app.routers.analysis import _rotation_metrics
    from tests.unit.conftest import AsyncSessionAdapter

    class AsyncFixtureSession(AsyncSessionAdapter):
        async def scalar(self, *args, **kwargs):
            return self._session.scalar(*args, **kwargs)

    fixture_db = AsyncFixtureSession(db)
    await seed_e2e_instruments(fixture_db)
    await seed_e2e_market_data(fixture_db)

    source = db.scalar(select(DataSource).where(DataSource.name == "e2e_reference"))
    assert source is not None
    assert source.config["controlled_fixture"] is True
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

        monthly = (
            db.query(OHLCVBar)
            .filter(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.MN,
                OHLCVBar.is_adjusted.is_(True),
                OHLCVBar.is_derived.is_(True),
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
            )
            .order_by(OHLCVBar.ts)
            .all()
        )
        assert len(weekly) > len(monthly)
        assert weekly[0].source_timeframe == Timeframe.D1.value
        assert all(row.data_source_id == source.id for row in weekly)
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
