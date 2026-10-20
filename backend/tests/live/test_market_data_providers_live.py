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
    estimate_coinbase_ohlcv_request_count,
    estimate_kraken_latest_ohlcv_request_count,
    estimate_kraken_ohlcv_request_count,
)
from app.providers.cta_plan import CTAPlanProvider
from app.providers.edgar import EdgarProvider
from app.providers.errors import ProviderNotConfiguredError, ProviderResponseError
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
    estimate_fmp_ohlcv_request_count,
    estimate_marketdata_app_ohlcv_credit_count,
    estimate_marketdata_app_option_quote_history_credit_count,
    estimate_marketstack_ohlcv_request_count,
)
from app.providers.registry import provider_rate_limit_seed
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from tests.live.live_usage import (
    activate_request_admission,
    archive_response_payloads,
    challenge_status_code,
    deactivate_request_admission,
    reconcile_native_account_usage,
    record_observation,
    wait_for_provider_start_window,
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

    wait_for_provider_start_window(provider_name)
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

    measurement, token = activate_provider_telemetry(capture_response_payloads=True)
    admission_token = activate_request_admission()
    try:
        result = call()
    except BaseException as exc:
        response_status_code = challenge_status_code(
            measurement.response_metadata, getattr(exc, "status_code", None)
        ) or getattr(exc, "status_code", None)
        expected_entitlement_denial = response_status_code in (expected_http_statuses or set())
        archive_error = None
        try:
            archive_response_payloads(
                provider_name,
                operation,
                measurement.response_payloads,
                response_bytes=measurement.response_bytes,
                response_metadata=measurement.response_metadata,
            )
            if measurement.http_requests != len(measurement.response_payloads):
                raise RuntimeError(
                    "live response body capture mismatch: "
                    f"{measurement.http_requests} responses, "
                    f"{len(measurement.response_payloads)} captured bodies"
                )
        except BaseException as archive_exc:
            archive_error = archive_exc
        try:
            settle_live_provider_operation(
                reservation,
                http_requests=measurement.http_requests,
                response_bytes=measurement.response_bytes,
                response_status_code=response_status_code,
            )
        finally:
            record_observation(
                provider_name,
                operation=operation,
                http_requests=measurement.http_requests,
                response_bytes=measurement.response_bytes,
                response_headers=measurement.response_headers,
                success=archive_error is None and expected_entitlement_denial,
                disposition=(
                    "archive_failure"
                    if archive_error is not None
                    else (
                        "expected_entitlement_denial"
                        if expected_entitlement_denial
                        else "provider_error"
                    )
                ),
                response_status_code=response_status_code,
                reservation_id=reservation.reservation_id,
            )
        assert measurement.http_requests > 0
        assert measurement.response_bytes > 0
        if archive_error is not None:
            raise archive_error from exc
        raise
    finally:
        deactivate_request_admission(admission_token)
        deactivate_provider_telemetry(token)
    archive_error = None
    try:
        archive_response_payloads(
            provider_name,
            operation,
            measurement.response_payloads,
            response_bytes=measurement.response_bytes,
            response_metadata=measurement.response_metadata,
        )
        if measurement.http_requests != len(measurement.response_payloads):
            raise RuntimeError(
                "live response body capture mismatch: "
                f"{measurement.http_requests} responses, "
                f"{len(measurement.response_payloads)} captured bodies"
            )
    except BaseException as archive_exc:
        archive_error = archive_exc
    try:
        response_status_code = challenge_status_code(measurement.response_metadata)
        settle_live_provider_operation(
            reservation,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
            **(
                {"response_status_code": response_status_code}
                if response_status_code is not None
                else {}
            ),
        )
    finally:
        record_observation(
            provider_name,
            operation=operation,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
            response_headers=measurement.response_headers,
            success=archive_error is None,
            disposition="observed" if archive_error is None else "archive_failure",
            response_status_code=response_status_code,
            reservation_id=reservation.reservation_id,
        )
    assert measurement.http_requests > 0
    assert measurement.response_bytes > 0
    if archive_error is not None:
        raise archive_error
    return result, measurement


def _observed_service_read(call, provider_name: str, operation: str, monkeypatch):
    """Record service-managed adapter measurements without a duplicate reservation.

    The service runtime itself reserves and settles every provider page. This
    wrapper collects those runtime measurements for the live acceptance ledger
    and raw-response archive; it deliberately does not reserve the same usage
    a second time as `_observed_read` does for direct adapter calls.
    """

    import app.services.provider_runtime as provider_runtime

    measurements = []
    activate = provider_runtime.activate_provider_telemetry

    def capture_measurement(*, capture_response_payloads=True):
        measurement, token = activate(capture_response_payloads=capture_response_payloads)
        measurements.append(measurement)
        return measurement, token

    monkeypatch.setattr(provider_runtime, "activate_provider_telemetry", capture_measurement)
    wait_for_provider_start_window(provider_name)
    succeeded = False
    try:
        result = call()
        succeeded = True
        return result
    finally:
        payloads = [payload for item in measurements for payload in item.response_payloads]
        response_metadata = [
            metadata for item in measurements for metadata in item.response_metadata
        ]
        response_bytes = sum(item.response_bytes for item in measurements)
        response_headers = {
            name: value for item in measurements for name, value in item.response_headers.items()
        }
        archive_error = None
        try:
            archive_response_payloads(
                provider_name,
                operation,
                payloads,
                response_bytes=response_bytes,
                response_metadata=response_metadata,
            )
            if sum(item.http_requests for item in measurements) != len(payloads):
                raise RuntimeError(
                    "live response body capture mismatch for service-managed provider call"
                )
        except BaseException as exc:
            archive_error = exc
        record_observation(
            provider_name,
            operation=operation,
            http_requests=sum(item.http_requests for item in measurements),
            response_bytes=response_bytes,
            response_headers=response_headers,
            success=succeeded and archive_error is None,
            disposition=(
                "archive_failure"
                if archive_error is not None
                else "observed"
                if succeeded
                else "provider_error"
            ),
        )
        if archive_error is not None:
            raise archive_error


_BINANCE_LIVE_USAGE_RESET_AT: datetime | None = None


def _ensure_binance_live_usage_baseline() -> None:
    """Refresh Binance's IP counter after its fixed-minute window rolls over.

    The live matrix runs many provider-native usage probes before data cases.
    A Binance snapshot can therefore be stale by the time its own history
    tests execute; additionally, a multi-page history request can cross a
    minute boundary. The shared coordinator correctly refuses requests in a
    new window until its native IP counter is observed, so refresh only when
    the latest observed reset boundary has elapsed.
    """

    global _BINANCE_LIVE_USAGE_RESET_AT
    now = datetime.now(UTC)
    if _BINANCE_LIVE_USAGE_RESET_AT is not None and now < _BINANCE_LIVE_USAGE_RESET_AT:
        return

    usage, _ = _observed_read(
        lambda: BinanceProvider().fetch_account_usage(),
        "binance",
        "fetch_account_usage",
    )
    assert usage is not None and usage.provider == "binance"
    assert usage.reset_at is not None and usage.reset_at.tzinfo is not None
    reconciliation = reconcile_native_account_usage("binance", usage)
    assert [item["status"] for item in reconciliation] == ["reconciled"]
    _BINANCE_LIVE_USAGE_RESET_AT = usage.reset_at


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
        identifier.identifier_type == "ISIN" and identifier.identifier_value == "US0378331005"
        for identifier in profile.identifiers
    )
    assert measurement.http_requests == 1


