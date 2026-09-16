"""Bounded, opt-in provider probes.

These tests perform one deliberately small read per provider and assert a
provider-native response shape. They are never part of ordinary unit runs.
Missing credentials are failures when live mode is explicitly enabled, not
silently skipped evidence.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import settings
from app.models.ohlcv import Timeframe
from app.providers.alpaca import (
    AlpacaProvider,
)
from app.providers.alpaca import (
    estimate_ohlcv_request_count as estimate_alpaca_ohlcv_request_count,
)
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.binance import (
    BinanceProvider,
    estimate_latest_ohlcv_request_weight,
)
from app.providers.coingecko import CoinGeckoProvider
from app.providers.crypto_market_data import (
    CoinbaseProvider,
    KrakenProvider,
    estimate_coinbase_latest_ohlcv_request_count,
    estimate_kraken_latest_ohlcv_request_count,
)
from app.providers.edgar import EdgarProvider
from app.providers.errors import ProviderResponseError
from app.providers.finra import FINRAProvider
from app.providers.finra_otc_directory import FINRAOTCDirectoryProvider
from app.providers.fred import FREDProvider
from app.providers.ibkr import IBKRProvider
from app.providers.massive import (
    MassiveProvider,
)
from app.providers.massive import (
    estimate_ohlcv_request_count as estimate_massive_ohlcv_request_count,
)
from app.providers.nasdaq import NasdaqProvider
from app.providers.openfigi import OpenFigiProvider
from app.providers.optional_market_data import (
    EODHDProvider,
    FinnhubProvider,
    FMPProvider,
    MarketDataAppProvider,
    MarketstackProvider,
    TiingoProvider,
    TradierProvider,
    TwelveDataProvider,
    estimate_marketdata_app_ohlcv_credit_count,
    estimate_marketdata_app_option_quote_history_credit_count,
    estimate_marketstack_ohlcv_request_count,
)
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from tests.live.live_usage import (
    activate_request_admission,
    deactivate_request_admission,
    reconcile_native_account_usage,
    record_observation,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1",
        reason="Set RUN_LIVE_PROVIDER_TESTS=1 to run the external provider matrix.",
    ),
]


def _bounds() -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(days=5), end


def _require(*names: str) -> None:
    missing = []
    for name in names:
        value = os.getenv(name, "").strip()
        if not value or (
            name == "EDGAR_USER_AGENT"
            and any(
                marker in value.lower()
                for marker in ("example.com", "myemail@", "your.email", "<", ">")
            )
        ):
            missing.append(name)
    if missing:
        pytest.fail(f"missing live provider credentials: {', '.join(missing)}")


def _skip_unadmitted_live_operation(provider_name: str, operation: str) -> None:
    """Skip an opt-in probe before adapter access when quota policy is unknown."""

    from app.services.provider_quota_coordinator import (
        ProviderQuotaAdmissionError,
        _reservation_plan_for_live_probe,
    )

    try:
        # This planner is pure: it validates a reviewed reservation shape but
        # neither reserves quota nor touches the provider/network.
        _reservation_plan_for_live_probe(provider_name, operation, None, datetime.now(UTC))
    except ProviderQuotaAdmissionError as exc:
        pytest.skip(
            f"no provider request made: {provider_name}/{operation} lacks "
            f"reviewed live quota admission: {exc}"
        )


def _observed_read(
    call,
    provider_name: str,
    operation: str,
    *,
    usage_identity: str | None = None,
    operation_cost_override: int | None = None,
    dimension_cost_overrides: dict[str, int] | None = None,
    expected_http_statuses: set[int] | None = None,
):
    """Durably reserve provider quota before every direct adapter operation."""

    from app.services.provider_quota_coordinator import (
        ProviderQuotaAdmissionError,
        reserve_live_provider_operation,
        settle_live_provider_operation,
    )

    reservation = reserve_live_provider_operation(
        provider_name,
        operation,
        usage_identity=usage_identity,
        operation_cost_override=operation_cost_override,
        dimension_cost_overrides=dimension_cost_overrides,
        require_persistent_coordinator=True,
    )
    if reservation is None:
        raise ProviderQuotaAdmissionError(
            f"provider quota exhausted before live operation {provider_name}/{operation}"
        )

    measurement, token = activate_provider_telemetry()
    admission_token = activate_request_admission()
    try:
        result = call()
    except BaseException as exc:
        response_status_code = getattr(exc, "status_code", None)
        expected_entitlement_denial = response_status_code in (expected_http_statuses or set())
        try:
            settle_live_provider_operation(
                reservation,
                http_requests=measurement.http_requests,
                response_bytes=measurement.response_bytes,
            )
        finally:
            record_observation(
                provider_name,
                operation=operation,
                http_requests=measurement.http_requests,
                response_bytes=measurement.response_bytes,
                response_headers=measurement.response_headers,
                success=expected_entitlement_denial,
                disposition=(
                    "expected_entitlement_denial"
                    if expected_entitlement_denial
                    else "provider_error"
                ),
                response_status_code=response_status_code,
                reservation_id=reservation.reservation_id,
            )
        assert measurement.http_requests > 0
        assert measurement.response_bytes > 0
        raise
    finally:
        deactivate_request_admission(admission_token)
        deactivate_provider_telemetry(token)
    try:
        settle_live_provider_operation(
            reservation,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
        )
    finally:
        record_observation(
            provider_name,
            operation=operation,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
            response_headers=measurement.response_headers,
            success=True,
            reservation_id=reservation.reservation_id,
        )
    assert measurement.http_requests > 0
    assert measurement.response_bytes > 0
    return result, measurement


def test_openfigi_keyless_mapping():
    rows, _ = _observed_read(
        lambda: OpenFigiProvider().fetch_stable_identifiers("SPY", exchange_code="US"),
        "openfigi",
        "fetch_stable_identifiers",
    )
    assert rows and any(row.identifier_type == "COMPOSITE_FIGI" for row in rows)


def test_openfigi_keyless_profile_resolution():
    """Exercise identifier-to-profile enrichment separately from ticker mapping."""

    profile, measurement = _observed_read(
        lambda: OpenFigiProvider().resolve_instrument_profile(isin="US0378331005"),
        "openfigi",
        "resolve_instrument_profile",
    )
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert any(
        identifier.identifier_type == "ISIN"
        and identifier.identifier_value == "US0378331005"
        for identifier in profile.identifiers
    )
    assert measurement.http_requests == 1


def test_sec_edgar_keyless_profile():
    _require("EDGAR_USER_AGENT")
    import app.providers.edgar as edgar_module

    edgar_module._ticker_map = {}
    edgar_module._ticker_map_ts = 0.0
    edgar_module._profile_cache = {}
    profile, measurement = _observed_read(
        lambda: EdgarProvider().get_instrument_profile("AAPL"),
        "edgar",
        "get_instrument_profile",
    )
    assert profile is not None and profile.name and profile.extra.get("cik")
    assert measurement.http_requests >= 2


def test_sec_edgar_keyless_search():
    """Exercise the cold SEC ticker-association search aid separately."""

    _require("EDGAR_USER_AGENT")
    import app.providers.edgar as edgar_module

    edgar_module._ticker_map = {}
    edgar_module._ticker_map_ts = 0.0
    rows, measurement = _observed_read(
        lambda: EdgarProvider().search_instruments("AAPL", limit=1),
        "edgar",
        "search_instruments",
    )
    assert rows
    assert rows[0].symbol == "AAPL"
    assert measurement.http_requests == 1


def test_sec_edgar_credentialed_filings_and_company_facts():
    """Exercise filing-derived earnings events and XBRL Company Facts."""

    _require("EDGAR_USER_AGENT")
    provider = EdgarProvider()
    events, _ = _observed_read(
        lambda: provider.fetch_instrument_events("AAPL"), "edgar", "fetch_instrument_events"
    )
    assert events
    assert all(event.event_type.value == "earnings" for event in events)
    assert all(event.event_time.tzinfo is not None for event in events)
    facts, _ = _observed_read(
        lambda: provider.fetch_fundamental_facts("320193"), "edgar", "fetch_fundamental_facts"
    )
    assert facts
    assert any(fact.namespace and fact.key and fact.unit for fact in facts)
    pipeline_events, _ = _observed_read(
        lambda: provider.fetch_ipo_pipeline_events(
            "320193",
            start=date.today() - timedelta(days=365 * 5),
            end=date.today(),
        ),
        "edgar",
        "fetch_ipo_pipeline_events",
    )
    assert all(event.event_type == "ipo_pipeline" for event in pipeline_events)


def test_sec_edgar_full_ticker_exchange_directory_pagination_is_complete(monkeypatch):
    """Fetch the official SEC directory once and prove local page completion."""

    _require("EDGAR_USER_AGENT")
    # This probe must establish a measured external read even when another
    # SEC test has already populated the independent exchange-directory cache.
    import app.providers.edgar as edgar_module

    monkeypatch.setattr(edgar_module, "_exchange_directory", [])
    monkeypatch.setattr(edgar_module, "_exchange_directory_ts", 0.0)
    provider = EdgarProvider()
    rows: list[dict] = []
    offset = 0
    declared_total: int | None = None
    declared_fingerprint: str | None = None
    first_page = True
    while True:
        if first_page:
            page, _ = _observed_read(
                lambda: provider.discover_universe_page("EQUITY", offset),
                "edgar",
                "discover_universe_page",
            )
            # The SEC ticker/exchange directory is one HTTP response; all
            # subsequent pagination is local projection of this snapshot.
            first_page = False
        else:
            # Subsequent pages are served from the provider's documented
            # in-process directory cache; validate pagination locally without
            # pretending that a second HTTP response occurred.
            page = provider.discover_universe_page("EQUITY", offset)
        page_rows = page["quotes"]
        assert page_rows
        if declared_total is None:
            declared_total = page["total"]
            declared_fingerprint = page["source_fingerprint"]
        assert page["total"] == declared_total
        assert page["source_fingerprint"] == declared_fingerprint
        rows.extend(page_rows)
        offset += len(page_rows)
        if offset >= declared_total:
            break
        assert len(page_rows) > 0

    assert declared_total == len(rows)
    assert len({(row["symbol"], row["exchange"], row.get("sec_cik")) for row in rows}) == len(rows)


def test_sec_edgar_complete_unique_issuer_cik_directory_pagination_is_complete(monkeypatch):
    """Traverse the current SEC ticker-association snapshot consistently."""

    _require("EDGAR_USER_AGENT")
    # Keep this case independently runnable.  Other SEC probes populate the
    # provider's documented in-process directory cache, while this assertion
    # intentionally requires one measured network response for the catalogue.
    import app.providers.edgar as edgar_module

    monkeypatch.setattr(edgar_module, "_ticker_map", {})
    monkeypatch.setattr(edgar_module, "_ticker_map_ts", 0.0)
    provider = EdgarProvider()
    rows: list[dict] = []
    offset = 0
    declared_total: int | None = None
    first_page = True
    while True:
        if first_page:
            page, _ = _observed_read(
                lambda: provider.discover_issuer_ciks_page(offset, limit=250),
                "edgar",
                "discover_issuer_ciks_page",
            )
            first_page = False
        else:
            page = provider.discover_issuer_ciks_page(offset, limit=250)
        page_rows = page["issuers"]
        if declared_total is None:
            declared_total = page["total"]
        assert page["total"] == declared_total
        assert page["offset"] == offset
        rows.extend(page_rows)
        offset += len(page_rows)
        if offset >= declared_total:
            break
        assert page_rows

    assert declared_total == len(rows)
    assert len({row["cik"] for row in rows}) == len(rows)
    assert all(len(row["cik"]) == 10 and row["cik"].isdigit() for row in rows)


def test_nasdaq_trader_keyless_directory(monkeypatch):
    _skip_unadmitted_live_operation("nasdaq", "discover_universe_page")
    import app.providers.nasdaq as nasdaq_module

    # The source is two directory files. Clear both cache layers so the
    # observed cold read cannot silently become an unmeasured cache hit.
    monkeypatch.setattr(nasdaq_module, "_cache", None)
    monkeypatch.setattr(nasdaq_module, "_file_cache", {})
    provider = NasdaqProvider()
    equities, measurement = _observed_read(
        lambda: provider.discover_universe_page("EQUITY", 0),
        "nasdaq",
        "discover_universe_page",
    )
    assert measurement.http_requests == 2
    # The first EQUITY read above populates the shared directory cache. The
    # ETF read is therefore a local projection of that same observed source.
    etfs = provider.discover_universe_page("ETF", 0)
    assert equities["quotes"] and etfs["quotes"]
    assert equities["source_files"] == ["nasdaqlisted", "otherlisted"]
    assert all(row["status"] == "active" for row in equities["quotes"][:10])
    assert all(not row["symbol"].startswith("FILE CREATION") for row in equities["quotes"])
    if equities["total"] > 1000:
        next_page = provider.discover_universe_page("EQUITY", 1000)
        assert (
            next_page["quotes"]
            and next_page["quotes"][0]["symbol"] != equities["quotes"][0]["symbol"]
        )


def test_nasdaq_trader_full_directory_pagination_is_complete(monkeypatch):
    """Fetch both official directory files once and prove page completion locally."""

    _skip_unadmitted_live_operation("nasdaq", "discover_universe_page")
    import app.providers.nasdaq as nasdaq_module

    monkeypatch.setattr(nasdaq_module, "_cache", None)
    monkeypatch.setattr(nasdaq_module, "_file_cache", {})
    provider = NasdaqProvider()
    first_page = True
    for quote_type in ("EQUITY", "ETF"):
        rows: list[dict] = []
        offset = 0
        declared_total: int | None = None
        while True:
            if first_page:
                page, measurement = _observed_read(
                    lambda: provider.discover_universe_page(quote_type, offset),
                    "nasdaq",
                    "discover_universe_page",
                )
                assert measurement.http_requests == 2
                first_page = False
            else:
                # All later pages and the ETF projection are served from the
                # same observed local directory snapshot.
                page = provider.discover_universe_page(quote_type, offset)
            assert page["source_files"] == ["nasdaqlisted", "otherlisted"]
            if declared_total is None:
                declared_total = page["total"]
            assert page["total"] == declared_total
            page_rows = page["quotes"]
            assert page_rows
            rows.extend(page_rows)
            next_offset = page.get("next_offset")
            if next_offset is None:
                break
            assert next_offset > offset
            assert len(rows) <= declared_total
            offset = next_offset

        assert declared_total == len(rows)
        assert len({(row["symbol"], row["exchange_mic"], row["quoteType"]) for row in rows}) == len(
            rows
        )


def test_binance_keyless_crypto_history():
    rows, _ = _observed_read(
        lambda: BinanceProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1, adjusted=False),
        "binance",
        "fetch_latest_ohlcv",
        operation_cost_override=estimate_latest_ohlcv_request_weight(Timeframe.D1, 1),
    )
    assert rows and rows[-1].close > 0
    price, _ = _observed_read(
        lambda: BinanceProvider().get_current_price("BTC-USD"),
        "binance",
        "get_current_price",
    )
    assert price is not None and price > 0
    universe, _ = _observed_read(
        lambda: BinanceProvider().discover_universe_page("CRYPTOCURRENCY", 0),
        "binance",
        "discover_universe_page",
        operation_cost_override=20,
    )
    assert universe["quotes"] and universe["total"] >= len(universe["quotes"])


def test_binance_keyless_bounded_daily_history():
    """Exercise the direct range path separately from latest-window history."""

    end = datetime.now(UTC)
    start = end - timedelta(days=30)
    rows, measurement = _observed_read(
        lambda: BinanceProvider().fetch_ohlcv(
            "BTC-USD", Timeframe.D1, start, end, adjusted=False
        ),
        "binance",
        "fetch_ohlcv",
        operation_cost_override=2,
    )
    # The provider may split the exact 30-day interval at its exchange
    # boundary; the reviewed safety ceiling for this case is two pages.
    assert 1 <= measurement.http_requests <= 2
    assert rows and rows[-1].close > 0
    assert all(row.ts.tzinfo is not None for row in rows)


def test_binance_keyless_account_usage_snapshot():
    """Exercise Binance's native fixed-minute request-weight counter."""

    usage, measurement = _observed_read(
        lambda: BinanceProvider().fetch_account_usage(),
        "binance",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "binance"
    assert usage.unit == "weight"
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    assert set(dimensions) == {"request_weight_per_minute"}
    weight = dimensions["request_weight_per_minute"]
    assert weight.limit == 6000
    assert weight.remaining is not None and weight.remaining >= 0
    assert weight.consumed is not None and weight.consumed >= 0
    assert weight.reset_at is not None and weight.reset_at.tzinfo is not None
    reconciliation = reconcile_native_account_usage("binance", usage)
    assert [item["status"] for item in reconciliation] == ["reconciled"]


def test_coinbase_keyless_crypto_history():
    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("coinbase", "fetch_latest_ohlcv")
    if missing:
        assert {
            "COINBASE_MARKET_DATA_USE_AUTHORIZED",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        } >= set(missing)
        return
    rows, _ = _observed_read(
        lambda: CoinbaseProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1, adjusted=False),
        "coinbase",
        "fetch_latest_ohlcv",
        operation_cost_override=estimate_coinbase_latest_ohlcv_request_count(Timeframe.D1, 1),
    )
    assert rows and rows[-1].close > 0


