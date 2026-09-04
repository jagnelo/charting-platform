from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.models.instrument_identity import InstrumentIdentifierType
from app.models.ohlcv import Timeframe
from app.services.bar_aggregation import aggregate_bars
from app.services.market_data_identity import choose_domain_key, make_domain_key
from app.services.market_series import SeriesScope, series_key


def test_figi_domain_key_is_namespaced_and_normalized():
    assert make_domain_key(InstrumentIdentifierType.FIGI, " bbg000b9xry4 ") == "figi:BBG000B9XRY4"
    assert choose_domain_key({"isin": "us0378331005", "figi": "bbg000b9xry4"}) == "figi:BBG000B9XRY4"


def test_internal_or_unknown_identifiers_do_not_become_domain_keys():
    assert make_domain_key(InstrumentIdentifierType.INTERNAL, "instrument:1") is None
    assert choose_domain_key({"internal": "instrument:1", "unknown": "x"}) is None


def test_series_key_contains_scope_and_adjustment():
    scope = SeriesScope(
        instrument_id=7,
        exchange_id=12,
        data_source_id=3,
        feed_scope="sip",
        session_code="post",
        timeframe="M5",
        adjustment_version="split-2026-01",
    )
    assert series_key(scope) == "7:12:3:sip:post:M5:raw:split-2026-01"


def test_local_rollup_emits_only_observed_buckets():
    bars = [
        SimpleNamespace(
            ts=datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
            session="regular",
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10.5"),
            volume=Decimal("2"),
            is_adjusted=False,
            adjustment_basis="raw",
            adjustment_version="v1",
        ),
        SimpleNamespace(
            ts=datetime(2026, 1, 2, 14, 32, tzinfo=UTC),
            session="regular",
            open=Decimal("10.5"),
            high=Decimal("12"),
            low=Decimal("10"),
            close=Decimal("11.5"),
            volume=Decimal("3"),
            is_adjusted=False,
            adjustment_basis="raw",
            adjustment_version="v1",
        ),
    ]
    result = aggregate_bars(bars, Timeframe.M5)
    assert len(result) == 1
    assert result[0]["open"] == Decimal("10")
    assert result[0]["close"] == Decimal("11.5")
    assert result[0]["high"] == Decimal("12")
    assert result[0]["volume"] == Decimal("5")