def test_openfigi_keyless_account_usage_snapshot():
    """Observe OpenFIGI's anonymous mapping-window headers exactly once."""

    usage, measurement = _observed_read(
        lambda: OpenFigiProvider().fetch_account_usage(),
        "openfigi",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "openfigi"
    assert usage.account_plan == "anonymous"
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    assert set(dimensions) == {"mapping_requests_per_minute"}
    window = dimensions["mapping_requests_per_minute"]
    assert window.limit == 25
    assert window.remaining is not None and 0 <= window.remaining <= window.limit
    assert window.consumed == window.limit - window.remaining
    assert window.reset_at is not None and window.reset_at > usage.observed_at
    reconciliation = reconcile_native_account_usage("openfigi", usage)
    assert [item["status"] for item in reconciliation] == ["reconciled"]


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


def test_nasdaq_trader_full_directory_pagination_is_complete(monkeypatch):
    """Fetch both official files once and prove the full directory locally.

    The two raw files consume the complete client-imposed daily request budget.
    Exercise cold-read, equity/ETF projection, and all local pages from that
    single measured fetch rather than repeating the same external requests in
    a second live test.
    """

    _skip_unadmitted_live_operation("nasdaq", "discover_universe_page")
    import app.providers.nasdaq as nasdaq_module

    monkeypatch.setattr(nasdaq_module, "_cache", None)
    monkeypatch.setattr(nasdaq_module, "_file_cache", {})
    provider = NasdaqProvider()
    equities, measurement = _observed_read(
        lambda: provider.discover_universe_page("EQUITY", 0),
        "nasdaq",
        "discover_universe_page",
    )
    assert measurement.http_requests == 2
    etfs = provider.discover_universe_page("ETF", 0)
    assert equities["quotes"] and etfs["quotes"]
    assert equities["source_files"] == ["nasdaqlisted", "otherlisted"]
    assert all(row["status"] == "active" for row in equities["quotes"][:10])
    assert all(not row["symbol"].startswith("FILE CREATION") for row in equities["quotes"])

    for quote_type, initial_page in (("EQUITY", equities), ("ETF", etfs)):
        rows: list[dict] = []
        offset = 0
        declared_total: int | None = initial_page["total"]
        page = initial_page
        while page:
            assert page["source_files"] == ["nasdaqlisted", "otherlisted"]
            assert set(page["source_file_creation_times"]) == {
                "nasdaqlisted",
                "otherlisted",
            }
            assert len({value[:10] for value in page["source_file_creation_times"].values()}) == 1
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
            # Subsequent pages are projections of the same observed snapshot.
            page = provider.discover_universe_page(quote_type, offset)

        assert declared_total == len(rows)
        assert len({(row["symbol"], row["exchange_mic"], row["quoteType"]) for row in rows}) == len(
            rows
        )


def test_cta_plan_latest_tape_ab_symbol_file_is_complete():
    """Read the current public Tape A/B file once and validate every source row."""

    _skip_unadmitted_live_operation("cta_plan", "discover_universe_page")
    page, measurement = _observed_read(
        lambda: CTAPlanProvider().discover_universe_page("EQUITY", 0),
        "cta_plan",
        "discover_universe_page",
    )

    assert measurement.http_requests == 2
    assert page["complete"] is True
    assert page["validation_errors"] == []
    assert page["source_snapshot_date"]
    assert len(page["source_files"]) == 2
    assert page["source_files"][0] == "cta_symbol_file_index"
    assert page["source_files"][1].endswith(".csv")
    assert page["source_row_count"] > 0
    assert page["total"] == len(page["quotes"]) > 0
    assert len({(row["symbol"], row["exchange_mic"]) for row in page["quotes"]}) == page["total"]
    assert all(row["exchange_mic"] and len(row["exchange_mic"]) == 4 for row in page["quotes"])
    assert page["raw_source_payload"]["index_html"]
    assert page["raw_source_payload"]["symbol_file_csv"]


def test_binance_keyless_crypto_history():
    _ensure_binance_live_usage_baseline()
    rows, measurement = _observed_read(
        lambda: BinanceProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1, adjusted=False),
        "binance",
        "fetch_latest_ohlcv",
        operation_cost_override=estimate_latest_ohlcv_request_weight(Timeframe.D1, 1),
    )
    assert rows and rows[-1].close > 0
    assert measurement.http_requests == 1
    _ensure_binance_live_usage_baseline()
    price, _ = _observed_read(
        lambda: BinanceProvider().get_current_price("BTC-USD"),
        "binance",
        "get_current_price",
    )
    assert price is not None and price > 0
    _ensure_binance_live_usage_baseline()
    universe, _ = _observed_read(
        lambda: BinanceProvider().discover_universe_page("CRYPTOCURRENCY", 0),
        "binance",
        "discover_universe_page",
        operation_cost_override=20,
    )
    assert universe["quotes"] and universe["total"] >= len(universe["quotes"])