def test_kraken_keyless_crypto_history():
    rows, _ = _observed_read(
        lambda: KrakenProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1, adjusted=False),
        "kraken",
        "fetch_latest_ohlcv",
        operation_cost_override=estimate_kraken_latest_ohlcv_request_count(Timeframe.D1, 1),
    )
    assert rows and rows[-1].close > 0
    time.sleep(1.2)
    price, _ = _observed_read(
        lambda: KrakenProvider().get_current_price("BTC-USD"),
        "kraken",
        "get_current_price",
    )
    assert price is not None and price > 0
    time.sleep(1.2)
    universe, _ = _observed_read(
        lambda: KrakenProvider().discover_universe_page("CRYPTOCURRENCY", 0),
        "kraken",
        "discover_universe_page",
    )
    assert universe["quotes"] and universe["total"] >= len(universe["quotes"])


def test_alpaca_credentialed_history():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: AlpacaProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end),
        "alpaca",
        "fetch_ohlcv",
        operation_cost_override=estimate_alpaca_ohlcv_request_count(Timeframe.D1, start, end),
    )
    assert rows and rows[-1].close > 0


def test_alpaca_credentialed_intraday_history():
    """Exercise the free IEX feed's bounded five-minute candle path."""

    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    end = datetime.now(UTC)
    start = end - timedelta(days=5)
    rows, measurement = _observed_read(
        lambda: AlpacaProvider().fetch_ohlcv("AAPL", Timeframe.M5, start, end, adjusted=False),
        "alpaca",
        "fetch_ohlcv",
        operation_cost_override=estimate_alpaca_ohlcv_request_count(Timeframe.M5, start, end),
    )
    assert measurement.http_requests > 0
    assert rows and rows[-1].close > 0
    assert all(row.ts.tzinfo is not None for row in rows)


