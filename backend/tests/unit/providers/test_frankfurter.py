"""Frankfurter FX reference-rate adapter, registry wiring, and discovery."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.ohlcv import Timeframe
from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.providers.frankfurter import (
    FRANKFURTER_BASE_URL,
    FrankfurterProvider,
    estimate_frankfurter_latest_ohlcv_request_count,
    estimate_frankfurter_ohlcv_request_count,
    market_convention_pair,
    parse_frankfurter_pair,
)
from app.providers.registry import (
    get_provider_usage_profile,
    list_provider_capabilities,
    provider_is_configured,
    provider_missing_routing_controls,
    provider_rate_limit_seed,
    provider_supports_adjustment,
    provider_supports_instrument,
    supported_provider_names,
)
from app.providers.telemetry import activate, deactivate
from app.services.market_data import ohlcv_operation_cost_overrides
from tests.unit.conftest import AsyncSessionAdapter

_HTTPX_GET = "app.providers.frankfurter.httpx.get"


def _response(payload, *, status_code: int = 200, headers: dict[str, str] | None = None):
    request = httpx.Request("GET", f"{FRANKFURTER_BASE_URL}/rates")
    response = MagicMock()
    response.status_code = status_code
    response.content = b"provider-payload"
    response.headers = headers or {}
    response.json.return_value = payload
    response.text = "payload"
    if status_code >= 400:
        real = httpx.Response(status_code, json=payload, request=request, headers=headers)
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=request, response=real
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _row(day: str, rate: float, base: str = "EUR", quote: str = "USD") -> dict:
    return {"date": day, "base": base, "quote": quote, "rate": rate}


def _currency(code: str, name: str, kind: str = "currency") -> dict:
    return {
        "iso_code": code,
        "iso_numeric": None,
        "name": name,
        "symbol": code,
        "type": kind,
        "start_date": "1999-01-04",
        "end_date": "2026-11-19",
    }


_CURRENCIES = [
    _currency("AUD", "Australian Dollar"),
    _currency("BTC", "Bitcoin", "crypto"),
    _currency("CAD", "Canadian Dollar"),
    _currency("CHF", "Swiss Franc"),
    _currency("EUR", "Euro"),
    _currency("GBP", "British Pound"),
    _currency("JPY", "Japanese Yen"),
    _currency("MXN", "Mexican Peso"),
    _currency("NZD", "New Zealand Dollar"),
    _currency("USD", "United States Dollar"),
    _currency("XAU", "Gold (Troy Ounce)", "metal"),
]


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("EURUSD", ("EUR", "USD")),
        ("eur/usd", ("EUR", "USD")),
        ("EUR-USD", ("EUR", "USD")),
        ("EURUSD=X", ("EUR", "USD")),
        ("usdjpy", ("USD", "JPY")),
        ("AAPL", None),
        ("USDUSD", None),
        ("EU1USD", None),
        ("BTC-USDT", None),
    ],
)
def test_pair_parser_accepts_the_platform_forex_spellings(symbol, expected):
    assert parse_frankfurter_pair(symbol) == expected


def test_market_convention_orients_pairs_by_interbank_priority():
    assert market_convention_pair("USD", "EUR") == ("EUR", "USD")
    assert market_convention_pair("JPY", "USD") == ("USD", "JPY")
    assert market_convention_pair("USD", "MXN") == ("USD", "MXN")
    assert market_convention_pair("CHF", "CAD") == ("CAD", "CHF")
    assert market_convention_pair("NZD", "AUD") == ("AUD", "NZD")


def test_history_builds_flat_daily_raw_bars_for_requested_weekdays_only():
    payload = [
        # Frankfurter carries the last observation before ``from`` into range
        # responses; it is outside the requested window and must be dropped.
        _row("2026-11-06", 1.08),
        _row("2026-11-09", 1.09),
        _row("2026-11-10", 1.1),
        # Blended rates exist on weekends; FX daily bars follow Mon-Fri.
        _row("2026-11-14", 1.2),
        _row("2026-11-15", 1.21),
        _row("2026-11-16", 1.11),
    ]
    with patch(_HTTPX_GET, return_value=_response(payload)) as get:
        bars = FrankfurterProvider().fetch_ohlcv(
            "EUR/USD",
            Timeframe.D1,
            datetime(2026, 11, 9, tzinfo=UTC),
            datetime(2026, 11, 17, tzinfo=UTC),
            adjusted=False,
            instrument_id=7,
            data_source_id=3,
        )

    get.assert_called_once()
    assert get.call_args.args[0] == f"{FRANKFURTER_BASE_URL}/rates"
    assert get.call_args.kwargs["params"] == {
        "base": "EUR",
        "quotes": "USD",
        "from": "2026-11-09",
        "to": "2026-11-16",
    }
    assert [bar.ts for bar in bars] == [
        datetime(2026, 11, 9, tzinfo=UTC),
        datetime(2026, 11, 10, tzinfo=UTC),
        datetime(2026, 11, 16, tzinfo=UTC),
    ]
    first = bars[0]
    assert first.open == first.high == first.low == first.close == 1.09
    assert first.volume is None
    assert first.instrument_id == 7 and first.data_source_id == 3
    assert first.timeframe is Timeframe.D1
    assert first.is_adjusted is False
    assert first.adjustment_basis == "raw"
    assert first.adjustment_version == "provider-native"
    assert first.provenance["provider"] == "frankfurter"
    assert first.provenance["endpoint"] == "/v2/rates"
    assert first.provenance["provider_symbol"] == "EURUSD"
    assert first.provenance["provider_payload"] == _row("2026-11-09", 1.09)


def test_history_end_is_exclusive_and_intraday_start_skips_its_own_midnight_bar():
    with patch(_HTTPX_GET, return_value=_response([])) as get:
        FrankfurterProvider().fetch_ohlcv(
            "USDJPY",
            Timeframe.D1,
            datetime(2026, 11, 9, 12, tzinfo=UTC),
            datetime(2026, 11, 13, 0, 0, 1, tzinfo=UTC),
            adjusted=False,
        )
    params = get.call_args.kwargs["params"]
    assert (params["from"], params["to"]) == ("2026-11-10", "2026-11-13")


def test_long_history_is_chunked_and_matches_the_reserved_request_count():
    start = datetime(1990, 1, 1, tzinfo=UTC)
    end = datetime(2026, 11, 19, tzinfo=UTC)
    calls: list[dict] = []

    def fake_get(url, *, params, timeout):
        calls.append(dict(params))
        first = date.fromisoformat(params["from"])
        weekday = first + timedelta(days=(7 - first.weekday()) % 7)
        return _response([_row(weekday.isoformat(), 1.0, "USD", "CHF")])

    with patch(_HTTPX_GET, side_effect=fake_get):
        bars = FrankfurterProvider().fetch_ohlcv("USDCHF", Timeframe.D1, start, end, adjusted=False)

    assert len(calls) == estimate_frankfurter_ohlcv_request_count(Timeframe.D1, start, end) == 4
    assert calls[0]["from"] == "1990-01-01"
    assert calls[-1]["to"] == "2026-11-18"
    for previous, current in zip(calls, calls[1:], strict=False):
        assert date.fromisoformat(current["from"]) == (
            date.fromisoformat(previous["to"]) + timedelta(days=1)
        )
        span = date.fromisoformat(previous["to"]) - date.fromisoformat(previous["from"])
        assert span.days + 1 == 3653
    assert len(bars) == 4
    assert bars == sorted(bars, key=lambda bar: bar.ts)


def test_request_estimates_are_daily_only_and_exact():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert estimate_frankfurter_ohlcv_request_count(Timeframe.D1, start, start) == 0
    assert (
        estimate_frankfurter_ohlcv_request_count(Timeframe.D1, start, start + timedelta(days=3653))
        == 1
    )
    assert (
        estimate_frankfurter_ohlcv_request_count(Timeframe.D1, start, start + timedelta(days=3654))
        == 2
    )
    assert estimate_frankfurter_ohlcv_request_count(Timeframe.H1, start, start) is None
    assert estimate_frankfurter_ohlcv_request_count(Timeframe.W1, start, start) is None
    assert estimate_frankfurter_latest_ohlcv_request_count(Timeframe.D1, 0) == 0
    assert estimate_frankfurter_latest_ohlcv_request_count(Timeframe.D1, 1) == 1
    assert estimate_frankfurter_latest_ohlcv_request_count(Timeframe.D1, 2000) == 1
    assert estimate_frankfurter_latest_ohlcv_request_count(Timeframe.MN, 5) is None


def test_market_data_cost_overrides_include_frankfurter_history_estimate():
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    assert ohlcv_operation_cost_overrides(Timeframe.D1, start, end)["frankfurter"] == 3
    assert "frankfurter" not in ohlcv_operation_cost_overrides(Timeframe.H1, start, end)


@pytest.mark.parametrize("timeframe", [Timeframe.H1, Timeframe.W1, Timeframe.MN, Timeframe.Y1])
def test_non_daily_timeframes_are_rejected_before_transport(timeframe):
    provider = FrankfurterProvider()
    now = datetime.now(UTC)
    with patch(_HTTPX_GET) as get:
        with pytest.raises(ProviderResponseError, match="unsupported reference-rate timeframe"):
            provider.fetch_ohlcv("EURUSD", timeframe, now - timedelta(days=5), now, adjusted=False)
        with pytest.raises(ProviderResponseError):
            provider.fetch_latest_ohlcv("EURUSD", timeframe, 5, adjusted=False)
        with pytest.raises(ProviderResponseError):
            provider.latest_window_start(timeframe, 5)
    get.assert_not_called()


def test_adjusted_history_is_rejected_and_non_pairs_make_no_request():
    provider = FrankfurterProvider()
    now = datetime.now(UTC)
    with patch(_HTTPX_GET) as get:
        with pytest.raises(ProviderResponseError, match="adjusted=False"):
            provider.fetch_ohlcv("EURUSD", Timeframe.D1, now - timedelta(days=5), now)
        assert (
            provider.fetch_ohlcv("AAPL", Timeframe.D1, now - timedelta(days=5), now, adjusted=False)
            == []
        )
        assert provider.fetch_ohlcv("EURUSD", Timeframe.D1, now, now, adjusted=False) == []
        assert provider.get_current_price("AAPL") is None
    get.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"date": "2026-11-10"}, "invalid rates array"),
        ([_row("2026-11-10", 1.1, "GBP", "USD")], "different currency pair"),
        ([_row("2026-11-10", "nan")], "invalid rate"),
        ([_row("2026-11-10", 0)], "invalid rate"),
        ([_row("2026-11-10", True)], "invalid rate"),
        ([_row("not-a-date", 1.1)], "invalid rate date"),
        (["2026-11-10"], "non-object rate row"),
    ],
)
def test_malformed_rate_payloads_fail_closed(payload, message):
    with patch(_HTTPX_GET, return_value=_response(payload)):
        with pytest.raises(ProviderResponseError, match=message):
            FrankfurterProvider().fetch_ohlcv(
                "EURUSD",
                Timeframe.D1,
                datetime(2026, 11, 9, tzinfo=UTC),
                datetime(2026, 11, 12, tzinfo=UTC),
                adjusted=False,
            )


def test_capacity_and_client_errors_are_typed():
    provider = FrankfurterProvider()
    with patch(
        _HTTPX_GET,
        return_value=_response(
            {"status": 429, "message": "slow down"},
            status_code=429,
            headers={"retry-after": "30"},
        ),
    ):
        with pytest.raises(ProviderRateLimitError) as rate_limited:
            provider.get_current_price("EURUSD")
    assert rate_limited.value.status_code == 429
    assert rate_limited.value.retry_at is not None

    with patch(
        _HTTPX_GET,
        return_value=_response(
            {"status": 422, "message": "invalid currency: ABC"}, status_code=422
        ),
    ):
        with pytest.raises(ProviderResponseError, match="invalid currency: ABC") as rejected:
            provider.get_current_price("ABCUSD")
    assert rejected.value.status_code == 422

    with patch(_HTTPX_GET, side_effect=httpx.ConnectError("boom")):
        with pytest.raises(ProviderResponseError, match="boom"):
            provider.get_current_price("EURUSD")


def test_current_price_reads_the_single_pair_endpoint():
    with patch(
        _HTTPX_GET,
        return_value=_response(_row("2026-11-19", 159.49, "USD", "JPY")),
    ) as get:
        assert FrankfurterProvider().get_current_price("USDJPY=X") == 159.49
    assert get.call_args.args[0] == f"{FRANKFURTER_BASE_URL}/rate/USD/JPY"

    with patch(_HTTPX_GET, return_value=_response(_row("2026-11-19", 0.9, "USD", "EUR"))):
        with pytest.raises(ProviderResponseError, match="different currency pair"):
            FrankfurterProvider().get_current_price("USDJPY")


def test_latest_bars_use_a_weekday_padded_daily_window():
    provider = FrankfurterProvider()
    before = datetime.now(UTC)
    window_start = provider.latest_window_start(Timeframe.D1, 10)
    assert timedelta(days=27) <= before - window_start <= timedelta(days=29)

    rows = [
        _row((date.today() - timedelta(days=offset)).isoformat(), 1.0 + offset / 100)
        for offset in range(20, 0, -1)
    ]
    with patch(_HTTPX_GET, return_value=_response(rows)) as get:
        bars = provider.fetch_latest_ohlcv("EURUSD", Timeframe.D1, 3, adjusted=False)
    get.assert_called_once()
    assert len(bars) == 3
    assert all(bar.ts.weekday() < 5 for bar in bars)
    assert bars == sorted(bars, key=lambda bar: bar.ts)
    assert provider.fetch_latest_ohlcv("EURUSD", Timeframe.D1, 0, adjusted=False) == []


def test_discovery_emits_usd_pairs_and_major_crosses_in_market_convention():
    with patch(_HTTPX_GET, return_value=_response(_CURRENCIES)) as get:
        page = FrankfurterProvider().discover_universe_page("currency", 0)
    get.assert_called_once()
    assert get.call_args.args[0] == f"{FRANKFURTER_BASE_URL}/currencies"

    symbols = [quote["symbol"] for quote in page["quotes"]]
    usd_pairs = {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "USDMXN"}
    crosses = {
        "EURGBP",
        "EURAUD",
        "EURNZD",
        "EURCAD",
        "EURCHF",
        "EURJPY",
        "GBPAUD",
        "GBPNZD",
        "GBPCAD",
        "GBPCHF",
        "GBPJPY",
        "AUDNZD",
        "AUDCAD",
        "AUDCHF",
        "AUDJPY",
        "NZDCAD",
        "NZDCHF",
        "NZDJPY",
        "CADCHF",
        "CADJPY",
        "CHFJPY",
    }
    assert set(symbols) == usd_pairs | crosses
    assert symbols == sorted(symbols)
    assert page["total"] == len(symbols) == 29
    assert page["next_offset"] is None and page["complete"] is True
    by_symbol = {quote["symbol"]: quote for quote in page["quotes"]}
    assert by_symbol["USDJPY"] == {
        "symbol": "USDJPY",
        "longName": "United States Dollar / Japanese Yen",
        "exchange": "Frankfurter",
        "quoteType": "CURRENCY",
        "currency": "JPY",
        "base_currency": "USD",
        "quote_currency": "JPY",
        "status": "active",
        "source_record": {
            "base": _currency("USD", "United States Dollar"),
            "quote": _currency("JPY", "Japanese Yen"),
        },
    }
    # Every emitted pair parses with the platform forex convention.
    assert all(parse_frankfurter_pair(symbol) for symbol in symbols)


def test_discovery_pages_and_rejects_unusable_listings():
    provider = FrankfurterProvider()
    with patch(_HTTPX_GET) as get:
        assert provider.discover_universe_page("CRYPTOCURRENCY", 0) == {"total": 0, "quotes": []}
    get.assert_not_called()

    with patch(_HTTPX_GET, return_value=_response(_CURRENCIES)):
        tail = provider.discover_universe_page("CURRENCY", 28)
    assert [quote["symbol"] for quote in tail["quotes"]] == ["USDMXN"]
    assert tail["complete"] is True

    without_usd = [item for item in _CURRENCIES if item["iso_code"] != "USD"]
    with patch(_HTTPX_GET, return_value=_response(without_usd)):
        with pytest.raises(ProviderResponseError, match="omitted USD"):
            provider.discover_universe_page("CURRENCY", 0)
    with patch(_HTTPX_GET, return_value=_response({"currencies": []})):
        with pytest.raises(ProviderResponseError, match="invalid currencies array"):
            provider.discover_universe_page("CURRENCY", 0)
    bad_code = [*_CURRENCIES, _currency("E1R", "Broken")]
    with patch(_HTTPX_GET, return_value=_response(bad_code)):
        with pytest.raises(ProviderResponseError, match="incomplete currency identity"):
            provider.discover_universe_page("CURRENCY", 0)
    assert provider.supported_discovery_types() == ["CURRENCY"]


def test_transport_is_reported_to_runtime_measurement():
    measurement, token = activate()
    try:
        with patch(_HTTPX_GET, return_value=_response(_row("2026-11-19", 1.1))):
            FrankfurterProvider().get_current_price("EURUSD")
    finally:
        deactivate(token)
    assert measurement.http_requests == 1
    assert measurement.response_bytes == len(b"provider-payload")


def test_registry_wires_a_keyless_fx_only_raw_history_provider():
    assert "frankfurter" in supported_provider_names()
    assert list_provider_capabilities("frankfurter") == [
        "price_history",
        "latest_price",
        "universe_discovery",
    ]
    assert provider_is_configured("frankfurter") is True
    for operation in (None, "fetch_ohlcv", "get_current_price", "reconcile_universe_page"):
        assert provider_missing_routing_controls("frankfurter", operation) == []
    assert provider_supports_instrument(
        "frankfurter", asset_class="Currency", instrument_type="Forex Pair"
    )
    assert not provider_supports_instrument(
        "frankfurter", asset_class="Equity", instrument_type="Stock"
    )
    assert not provider_supports_instrument(
        "frankfurter", asset_class="Cryptocurrency", instrument_type="Crypto Spot"
    )
    assert provider_supports_adjustment("frankfurter", False)
    assert not provider_supports_adjustment("frankfurter", True)


def test_frankfurter_seeds_are_documented_and_admissible():
    seed = provider_rate_limit_seed("frankfurter")
    (dimension,) = seed["quota_contract"]["dimensions"]
    assert dimension["limit"] == 60 and dimension["window_seconds"] == 60
    assert dimension["source"] == "https://frankfurter.dev/docs"
    assert dimension["baseline_mode"] == "local_zero"
    assert dimension["application_usage_only"] is True
    assert dimension["limit_basis"].startswith("application_policy:")
    assert seed["quota_contract"]["reset"] == "rolling"
    assert seed["quota_scope"] == "ip"

    assert get_provider_usage_profile("frankfurter")["operation_costs"] == {
        "get_current_price": 1,
        "discover_universe_page": 1,
        "reconcile_universe_page": 1,
    }

    entitlement = settings.PROVIDER_ENTITLEMENT_SEEDS["frankfurter"]
    assert entitlement["is_free"] is True
    assert entitlement["authentication_required"] is False
    assert "commercially" in entitlement["usage_terms"]
    assert "https://frankfurter.dev/docs" in entitlement["usage_terms"]
    assert entitlement["quota_policy"]["history_constraints"]["earliest_date"] == "1948-06-21"
    assert settings.PROVIDER_LIVE_PROBE_STATUS_SEEDS["frankfurter"] == "passed"
    for chain in ("price_history", "latest_price", "universe_discovery"):
        assert settings.PROVIDER_CHAIN_SEEDS[chain][-1] == "frankfurter"


@pytest.mark.asyncio
async def test_reconciliation_dispatches_currency_discovery_into_forex_pairs(db, monkeypatch):
    from app.services import market_universe

    source = DataSource(name="frankfurter", base_url=FRANKFURTER_BASE_URL)
    db.add(source)
    db.flush()
    provider = FrankfurterProvider()
    resolved = [SimpleNamespace(provider_name="frankfurter", data_source=source)]
    requested_types: list[str] = []

    async def resolve_fixture(*_args, **kwargs):
        assert kwargs["operation"] == "reconcile_universe_page"
        return resolved

    async def execute_fixture(_db, _capability, operation, *, invoke, **_kwargs):
        requested_types.append(operation.split(":")[1])
        return SimpleNamespace(result=invoke(provider, None), data_source=source)

    monkeypatch.setattr(market_universe, "resolve_provider_chain", resolve_fixture)
    monkeypatch.setattr(market_universe, "get_discovery_provider", lambda _name: provider)
    monkeypatch.setattr(market_universe, "execute_provider_call", execute_fixture)

    with patch(_HTTPX_GET, return_value=_response(_CURRENCIES)):
        result = await market_universe.reconcile_us_universe(AsyncSessionAdapter(db))

    assert requested_types == ["CURRENCY"]
    assert result["status"] == "complete"
    usdjpy = db.query(Instrument).filter(Instrument.symbol == "USDJPY").one()
    assert usdjpy.currency == "JPY"
    assert usdjpy.instrument_type.name == "Forex Pair"
    assert usdjpy.instrument_type.asset_class.name == "Currency"
    assert provider_supports_instrument(
        "frankfurter",
        asset_class=usdjpy.instrument_type.asset_class.name,
        instrument_type=usdjpy.instrument_type.name,
    )
    alias = (
        db.query(InstrumentProviderSymbol)
        .filter(
            InstrumentProviderSymbol.data_source_id == source.id,
            InstrumentProviderSymbol.provider_symbol == "USDJPY",
        )
        .one()
    )
    assert alias.instrument_id == usdjpy.id
    assert db.query(Instrument).filter(Instrument.symbol.in_(["EURUSD", "CHFJPY"])).count() == 2