def test_binance_keyless_bounded_daily_history():
    """Exercise the direct range path separately from latest-window history."""

    _ensure_binance_live_usage_baseline()
    end = datetime.now(UTC)
    start = end - timedelta(days=30)
    rows, measurement = _observed_read(
        lambda: BinanceProvider().fetch_ohlcv("BTC-USD", Timeframe.D1, start, end, adjusted=False),
        "binance",
        "fetch_ohlcv",
        operation_cost_override=2,
    )
    # This range fits in one Binance 1,000-candle page. The adapter must stop
    # after that short page rather than making an unbudgeted empty-page call.
    assert measurement.http_requests == 1
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
    global _BINANCE_LIVE_USAGE_RESET_AT
    _BINANCE_LIVE_USAGE_RESET_AT = usage.reset_at


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


def test_coinbase_keyless_history_quote_and_usd_products():
    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("coinbase", "fetch_ohlcv")
    if missing:
        assert {
            "COINBASE_MARKET_DATA_USE_AUTHORIZED",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        } >= set(missing)
        return

    end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    bars, history_measurement = _observed_read(
        lambda: CoinbaseProvider().fetch_ohlcv("BTC-USD", Timeframe.D1, start, end, adjusted=False),
        "coinbase",
        "fetch_ohlcv",
        operation_cost_override=estimate_coinbase_ohlcv_request_count(Timeframe.D1, start, end),
    )
    assert history_measurement.http_requests == 1
    assert bars and all(bar.close > 0 for bar in bars)

    price, price_measurement = _observed_read(
        lambda: CoinbaseProvider().get_current_price("BTC-USD"),
        "coinbase",
        "get_current_price",
    )
    assert price_measurement.http_requests == 1
    assert price is not None and price > 0

    catalogue, catalogue_measurement = _observed_read(
        lambda: CoinbaseProvider().discover_universe_page("CRYPTOCURRENCY", 0),
        "coinbase",
        "discover_universe_page",
    )
    assert catalogue_measurement.http_requests == 1
    assert catalogue["total"] >= len(catalogue["quotes"]) > 0
    assert all(quote["quoteType"] == "CRYPTOCURRENCY" for quote in catalogue["quotes"])


def test_kraken_keyless_crypto_history():
    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("kraken", "fetch_latest_ohlcv")
    if missing:
        assert {
            "KRAKEN_MARKET_DATA_USE_AUTHORIZED",
            "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "KRAKEN_MARKET_DATA_USE_REVIEWED_AT",
        } >= set(missing)
        return
    rows, _ = _observed_read(
        lambda: KrakenProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1, adjusted=False),
        "kraken",
        "fetch_latest_ohlcv",
        operation_cost_override=estimate_kraken_latest_ohlcv_request_count(Timeframe.D1, 1),
    )
    assert rows and rows[-1].close > 0
    time.sleep(1.2)
    history_end = datetime.now(UTC)
    history_start = history_end - timedelta(days=7)
    history, history_measurement = _observed_read(
        lambda: KrakenProvider().fetch_ohlcv(
            "BTC-USD", Timeframe.D1, history_start, history_end, adjusted=False
        ),
        "kraken",
        "fetch_ohlcv",
        operation_cost_override=estimate_kraken_ohlcv_request_count(
            Timeframe.D1, history_start, history_end
        ),
    )
    assert history_measurement.http_requests == 1
    assert history and history[-1].close > 0
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


def test_alpaca_credentialed_account_usage_snapshot():
    """Observe Alpaca's native request-window headers without charging data routing."""

    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    usage, measurement = _observed_read(
        lambda: AlpacaProvider().fetch_account_usage(),
        "alpaca",
        "fetch_account_usage",
    )
    assert usage is not None
    assert usage.provider == "alpaca"
    assert usage.account_plan == "market_data_headers"
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    assert set(dimensions) == {"market_data_requests_per_minute"}
    window = dimensions["market_data_requests_per_minute"]
    assert window.limit is not None and window.limit > 0
    assert window.remaining is not None and 0 <= window.remaining <= window.limit
    assert window.consumed == window.limit - window.remaining
    assert window.reset_at is not None and window.reset_at.tzinfo is not None
    # The native counter is accepted as a durable baseline when the response
    # proves the reviewed limit and remaining count. Alpaca's reset header is
    # integer Unix seconds and may be at the current boundary by the time the
    # response reaches us; the provider-specific two-second skew allowance is
    # safe because admission uses the reviewed rolling 60-second envelope.
    reconciliation = reconcile_native_account_usage("alpaca", usage)
    assert len(reconciliation) == 1
    assert reconciliation[0]["status"] == "reconciled"


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


def test_alpaca_credentialed_assets_and_corporate_actions_page():
    """Exercise one durable Alpaca event page without hiding later cursors."""

    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    provider = AlpacaProvider()
    page, _ = _observed_read(
        lambda: provider.discover_universe_page("EQUITY", 0),
        "alpaca",
        "discover_universe_page",
    )
    assert page["quotes"]
    assert page["total"] >= len(page["quotes"])
    assert all(row["quoteType"] == "EQUITY" for row in page["quotes"])
    page, _ = _observed_read(
        lambda: provider.fetch_instrument_events_page("AAPL"),
        "alpaca",
        "fetch_instrument_events",
        operation_cost_override=1,
    )
    assert isinstance(page.events, list)
    assert isinstance(page.raw_payload, dict)
    assert page.next_page_token is None or isinstance(page.next_page_token, str)