def test_alpaca_credentialed_latest_price():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    price, _ = _observed_read(
        lambda: AlpacaProvider().get_current_price("AAPL"), "alpaca", "get_current_price"
    )
    assert price is not None and price > 0


def test_alpaca_credentialed_profile():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    profile, _ = _observed_read(
        lambda: AlpacaProvider().get_instrument_profile("AAPL"),
        "alpaca",
        "get_instrument_profile",
    )
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.name
    assert profile.listings and profile.listings[0].provider_symbol == "AAPL"


def test_alpaca_credentialed_crypto_profile():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    profile, _ = _observed_read(
        lambda: AlpacaProvider().get_instrument_profile("BTC-USD"),
        "alpaca",
        "get_instrument_profile",
    )
    assert profile is not None
    assert profile.symbol == "BTC-USD"
    assert profile.quote_type == "CRYPTOCURRENCY"
    assert profile.listings and profile.listings[0].provider_symbol == "BTC/USD"


def test_alpaca_credentialed_assets_and_corporate_actions(monkeypatch):
    """Exercise the non-price Alpaca surfaces used by universe/event refreshes."""

    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    # Keep the direct live probe bounded even when the provider returns a
    # cursor. This is test-safety only; deployment routing still requires its
    # own operator-reviewed positive bound and remains fail-closed by default.
    monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 2)
    provider = AlpacaProvider()
    page, _ = _observed_read(
        lambda: provider.discover_universe_page("EQUITY", 0),
        "alpaca",
        "discover_universe_page",
    )
    assert page["quotes"]
    assert page["total"] >= len(page["quotes"])
    assert all(row["quoteType"] == "EQUITY" for row in page["quotes"])
    events, _ = _observed_read(
        lambda: provider.fetch_instrument_events("AAPL"),
        "alpaca",
        "fetch_instrument_events",
        operation_cost_override=settings.ALPACA_CORPORATE_ACTIONS_MAX_PAGES,
    )
    # A symbol can legitimately have no actions in the bounded lookback. The
    # transport and normalized event container must still be valid.
    assert isinstance(events, list)
    assert all(event.event_type.value in {"split", "dividend", "ex_dividend"} for event in events)


def test_massive_credentialed_reference():
    _require("MASSIVE_API_KEY")
    # Keep this case within the documented five-call/minute Stocks Basic
    # allowance: profile (1), IPO calendar (1), search (1), holidays (1), and
    # one adjusted daily history read (1). Corporate actions deliberately
    # remain a separately scheduled two-request live case because Massive
    # exposes splits and dividends as independent paginated endpoints; doing
    # both here would overrun the key's five-call window.
    provider = MassiveProvider()
    profile, _ = _observed_read(
        lambda: provider.get_instrument_profile("AAPL"), "massive", "get_instrument_profile"
    )
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.name
    assert profile.exchange
    assert any(
        identifier.identifier_type in {"CIK", "COMPOSITE_FIGI", "SHARE_CLASS_FIGI"}
        for identifier in profile.identifiers
    )
    events, _ = _observed_read(
        lambda: provider.fetch_market_events(
            start=date.today() - timedelta(days=7), end=date.today() + timedelta(days=90)
        ),
        "massive",
        "fetch_market_events",
    )
    assert isinstance(events, list)
    assert all(event.event_type == "ipo" for event in events)
    assert all(event.effective_date is not None for event in events)
    search_rows, _ = _observed_read(
        lambda: provider.search_instruments("AAPL", limit=1),
        "massive",
        "search_instruments",
    )
    assert search_rows and search_rows[0].symbol == "AAPL"
    holidays, _ = _observed_read(
        lambda: provider.fetch_market_holidays(
            start=date.today(), end=date.today() + timedelta(days=90)
        ),
        "massive",
        "fetch_market_holidays",
    )
    assert isinstance(holidays, list)
    start = datetime.now(UTC) - timedelta(days=30)
    end = datetime.now(UTC)
    bars, _ = _observed_read(
        lambda: provider.fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            start,
            end,
            adjusted=True,
        ),
        "massive",
        "fetch_ohlcv",
        operation_cost_override=estimate_massive_ohlcv_request_count(Timeframe.D1, start, end),
    )
    assert bars
    assert all(bar.is_adjusted for bar in bars)
    assert all(bar.high >= max(bar.open, bar.close) for bar in bars)
    assert all(bar.low <= min(bar.open, bar.close) for bar in bars)