def test_massive_credentialed_reference():
    _require("MASSIVE_API_KEY")
    # This case makes four Stocks asset-class requests (profile, IPO calendar,
    # search, holidays) and one Stocks market-data request (history). The live
    # preflight reserves all five from the same documented 5/minute account
    # bucket. Corporate actions remain a separate two-request case but use the
    # same bucket.
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
        lambda: provider.search_instruments("AAPL", limit=100),
        "massive",
        "search_instruments",
    )
    assert any(row.symbol == "AAPL" for row in search_rows)
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


def test_massive_credentialed_corporate_actions_complete():
    """Read both split and dividend histories; the adapter follows all cursors."""

    _require("MASSIVE_API_KEY")
    events, measurement = _observed_read(
        lambda: MassiveProvider().fetch_instrument_events("AAPL"),
        "massive",
        "fetch_instrument_events",
        operation_cost_override=2,
    )
    assert measurement.http_requests >= 2
    assert isinstance(events, list)
    assert events
    assert all(event.event_time is not None and event.source_event_key for event in events)


def test_massive_credentialed_ipo_cursor_continuation():
    """Force a one-row IPO page and verify the provider cursor retrieves page two."""

    _require("MASSIVE_API_KEY")
    provider = MassiveProvider()

    def fetch_two_pages():
        first = provider.fetch_market_events_page(limit=1)
        assert first["events"]
        cursor = first["next_cursor"]
        assert cursor, "Massive IPO page did not expose a continuation cursor"
        second = provider.fetch_market_events_page(cursor=cursor, limit=1)
        assert second["events"]
        return first, second

    (first, second), measurement = _observed_read(
        fetch_two_pages,
        "massive",
        "fetch_market_events",
        operation_cost_override=2,
    )
    assert measurement.http_requests == 2
    assert first["events"][0].event_key != second["events"][0].event_key


def test_massive_credentialed_otc_ticker_universe_pagination_is_complete(db):
    import asyncio

    _require("MASSIVE_API_KEY")
    from app.models.data_source import DataSource
    from app.models.provider_observation import UniverseDiscoverySnapshot
    from app.services.provider_observations import store_universe_discovery_snapshot
    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
    from tests.unit.conftest import AsyncSessionAdapter

    provider = MassiveProvider()
    data_source = db.query(DataSource).filter_by(name="massive_live_otc_probe").one_or_none()
    if data_source is None:
        data_source = DataSource(
            name="massive_live_otc_probe",
            base_url="https://api.massive.com",
            description="Disposable live-test archive for complete OTC pagination validation",
        )
        db.add(data_source)
        db.flush()

    offset = 0
    pages = 0
    row_count = 0
    identities: set[tuple[str, ...]] = set()
    continuation_urls: set[str] = set()
    raw_pages: dict[int, dict] = {}
    observed_at = datetime.now(UTC)
    archive_session = AsyncSessionAdapter(db)

    while True:
        try:
            page, _ = _observed_read(
                lambda offset=offset: provider.discover_universe_page("OTC", offset),
                "massive",
                "discover_universe_page",
            )
        except ProviderQuotaAdmissionError as exc:
            # Every page reserves one unit from Massive's independently
            # accounted 5-calls/minute reference bucket. If earlier probes
            # filled that rolling window, wait for it to clear and retry this
            # same page; never skip ahead or truncate the universe.
            if "quota exhausted before live operation massive/discover_universe_page" not in str(
                exc
            ):
                raise
            time.sleep(60)
            continue

        pages += 1
        quotes = page.get("quotes") or []
        assert quotes, f"Massive OTC page {pages} unexpectedly returned no rows"
        assert len(quotes) <= 1000
        for quote in quotes:
            raw = quote.get("raw_payload")
            assert quote.get("symbol") and isinstance(raw, dict)
            assert str(raw.get("market") or "").lower() == "otc"
            assert raw.get("active", True) is True
            identity = (
                str(quote["symbol"]).upper(),
                str(raw.get("type") or "").upper(),
                str(quote.get("exchange") or "").upper(),
                str(raw.get("cik") or ""),
                str(raw.get("composite_figi") or "").upper(),
                str(raw.get("share_class_figi") or "").upper(),
                str(raw.get("name") or "").strip().casefold(),
            )
            assert (
                identity not in identities
            ), f"duplicate OTC security across cursor pages: {identity}"
            identities.add(identity)
            row_count += 1

        next_url = page.get("next_url")
        assert page["complete"] is (not bool(next_url))
        raw_pages[offset] = page
        asyncio.run(
            store_universe_discovery_snapshot(
                archive_session,
                data_source_id=data_source.id,
                quote_type="OTC",
                offset=offset,
                page=page,
                observed_at=observed_at,
                fetched_at=observed_at,
            )
        )
        # The production reconciliation worker commits each raw provider page
        # before it normalizes rows. Mirror that crash-safe boundary here.
        db.commit()
        if not next_url:
            assert page.get("next_offset") is None
            break
        assert next_url not in continuation_urls, "Massive OTC pagination repeated a cursor"
        continuation_urls.add(str(next_url))
        next_offset = page.get("next_offset")
        assert isinstance(next_offset, int) and next_offset > offset
        offset = next_offset

    assert pages >= 1
    assert row_count == len(identities) > 0
    archived_pages = (
        db.query(UniverseDiscoverySnapshot)
        .filter_by(
            data_source_id=data_source.id,
            quote_type="OTC",
            observed_at=observed_at,
        )
        .order_by(UniverseDiscoverySnapshot.offset)
        .all()
    )
    assert [snapshot.offset for snapshot in archived_pages] == sorted(raw_pages)
    assert [snapshot.payload["page"] for snapshot in archived_pages] == [
        raw_pages[offset] for offset in sorted(raw_pages)
    ]