def test_alpha_vantage_credentialed_daily():
    _require("ALPHA_VANTAGE_API_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_ohlcv(
            "AAPL", Timeframe.D1, start, end, adjusted=False
        ),
        "alpha_vantage",
        "fetch_ohlcv",
    )
    assert rows and rows[-1].close > 0


def test_alpha_vantage_credentialed_ipo_calendar():
    """Exercise the separate IPO-calendar operation in a fresh live window."""

    _require("ALPHA_VANTAGE_API_KEY")
    events, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_market_events(),
        "alpha_vantage",
        "fetch_market_events",
    )
    # Alpha Vantage may legitimately return only the CSV header when no IPO
    # rows are currently published. Transport and schema evidence still matter;
    # do not synthesize an event merely to make the live probe non-empty.
    assert isinstance(events, list)
    assert all(event.event_type == "ipo" for event in events)
    assert all(event.effective_date is not None for event in events)


def test_alpha_vantage_credentialed_earnings_calendar():
    """Exercise the documented bounded forward earnings-calendar CSV."""

    _require("ALPHA_VANTAGE_API_KEY")
    events, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_earnings_calendar(
            horizon="3month",
            start=date.today(),
            end=date.today() + timedelta(days=90),
        ),
        "alpha_vantage",
        "fetch_earnings_calendar",
    )
    # The provider may publish no rows in a particular window; transport and
    # schema evidence still matter, but no synthetic event is accepted.
    assert isinstance(events, list)
    assert all(event.event_type == "earnings" for event in events)
    assert all(event.effective_date is not None for event in events)


def test_alpha_vantage_credentialed_earnings_history():
    """Exercise annual/quarterly EPS normalization when the daily quota permits it."""

    _require("ALPHA_VANTAGE_API_KEY")
    events, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_instrument_events("AAPL"),
        "alpha_vantage",
        "fetch_instrument_events",
    )
    assert events
    assert all(event.event_type.value in {"earnings", "earnings_estimate"} for event in events)
    assert all(event.event_time.tzinfo is not None for event in events)
    assert all(event.source_event_key.startswith("alpha_vantage:earnings:") for event in events)


def test_coingecko_credentialed_search():
    _require("COINGECKO_API_KEY")
    rows, _ = _observed_read(
        lambda: CoinGeckoProvider().search_instruments("bitcoin", limit=1),
        "coingecko",
        "search_instruments",
    )
    assert rows and rows[0].symbol == "BTC-USD"


def test_coingecko_credentialed_profile_observes_id_resolution_request():
    _require("COINGECKO_API_KEY")
    profile, measurement = _observed_read(
        lambda: CoinGeckoProvider().get_instrument_profile("BTC-USD"),
        "coingecko",
        "get_instrument_profile",
    )
    assert profile is not None
    assert profile.extra["coingecko_id"] == "bitcoin"
    assert measurement.http_requests >= 2


def test_fred_series_requires_persisted_data_rights_before_network_access():
    """Avoid network access while FRED storage rights and quota scope are unresolved."""

    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("fred", "fetch_ohlcv")
    if missing:
        assert {
            "FRED_REVIEWED_LIMIT_SCOPE",
            "FRED_REVIEWED_REQUESTS_PER_MINUTE",
            "FRED_REVIEWED_QUOTA_EVIDENCE",
            "FRED_PERSISTED_STORAGE_AUTHORIZED",
            "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE",
            "FRED_AUTOMATED_USE_AUTHORIZED",
            "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
            "FRED_SERIES_RIGHTS_EVIDENCE",
        } >= set(missing)
        return
    _require("FRED_API_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: FREDProvider().fetch_ohlcv("^IRX", Timeframe.D1, start, end),
        "fred",
        "fetch_ohlcv",
    )
    assert rows and all(row.close > 0 for row in rows)


def test_finra_credentialed_short_interest():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    rows, _ = _observed_read(
        lambda: FINRAProvider().fetch_short_interest("AAPL"),
        "finra",
        "fetch_short_interest",
        # FINRA's per-dataset async limiter does not apply to these direct
        # synchronous endpoints. Keep sync requests and the 3 MiB response
        # reservation in place; explicitly declare no async-dimension use.
        dimension_cost_overrides={"asynchronous_requests_per_minute_dataset": 0},
    )
    assert rows
    assert all(row.settlement_date and row.short_position is not None for row in rows)
    assert any((row.source_identifier or "").upper() == "AAPL" for row in rows)


def test_finra_credentialed_otc_daily_list():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    end = date.today()
    rows, _ = _observed_read(
        lambda: FINRAProvider().fetch_market_events(start=end - timedelta(days=45), end=end),
        "finra",
        "fetch_market_events",
        dimension_cost_overrides={"asynchronous_requests_per_minute_dataset": 0},
    )
    assert rows
    for row in rows:
        assert row.event_key.startswith("finra:otc_daily_list:")


def test_finra_otc_directory_credentialed_source():
    """Probe OTC source only after its current availability is evidenced."""

    configured_source = settings.FINRA_OTC_SYMBOL_DIRECTORY_URL.strip()
    reviewed_source = settings.FINRA_OTC_REVIEWED_SOURCE_URL.strip()
    if (
        not settings.FINRA_OTC_SOURCE_REVIEWED
        or not settings.FINRA_OTC_SOURCE_EVIDENCE.strip()
        or not configured_source
        or reviewed_source != configured_source
    ):
        pytest.skip(
            "FINRA's current public dataset catalog does not list otcSecurityMaster; "
            "no live request is permitted until current documentation or written "
            "provider confirmation is recorded and the reviewed URL exactly matches "
            "FINRA_OTC_SYMBOL_DIRECTORY_URL."
        )

    _require("FINRA_OTC_SYMBOL_DIRECTORY_URL")
    page, _ = _observed_read(
        lambda: FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0),
        "finra_otc_directory",
        "discover_universe_page",
    )
    assert page["quotes"]
    assert page["total"] >= len(page["quotes"])
    assert page["source_files"] == [os.environ["FINRA_OTC_SYMBOL_DIRECTORY_URL"].strip()]
    assert all(row["exchange"] == "OTC" for row in page["quotes"])


@pytest.mark.parametrize(
    ("provider", "credentials", "symbol"),
    [
        (TiingoProvider(), ("TIINGO_API_KEY",), "AAPL"),
        (TwelveDataProvider(), ("TWELVE_DATA_API_KEY",), "AAPL"),
        (MarketstackProvider(), ("MARKETSTACK_API_KEY",), "AAPL"),
        (EODHDProvider(), ("EODHD_API_KEY",), "AAPL"),
        (FMPProvider(), ("FMP_API_KEY",), "AAPL"),
        (TradierProvider(), ("TRADIER_API_KEY",), "AAPL"),
        (MarketDataAppProvider(), ("MARKETDATA_APP_API_KEY",), "AAPL"),
    ],
    ids=lambda item: getattr(item, "name", str(item)),
)
def test_optional_credentialed_provider_small_read(provider, credentials, symbol):
    _require(*credentials)
    start, end = _bounds()
    operation_cost = None
    if provider.name == "marketstack":
        operation_cost = estimate_marketstack_ohlcv_request_count(Timeframe.D1, start, end)
    elif provider.name == "marketdata_app":
        operation_cost = estimate_marketdata_app_ohlcv_credit_count(Timeframe.D1, start, end)
    rows, _ = _observed_read(
        lambda: provider.fetch_ohlcv(symbol, Timeframe.D1, start, end, adjusted=False),
        provider.name,
        "fetch_ohlcv",
        usage_identity=symbol,
        operation_cost_override=operation_cost,
    )
    assert rows
    assert all(row.ts.tzinfo is not None for row in rows)
    assert all(row.close > 0 for row in rows)
    if provider.name == "tiingo":
        profile, _ = _observed_read(
            lambda: provider.get_instrument_profile(symbol),
            provider.name,
            "get_instrument_profile",
            usage_identity=symbol,
        )
        assert profile is not None
        assert profile.symbol == symbol
        assert profile.name and profile.exchange
    if provider.name == "twelve_data":
        intraday_start = datetime.now(UTC) - timedelta(days=5)
        intraday_rows, _ = _observed_read(
            lambda: provider.fetch_ohlcv(
                symbol, Timeframe.M5, intraday_start, datetime.now(UTC), adjusted=False
            ),
            provider.name,
            "fetch_ohlcv",
        )
        assert intraday_rows
        assert all(row.ts.tzinfo is not None and row.close > 0 for row in intraday_rows)
        search_rows, _ = _observed_read(
            lambda: provider.search_instruments("AAPL", limit=1),
            provider.name,
            "search_instruments",
        )
        assert search_rows and search_rows[0].symbol == "AAPL"
        current, _ = _observed_read(
            lambda: provider.get_current_price(symbol), provider.name, "get_current_price"
        )
        assert current is not None and current > 0
        universe, _ = _observed_read(
            lambda: provider.discover_universe_page("EQUITY", 0),
            provider.name,
            "discover_universe_page",
        )
        assert universe["quotes"] and universe["total"] >= len(universe["quotes"])
    if provider.name == "eodhd":
        # EODHD documents the same EOD endpoint with d/w/m period selectors;
        # exercise the two non-daily adapter paths in the bounded live case.
        period_start = datetime.now(UTC) - timedelta(days=90)
        for timeframe in (Timeframe.W1, Timeframe.MN):
            period_rows, _ = _observed_read(
                lambda timeframe=timeframe: provider.fetch_ohlcv(
                    symbol, timeframe, period_start, end, adjusted=False
                ),
                provider.name,
                "fetch_ohlcv",
            )
            assert period_rows
            assert all(row.ts.tzinfo is not None and row.close > 0 for row in period_rows)
        current, _ = _observed_read(
            lambda: provider.get_current_price(symbol), provider.name, "get_current_price"
        )
        assert current is not None and current > 0
        universe, _ = _observed_read(
            lambda: provider.discover_universe_page("EQUITY", 0),
            provider.name,
            "discover_universe_page",
        )
        assert universe["quotes"] and universe["total"] >= len(universe["quotes"])
    if provider.name == "marketstack":
        current, _ = _observed_read(
            lambda: provider.get_current_price(symbol), provider.name, "get_current_price"
        )
        assert current is not None and current > 0
    if provider.name == "fmp":
        profile, _ = _observed_read(
            lambda: provider.get_instrument_profile(symbol), provider.name, "get_instrument_profile"
        )
        assert profile is not None
        assert profile.symbol == symbol
        assert profile.name and profile.exchange
        calendar_events, _ = _observed_read(
            lambda: provider.fetch_market_events(
                start=date.today() - timedelta(days=7),
                end=date.today() + timedelta(days=45),
            ),
            provider.name,
            "fetch_market_events",
        )
        assert calendar_events
        assert all(event.event_type == "earnings" for event in calendar_events)
        assert all(event.effective_date is not None for event in calendar_events)
    if provider.name == "tradier":
        expirations, _ = _observed_read(
            lambda: provider.list_option_expirations(symbol),
            provider.name,
            "list_option_expirations",
        )
        assert expirations
        contracts, _ = _observed_read(
            lambda: provider.fetch_option_chain(symbol, expiration=expirations[0]),
            provider.name,
            "fetch_option_chain",
        )
        assert contracts
        assert all(contract.underlying_symbol == symbol for contract in contracts)
        assert all(contract.right in {"call", "put"} for contract in contracts)