def test_marketstack_credentialed_exchange_ticker_pages(db):
    """Read and archive every page for the explicitly configured MIC."""

    import asyncio

    from app.models.data_source import DataSource
    from app.models.provider_observation import UniverseDiscoverySnapshot
    from app.services.provider_observations import store_universe_discovery_snapshot
    from tests.unit.conftest import AsyncSessionAdapter

    _require("MARKETSTACK_API_KEY", "MARKETSTACK_DISCOVERY_EXCHANGE")
    exchange = settings.MARKETSTACK_DISCOVERY_EXCHANGE.strip().upper()
    assert exchange
    provider = MarketstackProvider()
    source_name = f"marketstack_live_tickers_{exchange.lower()}"
    data_source = db.query(DataSource).filter_by(name=source_name).one_or_none()
    if data_source is None:
        data_source = DataSource(
            name=source_name,
            base_url="https://api.marketstack.com/v2",
            description=("Live test archive for complete Marketstack exchange-ticker pagination"),
        )
        db.add(data_source)
        db.flush()

    offset = 0
    total: int | None = None
    raw_count = 0
    pages: dict[int, dict] = {}
    observed_at = datetime.now(UTC)
    archive_session = AsyncSessionAdapter(db)
    while True:
        page, _ = _observed_read(
            lambda offset=offset: provider.discover_universe_page("EQUITY", offset),
            "marketstack",
            "discover_universe_page",
        )
        raw_payload = page.get("raw_payload")
        assert isinstance(raw_payload, dict)
        raw_data = raw_payload.get("data")
        raw_rows = raw_data.get("tickers") if isinstance(raw_data, dict) else None
        pagination = raw_payload.get("pagination")
        assert isinstance(raw_rows, list) and raw_rows
        assert isinstance(raw_data, dict)
        assert raw_data.get("mic") == exchange
        assert isinstance(pagination, dict)
        assert len(raw_rows) == pagination["count"]
        assert pagination["offset"] == offset
        total = page["total"] if total is None else total
        assert page["total"] == total == pagination["total"]
        assert page["total_scope"] == "raw"
        assert page["complete"] is (page.get("next_offset") is None)
        pages[offset] = page
        raw_count += len(raw_rows)

        asyncio.run(
            store_universe_discovery_snapshot(
                archive_session,
                data_source_id=data_source.id,
                quote_type="EQUITY",
                offset=offset,
                page=page,
                observed_at=observed_at,
                fetched_at=observed_at,
            )
        )
        # Commit each quota-consuming response before requesting its successor.
        db.commit()
        next_offset = page.get("next_offset")
        if next_offset is None:
            assert page["complete"] is True
            break
        assert isinstance(next_offset, int) and next_offset > offset
        offset = next_offset

    assert total and raw_count == total
    archived = (
        db.query(UniverseDiscoverySnapshot)
        .filter_by(
            data_source_id=data_source.id,
            quote_type="EQUITY",
            observed_at=observed_at,
        )
        .order_by(UniverseDiscoverySnapshot.offset)
        .all()
    )
    assert [snapshot.offset for snapshot in archived] == sorted(pages)
    assert [snapshot.payload["page"] for snapshot in archived] == [
        pages[page_offset] for page_offset in sorted(pages)
    ]


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


def test_alpha_vantage_credentialed_complete_listing_status():
    """One full CSV request must retain every listing row and raw source field."""

    _require("ALPHA_VANTAGE_API_KEY")
    _skip_unadmitted_live_operation("alpha_vantage", "discover_universe_page")
    page, measurement = _observed_read(
        lambda: AlphaVantageProvider().discover_universe_page("EQUITY", 0),
        "alpha_vantage",
        "discover_universe_page",
    )
    rows = page["quotes"]
    assert page["complete"] is True
    assert page["total"] == len(rows) > 0
    assert measurement.http_requests == 1
    assert isinstance(page.get("raw_payload"), str) and page["raw_payload"]
    # Alpha Vantage's complete CSV has valid symbols whose company-name field
    # is empty. Those rows must remain usable and retain the raw source data;
    # the instrument reconciler can use the symbol provisionally as its name.
    assert all(row.get("symbol") for row in rows)
    assert all(isinstance(row.get("raw_payload"), dict) for row in rows)


def test_alpha_vantage_credentialed_weekly():
    """Exercise the documented raw weekly series with one bounded request."""

    _require("ALPHA_VANTAGE_API_KEY")
    end = datetime.now(UTC)
    rows, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_ohlcv(
            "AAPL",
            Timeframe.W1,
            end - timedelta(days=90),
            end,
            adjusted=False,
        ),
        "alpha_vantage",
        "fetch_ohlcv",
        usage_identity="AAPL:W1",
    )
    assert rows and rows[-1].close > 0
    assert all(row.timeframe is Timeframe.W1 for row in rows)


def test_alpha_vantage_credentialed_monthly():
    """Exercise the documented raw monthly series with one bounded request."""

    _require("ALPHA_VANTAGE_API_KEY")
    end = datetime.now(UTC)
    rows, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_ohlcv(
            "AAPL",
            Timeframe.MN,
            end - timedelta(days=740),
            end,
            adjusted=False,
        ),
        "alpha_vantage",
        "fetch_ohlcv",
        usage_identity="AAPL:MN",
    )
    assert rows and rows[-1].close > 0
    assert all(row.timeframe is Timeframe.MN for row in rows)


def test_alpha_vantage_credentialed_current_price():
    """Exercise the one-request daily-candle current-price wrapper."""

    _require("ALPHA_VANTAGE_API_KEY")
    price, _ = _observed_read(
        lambda: AlphaVantageProvider().get_current_price("AAPL"),
        "alpha_vantage",
        "get_current_price",
    )
    assert price is not None and price > 0


def test_alpha_vantage_credentialed_search():
    """Exercise Alpha Vantage's independently metered SYMBOL_SEARCH endpoint."""

    _require("ALPHA_VANTAGE_API_KEY")
    rows, _ = _observed_read(
        lambda: AlphaVantageProvider().search_instruments("Apple", limit=5),
        "alpha_vantage",
        "search_instruments",
    )
    assert rows
    assert any(row.symbol.upper() == "AAPL" for row in rows)


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