def test_twelve_data_credentialed_account_usage_snapshot():
    """Exercise Twelve Data's native minute-credit usage endpoint."""

    _require("TWELVE_DATA_API_KEY")
    usage, measurement = _observed_read(
        lambda: TwelveDataProvider().fetch_account_usage(),
        "twelve_data",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "twelve_data"
    # The live /api_usage response may omit the optional plan body field;
    # absence is preserved as ``None`` rather than inferred from the key.
    assert usage.account_plan is None or usage.account_plan.strip()
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    assert set(dimensions) == {"credits_per_minute"}
    minute = dimensions["credits_per_minute"]
    assert minute.limit is not None and minute.limit > 0
    assert minute.remaining is not None and minute.remaining >= 0
    assert minute.consumed is not None and minute.consumed >= 0
    assert minute.reset_at is not None and minute.reset_at.tzinfo is not None
    reconciliation = reconcile_native_account_usage("twelve_data", usage)
    assert [item["status"] for item in reconciliation] == ["reconciled"]


def test_eodhd_credentialed_account_usage_snapshot():
    """Exercise EODHD's documented daily-call usage endpoint."""

    _require("EODHD_API_KEY")
    usage, measurement = _observed_read(
        lambda: EODHDProvider().fetch_account_usage(),
        "eodhd",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "eodhd"
    assert usage.account_plan
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    assert "calls_per_day" in dimensions
    daily = dimensions["calls_per_day"]
    assert daily.limit is not None and daily.limit > 0
    assert daily.remaining is not None and daily.remaining >= 0
    assert daily.consumed is not None and daily.consumed >= 0
    if daily.reset_at is not None:
        assert daily.reset_at.tzinfo is not None
    reconciliation = reconcile_native_account_usage("eodhd", usage)
    # The supplied account can report the previous usage date until the first
    # request after midnight GMT. Preserve that observation without fabricating
    # a current daily baseline when the reset boundary is absent.
    assert all(item["status"] == "not_reconciled" for item in reconciliation)


def test_eodhd_free_plan_profile_entitlement_is_explicit():
    """The configured free EODHD key is EOD-only; do not treat 403 as no data."""

    _require("EODHD_API_KEY")
    with pytest.raises(ProviderResponseError) as exc_info:
        _observed_read(
            lambda: EODHDProvider().get_instrument_profile("AAPL"),
            "eodhd",
            "get_instrument_profile",
            expected_http_statuses={403},
        )
    assert exc_info.value.status_code == 403


def test_marketdata_app_credentialed_option_surface():
    """Exercise the documented free/trial option expiration and chain paths."""

    _require("MARKETDATA_APP_API_KEY")
    provider = MarketDataAppProvider()
    expirations, _ = _observed_read(
        lambda: provider.list_option_expirations("AAPL"),
        provider.name,
        "list_option_expirations",
    )
    assert expirations
    expiration = next((value for value in expirations if value >= date.today()), expirations[-1])
    contracts, _ = _observed_read(
        lambda: provider.fetch_option_chain("AAPL", expiration=expiration, max_symbols=20),
        provider.name,
        "fetch_option_chain",
        operation_cost_override=20,
    )
    assert contracts
    assert len(contracts) <= 20
    assert all(contract.underlying_symbol == "AAPL" for contract in contracts)
    assert all(contract.expiry_date == expiration for contract in contracts)
    assert all(contract.right in {"call", "put"} for contract in contracts)
    assert all(contract.strike > 0 for contract in contracts)


def test_marketdata_app_credentialed_option_quote_history():
    """Exercise the response-priced history path with its exact date bound."""

    _require("MARKETDATA_APP_API_KEY")
    provider = MarketDataAppProvider()
    expirations, _ = _observed_read(
        lambda: provider.list_option_expirations("AAPL"),
        provider.name,
        "list_option_expirations",
    )
    assert expirations
    expiration = next((value for value in expirations if value >= date.today()), expirations[-1])
    contracts, _ = _observed_read(
        lambda: provider.fetch_option_chain("AAPL", expiration=expiration, max_symbols=2),
        provider.name,
        "fetch_option_chain",
        operation_cost_override=2,
    )
    assert contracts
    contract = contracts[0]
    end = datetime.now(UTC) - timedelta(days=1)
    start = end - timedelta(days=2)
    points, measurement = _observed_read(
        lambda: provider.fetch_option_quote_history(
            contract.provider_symbol,
            start=start,
            end=end,
        ),
        provider.name,
        "fetch_option_quote_history",
        usage_identity=contract.provider_symbol,
        operation_cost_override=estimate_marketdata_app_option_quote_history_credit_count(
            start, end
        ),
    )
    assert measurement.http_requests == 1
    assert isinstance(points, list)
    assert all(point.provider_symbol == contract.provider_symbol for point in points)


def test_marketdata_app_response_priced_option_history_is_blocked_without_bound():
    """Verify unbounded response-priced options history never reaches transport."""

    from app.services.provider_quota_coordinator import (
        ProviderQuotaAdmissionError,
        reserve_live_provider_operation,
    )

    with pytest.raises(ProviderQuotaAdmissionError, match="operation cost is unreviewed"):
        reserve_live_provider_operation("marketdata_app", "fetch_option_quote_history")


def test_marketdata_app_credentialed_account_usage_snapshot():
    """Exercise the documented account quota and options-entitlement endpoint."""

    _require("MARKETDATA_APP_API_KEY")
    usage, measurement = _observed_read(
        lambda: MarketDataAppProvider().fetch_account_usage(),
        "marketdata_app",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "marketdata_app"
    assert usage.unit == "credits"
    assert usage.limit is not None and usage.limit > 0
    assert usage.remaining is not None
    assert usage.consumed is not None and usage.consumed >= 0
    assert usage.reset_at is not None and usage.reset_at.tzinfo is not None
    assert isinstance(usage.options_data_permissions, str)
    assert measurement.http_requests == 1
    reconciliation = reconcile_native_account_usage("marketdata_app", usage)
    assert [item["status"] for item in reconciliation] == ["reconciled"]


def test_marketdata_app_credentialed_latest_price():
    """Exercise the provider's fixed one-credit latest-price contract."""

    _require("MARKETDATA_APP_API_KEY")
    price, measurement = _observed_read(
        lambda: MarketDataAppProvider().get_current_price("AAPL"),
        "marketdata_app",
        "get_current_price",
        usage_identity="AAPL",
    )
    assert measurement.http_requests > 0
    assert price is not None and price > 0


def test_marketdata_app_credentialed_intraday_history():
    """Exercise the documented five-minute delayed stock-candle surface."""

    _require("MARKETDATA_APP_API_KEY")
    end = datetime.now(UTC)
    start = end - timedelta(days=5)
    rows, measurement = _observed_read(
        lambda: MarketDataAppProvider().fetch_ohlcv(
            "AAPL", Timeframe.M5, start, end, adjusted=False
        ),
        "marketdata_app",
        "fetch_ohlcv",
        usage_identity="AAPL",
        operation_cost_override=estimate_marketdata_app_ohlcv_credit_count(
            Timeframe.M5, start, end
        ),
    )
    assert measurement.http_requests > 0
    assert rows and rows[-1].close > 0
    assert all(row.ts.tzinfo is not None for row in rows)


def test_finnhub_credentialed_company_profile():
    """The observed free key does not entitle the stock-candle endpoint."""

    _require("FINNHUB_API_KEY")
    profile, _ = _observed_read(
        lambda: FinnhubProvider().get_instrument_profile("AAPL"),
        "finnhub",
        "get_instrument_profile",
    )
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.name and profile.exchange
    events, _ = _observed_read(
        lambda: FinnhubProvider().fetch_instrument_events("AAPL"),
        "finnhub",
        "fetch_instrument_events",
    )
    assert events
    assert all(event.event_time.tzinfo is not None for event in events)
    assert any(event.eps_actual is not None or event.eps_estimate is not None for event in events)
    search_rows, _ = _observed_read(
        lambda: FinnhubProvider().search_instruments("AAPL", limit=1),
        "finnhub",
        "search_instruments",
    )
    assert search_rows and search_rows[0].symbol == "AAPL"
    universe, _ = _observed_read(
        lambda: FinnhubProvider().discover_universe_page("EQUITY", 0),
        "finnhub",
        "discover_universe_page",
    )
    assert universe["quotes"] and universe["total"] >= len(universe["quotes"])
    start, end = _bounds()
    with pytest.raises(ProviderResponseError) as candle_error:
        _observed_read(
            lambda: FinnhubProvider().fetch_ohlcv(
                "AAPL", Timeframe.D1, start, end, adjusted=False
            ),
            "finnhub",
            "fetch_ohlcv",
            expected_http_statuses={403},
        )
    assert candle_error.value.status_code == 403
    calendar_events, _ = _observed_read(
        lambda: FinnhubProvider().fetch_market_events(
            start=date.today() - timedelta(days=7),
            end=date.today() + timedelta(days=45),
        ),
        "finnhub",
        "fetch_market_events",
    )
    assert all(event.effective_date is not None for event in calendar_events)


def test_ibkr_read_only_gateway_profile_history_and_snapshot():
    """Exercise the documented gateway session, history, and snapshot paths."""

    _require("IBKR_READ_ONLY_URL", "IBKR_READ_ONLY_SESSION_COOKIE")
    provider = IBKRProvider()
    profile, _ = _observed_read(
        lambda: provider.get_instrument_profile("AAPL"), "ibkr", "get_instrument_profile"
    )
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.listings and profile.listings[0].extra_data.get("conid")
    start = datetime.now(UTC) - timedelta(days=5)
    bars, _ = _observed_read(
        lambda: provider.fetch_ohlcv(
            "AAPL", Timeframe.D1, start, datetime.now(UTC), adjusted=False
        ),
        "ibkr",
        "fetch_ohlcv",
    )
    assert bars and bars[-1].close > 0
    price, measurement = _observed_read(
        lambda: provider.get_current_price("AAPL"), "ibkr", "get_current_price"
    )
    assert price is not None and price > 0
    assert measurement.http_requests >= 2