def test_coingecko_credentialed_universe_page():
    """Exercise exactly one market-cap-ordered crypto catalogue page."""

    _require("COINGECKO_API_KEY")
    page, measurement = _observed_read(
        lambda: CoinGeckoProvider().discover_universe_page("CRYPTOCURRENCY", 0),
        "coingecko",
        "discover_universe_page",
        operation_cost_override=1,
    )
    assert measurement.http_requests == 1
    assert page["total"] is None
    assert page["quotes"]
    if len(page["quotes"]) == 250:
        assert page["next_offset"] == 250
        assert page["complete"] is False
    else:
        assert page["next_offset"] is None
        assert page["complete"] is True
    assert all(quote["quoteType"] == "CRYPTOCURRENCY" for quote in page["quotes"])
    assert all(quote.get("coingecko_id") for quote in page["quotes"])


def test_coingecko_credentialed_account_usage_snapshot():
    """Check Pro-only usage entitlement; exercise `/key` only on Pro tiers."""

    _require("COINGECKO_API_KEY")
    if str(settings.COINGECKO_REVIEWED_PLAN or "demo").strip().lower() in {"demo", "free-demo"}:
        with pytest.raises(ProviderNotConfiguredError, match="Pro-only"):
            CoinGeckoProvider().fetch_account_usage()
        return
    usage, measurement = _observed_read(
        lambda: CoinGeckoProvider().fetch_account_usage(),
        "coingecko",
        "fetch_account_usage",
        operation_cost_override=1,
    )
    assert measurement.http_requests == 1
    assert usage.provider == "coingecko"
    assert usage.account_plan
    dimensions = {item.name: item for item in usage.dimensions}
    monthly = dimensions["calls_per_month"]
    assert monthly.limit is not None and monthly.limit > 0
    assert monthly.consumed is not None and monthly.remaining is not None
    assert monthly.consumed + monthly.remaining == monthly.limit
    assert monthly.reset_at is not None and monthly.reset_at.tzinfo is not None
    assert dimensions["calls_per_minute"].limit is not None
    # /key reports the minute cap but not active usage within that window.
    assert dimensions["calls_per_minute"].consumed is None


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


def test_fred_credentialed_current_value():
    """Exercise the latest-observation read independently of history."""

    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("fred", "get_current_price")
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
    price, measurement = _observed_read(
        lambda: FREDProvider().get_current_price("^TNX"),
        "fred",
        "get_current_price",
        operation_cost_override=1,
    )
    assert measurement.http_requests == 1
    assert price is not None and price > 0


def test_finra_credentialed_short_interest():
    from app.providers.registry import provider_missing_routing_controls

    missing = provider_missing_routing_controls("finra", "fetch_short_interest")
    if missing:
        pytest.skip("no provider request made: FINRA data-use review is missing")
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    page, _ = _observed_read(
        lambda: FINRAProvider().fetch_short_interest_page("AAPL", start=date(2020, 1, 1)),
        "finra",
        "fetch_short_interest",
        # FINRA's per-dataset async limiter does not apply to these direct
        # synchronous endpoints. Keep sync requests and the 3 MiB response
        # reservation in place; explicitly declare no async-dimension use.
        dimension_cost_overrides={"asynchronous_requests_per_minute_dataset": 0},
    )
    assert page["complete"] is True
    rows = page["records"]
    assert rows
    assert all(row.settlement_date and row.short_position is not None for row in rows)
    assert any((row.source_identifier or "").upper() == "AAPL" for row in rows)


def test_finra_credentialed_otc_daily_list(db, monkeypatch):
    import asyncio

    from sqlalchemy import select

    from app.models.market_data_foundation import MarketEvent, ProviderPaginationState
    from app.providers.registry import provider_missing_routing_controls
    from app.services.market_events import refresh_market_events
    from tests.unit.conftest import AsyncSessionAdapter

    missing = provider_missing_routing_controls("finra", "fetch_market_events")
    if missing:
        pytest.skip("no provider request made: FINRA data-use review is missing")
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    end = date.today()
    result = _observed_service_read(
        lambda: asyncio.run(
            refresh_market_events(
                AsyncSessionAdapter(db),
                start=end - timedelta(days=45),
                end=end,
                provider_names=["finra"],
                max_pages=None,
            )
        ),
        "finra",
        "fetch_market_events",
        monkeypatch,
    )
    provider_result = result["providers"][0]
    assert result["failures"] == 0, provider_result["failures"]
    assert provider_result["pagination"]["status"] == "complete"
    # A 45-day delta window may legitimately fit on one page when the live
    # market has few events. Completion, a cleared cursor, and the durable
    # page-count equality below prove the entire response was traversed; the
    # multi-page continuation path is covered by deterministic service tests.
    assert provider_result["pagination"]["pages_fetched"] >= 1
    assert provider_result["events"] > 0

    persisted = db.execute(select(MarketEvent).where(MarketEvent.source == "finra")).scalars().all()
    assert persisted
    assert all(row.event_key.startswith("finra:otc_daily_list:") for row in persisted)
    assert all(row.payload for row in persisted)
    state = db.execute(
        select(ProviderPaginationState).where(ProviderPaginationState.provider == "finra")
    ).scalar_one()
    assert state.status == "complete"
    assert state.cursor is None
    assert state.pages_fetched == provider_result["pagination"]["total_pages_fetched"]


def test_finra_otc_directory_credentialed_source(db):
    """Fetch and durably retain every current OTC security-master page."""

    import asyncio

    from app.models.data_source import DataSource
    from app.models.provider_observation import UniverseDiscoverySnapshot
    from app.services.provider_observations import store_universe_discovery_snapshot
    from tests.unit.conftest import AsyncSessionAdapter

    source_kind = settings.FINRA_OTC_SOURCE_KIND.strip().lower()
    configured_source = settings.FINRA_OTC_SYMBOL_DIRECTORY_URL.strip()
    reviewed_source = settings.FINRA_OTC_REVIEWED_SOURCE_URL.strip()
    query_api = source_kind == "finra_otc_query_api"
    orf_reviewed = (
        source_kind == "finra_orf_security_master"
        and settings.FINRA_OTC_SOURCE_REVIEWED
        and settings.FINRA_OTC_SOURCE_EVIDENCE.strip()
        and configured_source
        and reviewed_source == configured_source
        and settings.FINRA_OTC_INACTIVE_SECURITY_MASTER_URL.strip()
        and settings.FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL.strip()
        == settings.FINRA_OTC_INACTIVE_SECURITY_MASTER_URL.strip()
    )
    if not query_api and not orf_reviewed:
        pytest.skip(
            "FINRA OTC source is neither the official Query API nor a completely "
            "reviewed ORF source pair."
        )

    _require("FINRA_OTC_SYMBOL_DIRECTORY_URL")
    if query_api:
        _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
        assert configured_source == (
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster"
        )
    else:
        _require(
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "FINRA_ORF_USERNAME",
            "FINRA_ORF_REFRESH_TOKEN",
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
        )
    provider = FINRAOTCDirectoryProvider()
    data_source = (
        db.query(DataSource).filter_by(name="finra_otc_directory_live_probe").one_or_none()
    )
    if data_source is None:
        data_source = DataSource(
            name="finra_otc_directory_live_probe",
            base_url="https://api.finra.org",
            description="Disposable live-test archive for complete FINRA OTC pagination",
        )
        db.add(data_source)
        db.flush()
    archive_session = AsyncSessionAdapter(db)
    observed_at = datetime.now(UTC)
    offset = 0
    total = None
    symbols: set[str] = set()
    pages = 0
    snapshot_date = None
    while True:
        page, _ = _observed_read(
            lambda offset=offset: provider.discover_universe_page("EQUITY", offset),
            "finra_otc_directory",
            "discover_universe_page",
        )
        assert page["quotes"]
        assert page["total"] >= offset + len(page["quotes"])
        # This is deliberately inside the page loop.  A later transport or
        # validation failure must not erase an already obtained quota-limited
        # response, matching the production reconciler's commit boundary.
        asyncio.run(
            store_universe_discovery_snapshot(
                archive_session,
                data_source_id=data_source.id,
                quote_type="EQUITY",
                offset=offset,
                page=page,
                observed_at=observed_at,
                fetched_at=observed_at,
            )
        )
        db.commit()
        total = page["total"] if total is None else total
        assert page["total"] == total
        page_symbols = [row["symbol"] for row in page["quotes"]]
        assert len(page_symbols) == len(set(page_symbols))
        assert symbols.isdisjoint(page_symbols)
        symbols.update(page_symbols)
        if query_api:
            current_snapshot_date = page["source_snapshot_date"]
            snapshot_date = current_snapshot_date if snapshot_date is None else snapshot_date
            assert current_snapshot_date == snapshot_date
            assert page["source_documents"]
        pages += 1
        next_offset = page.get("next_offset")
        if next_offset is None:
            assert page.get("complete") is True
            break
        assert next_offset == offset + len(page["quotes"])
        offset = next_offset
    assert len(symbols) == total
    assert pages >= 1
    persisted_pages = (
        db.query(UniverseDiscoverySnapshot)
        .filter_by(data_source_id=data_source.id)
        .order_by(UniverseDiscoverySnapshot.offset)
        .all()
    )
    assert len(persisted_pages) == pages
    assert sum(len(snapshot.payload["page"]["quotes"]) for snapshot in persisted_pages) == total
    assert all(snapshot.payload["page"]["source_documents"] for snapshot in persisted_pages)
    assert {
        row["symbol"] for snapshot in persisted_pages for row in snapshot.payload["page"]["quotes"]
    } == symbols
    expected_sources = [os.environ["FINRA_OTC_SYMBOL_DIRECTORY_URL"].strip()]
    if query_api:
        expected_sources.insert(
            0,
            "https://api.finra.org/partitions/group/otcMarket/name/otcSecurityMaster",
        )
    else:
        expected_sources.append(os.environ["FINRA_OTC_INACTIVE_SECURITY_MASTER_URL"].strip())
    assert page["source_files"] == expected_sources
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
        current, _ = _observed_read(
            lambda: provider.get_current_price(symbol),
            provider.name,
            "get_current_price",
            usage_identity=symbol,
        )
        assert current is not None and current > 0
        search_rows, _ = _observed_read(
            lambda: provider.search_instruments("Apple", limit=5),
            provider.name,
            "search_instruments",
        )
        assert search_rows
        assert any(row.symbol.upper() == symbol for row in search_rows)
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
        current, _ = _observed_read(
            lambda: provider.get_current_price(symbol),
            provider.name,
            "get_current_price",
            usage_identity=symbol,
        )
        assert current is not None and current > 0
        profile, _ = _observed_read(
            lambda: provider.get_instrument_profile(symbol), provider.name, "get_instrument_profile"
        )
        assert profile is not None
        assert profile.symbol == symbol
        assert profile.name and profile.exchange
        calendar_page, _ = _observed_read(
            lambda: provider.fetch_market_events_page(
                start=date.today() - timedelta(days=7),
                end=date.today() + timedelta(days=45),
                cursor=None,
            ),
            provider.name,
            "fetch_market_events",
        )
        assert calendar_page["events"]
        assert all(event.event_type == "earnings" for event in calendar_page["events"])
        assert all(event.effective_date is not None for event in calendar_page["events"])
        assert calendar_page["complete"] is (calendar_page["next_cursor"] is None)
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


def test_fmp_long_history_is_paginated_without_gaps():
    """Exercise FMP's multi-request history path with exact durable cost."""

    _require("FMP_API_KEY")
    provider = FMPProvider()
    start = datetime(2000, 1, 1, tzinfo=UTC)
    end = datetime.now(UTC)
    request_count = estimate_fmp_ohlcv_request_count(Timeframe.D1, start, end)
    assert request_count is not None and request_count > 1

    rows, measurement = _observed_read(
        lambda: provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False),
        "fmp",
        "fetch_ohlcv",
        usage_identity="AAPL",
        operation_cost_override=request_count,
    )

    assert rows
    assert measurement.http_requests == request_count
    assert all(left.ts < right.ts for left, right in zip(rows, rows[1:], strict=False))
    chunk_boundary = start.date() + timedelta(days=4499)
    left_page_rows = [row for row in rows if row.ts.date() <= chunk_boundary]
    right_page_rows = [row for row in rows if row.ts.date() > chunk_boundary]
    assert left_page_rows and right_page_rows
    assert (chunk_boundary - left_page_rows[-1].ts.date()).days <= 7
    assert (right_page_rows[0].ts.date() - chunk_boundary).days <= 7


def test_fmp_credentialed_account_usage_snapshot():
    """Reconcile FMP dashboard request and bandwidth counters before data reads."""

    _require("FMP_API_KEY")
    usage, measurement = _observed_read(
        lambda: FMPProvider().fetch_account_usage(),
        "fmp",
        "fetch_account_usage",
    )
    assert usage is not None and usage.provider == "fmp"
    assert usage.account_plan == str(settings.FMP_REVIEWED_PLAN).lower()
    assert measurement.http_requests == 1
    dimensions = {dimension.name: dimension for dimension in usage.dimensions}
    call_dimension = (
        "calls_per_day"
        if str(settings.FMP_REVIEWED_PLAN).lower() == "basic"
        else "calls_per_minute"
    )
    assert set(dimensions) == {call_dimension, "bandwidth_bytes_per_30_days"}
    assert dimensions[call_dimension].limit is not None
    assert dimensions[call_dimension].consumed is not None
    assert dimensions["bandwidth_bytes_per_30_days"].limit >= 500_000_000
    assert dimensions["bandwidth_bytes_per_30_days"].consumed is not None
    reconciliation = reconcile_native_account_usage("fmp", usage)
    assert len(reconciliation) == 2
    assert [item["status"] for item in reconciliation] == ["reconciled", "reconciled"]


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
    assert {
        "credits_per_minute",
        "requests_per_minute",
        "requests_per_day",
    } <= set(dimensions)
    minute = dimensions["credits_per_minute"]
    assert minute.limit is not None and minute.limit > 0
    assert minute.remaining is not None and minute.remaining >= 0
    assert minute.consumed is not None and minute.consumed >= 0
    assert minute.reset_at is not None and minute.reset_at.tzinfo is not None
    # The official SDK describes these body values as request counts. Keep
    # them visible, but do not reinterpret them as weighted API credits.
    minute_requests = dimensions["requests_per_minute"]
    assert minute_requests.unit == "requests"
    assert minute_requests.limit is not None and minute_requests.limit > 0
    assert minute_requests.consumed is not None and minute_requests.consumed >= 0
    daily_requests = dimensions["requests_per_day"]
    assert daily_requests.unit == "requests"
    assert daily_requests.limit == 800
    assert daily_requests.consumed is not None and daily_requests.consumed >= 0
    assert daily_requests.reset_at is not None and daily_requests.reset_at.tzinfo is not None
    reconciliation = reconcile_native_account_usage("twelve_data", usage)
    outcomes = {item["dimension"]: item["status"] for item in reconciliation}
    assert outcomes["credits_per_minute"] == "reconciled"
    assert outcomes["requests_per_day"] == "reconciled"
    # The minute request-count field is observational only: the Basic plan's
    # enforced minute pool is weighted API credits, not request count.
    assert outcomes["requests_per_minute"] == "not_reconciled"


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
    daily_reconciliation = next(
        item for item in reconciliation if item.get("dimension") == "calls_per_day"
    )
    assert daily_reconciliation["status"] == "reconciled"
    assert daily_reconciliation["used_units"] == daily.consumed
    # The endpoint's native minute headers may report a value above the
    # conservative Free-plan cap because official EODHD pages conflict.
    # Retain the observation, but reconcile usage only when it fits the
    # configured local envelope; never let the header widen that envelope.
    minute = dimensions["requests_per_minute"]
    assert minute.limit is not None and minute.limit > 0
    assert minute.remaining is not None and minute.remaining >= 0
    assert minute.consumed is not None and minute.consumed >= 0

    minute_reconciliation = next(
        (item for item in reconciliation if item.get("dimension") == "requests_per_minute"),
        None,
    )
    local_minute_limit = provider_rate_limit_seed("eodhd")["tokens_per_minute"]
    if minute.limit >= local_minute_limit and minute.consumed <= local_minute_limit:
        assert minute_reconciliation is not None
        assert minute_reconciliation["status"] == "reconciled"
    else:
        assert minute_reconciliation is None or minute_reconciliation["status"] == "not_reconciled"


@pytest.mark.live
def test_eodhd_credentialed_delayed_quote():
    """Verify EODHD's documented one-call delayed quote endpoint and schema."""

    _require("EODHD_API_KEY")
    quote, measurement = _observed_read(
        lambda: EODHDProvider().get_current_price("AAPL"),
        "eodhd",
        "get_current_price",
        usage_identity="AAPL",
    )
    assert quote is not None and quote > 0
    assert measurement.http_requests == 1


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


def test_finnhub_credentialed_account_usage_snapshot():
    """Bootstrap the plan's minute counter from native response headers."""

    _require("FINNHUB_API_KEY")
    usage, measurement = _observed_read(
        lambda: FinnhubProvider().fetch_account_usage(),
        "finnhub",
        "fetch_account_usage",
    )
    assert measurement.http_requests == 1
    assert usage.provider == "finnhub"
    assert usage.limit and usage.limit > 0
    assert usage.remaining is not None and 0 <= usage.remaining <= usage.limit
    assert usage.reset_at is not None and usage.reset_at > usage.observed_at
    assert any(dimension.name == "calls_per_minute" for dimension in usage.dimensions)
    assert "x-ratelimit-limit" in usage.response_headers
    assert "x-ratelimit-remaining" in usage.response_headers
    reconciliations = reconcile_native_account_usage("finnhub", usage)
    assert len(reconciliations) == 1
    assert reconciliations[0]["status"] == "reconciled"
    assert reconciliations[0]["dimension"] == "calls_per_minute"


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
    current, _ = _observed_read(
        lambda: FinnhubProvider().get_current_price("AAPL"),
        "finnhub",
        "get_current_price",
        usage_identity="AAPL",
    )
    assert current is not None and current > 0
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
            lambda: FinnhubProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False),
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
