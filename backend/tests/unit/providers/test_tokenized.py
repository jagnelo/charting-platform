from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import httpx
import pytest

from app.config import settings
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.registry import list_provider_capabilities
from app.providers.tokenized import (
    BybitXStocksProvider,
    DinariTokenProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    OndoGlobalMarketsProvider,
    RobinhoodTokenProvider,
    XStocksProvider,
)
from app.services.tokenized_assets import tokenized_domain_key


@pytest.fixture(autouse=True)
def _authenticated_tokenized_provider_settings(monkeypatch):
    """Keep network-shape fixtures independent of the operator's environment."""

    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "unit-dinari-key-id")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "unit-dinari-secret")
    monkeypatch.setattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "unit-ondo-key")


def test_tokenized_domain_key_is_provider_scoped_and_stable():
    first = tokenized_domain_key("xstocks", "asset-123")
    assert first == tokenized_domain_key("xstocks", "asset-123")
    assert first.startswith("tokenized:xstocks:")
    assert first != tokenized_domain_key("robinhood_tokens", "asset-123")


def test_xstocks_record_preserves_underlying_and_chain_deployment():
    record = XStocksProvider()._record(
        {
            "id": "x:AAPL",
            "symbol": "xAAPL",
            "name": "Apple xStock",
            "underlying": {
                "symbol": "AAPL",
                "isin": "US0378331005",
                "figi": "BBG000B9XRY4",
                "compositeFigi": "BBG000B9XRY4",
                "cusip": "037833100",
            },
            "currentMultiplier": "0.97",
            "deployments": [
                {"network": "solana", "chainId": 101, "address": "So111"},
            ],
        }
    )
    assert record.asset_id == "x:AAPL"
    assert record.underlying_symbol == "AAPL"
    assert record.underlying_figi == "BBG000B9XRY4"
    assert record.underlying_composite_figi == "BBG000B9XRY4"
    assert record.underlying_isin == "US0378331005"
    assert record.underlying_cusip == "037833100"
    assert record.network == "solana"
    assert record.chain_id == 101
    assert record.contract_address == "So111"
    assert record.multiplier == Decimal("0.97")
    assert record.collateral["deployments"][0]["address"] == "So111"


def test_robinhood_record_keeps_debt_security_backing_semantics():
    record = RobinhoodTokenProvider._record(
        {
            "id": "rh-aapl",
            "tokenSymbol": "AAPLx",
            "tokenName": "Apple Stock Token",
            "currentMultiplier": 1,
            "deployments": [{"network": "base", "chainId": 8453, "address": "0xabc"}],
            "status": "ACTIVE",
        }
    )
    assert record.symbol == "AAPLx"
    assert record.backing_type == "economic_exposure_debt_security"
    assert record.chain_id == 8453
    assert record.contract_address == "0xabc"
    assert record.status == "active"


def test_bybit_record_uses_explicit_multiplier_fields_only():
    record = BybitXStocksProvider._record(
        {
            "symbol": "AAPLx",
            "baseCoin": "AAPL",
            "quoteCoin": "USDT",
            "minOrderQty": "0.01",
            "xstocksMultiplier": "0.98",
            "status": "Trading",
        },
        {"lastPrice": "100", "bid1Price": "99", "ask1Price": "101"},
    )
    assert record.multiplier == Decimal("0.98")
    assert record.price == Decimal("100")
    assert record.bid == Decimal("99")
    assert record.ask == Decimal("101")
    assert record.currency == "USDT"


def test_exchange_tokenized_adapters_expose_required_provider_surface():
    for provider in (
        XStocksProvider(),
        RobinhoodTokenProvider(),
        BybitXStocksProvider(),
        GateTradfiProvider(),
        KrakenXStocksProvider(),
    ):
        assert "tokenized_assets" in list_provider_capabilities(provider.name)
        assert callable(provider.discover_tokenized_assets)
        assert callable(provider.get_tokenized_asset)
        assert callable(provider.get_tokenized_price)


def test_only_action_capable_tokenized_adapters_expose_corporate_action_capability():
    assert "tokenized_corporate_actions" in list_provider_capabilities("xstocks")
    assert "tokenized_corporate_actions" in list_provider_capabilities("robinhood_tokens")
    assert "tokenized_corporate_actions" in list_provider_capabilities("dinari")
    for provider in ("bybit_xstocks", "gate_tradfi", "kraken_xstocks", "ondo_global_markets"):
        assert "tokenized_corporate_actions" not in list_provider_capabilities(provider)


def test_gate_and_kraken_records_keep_provider_symbols_distinct_from_underlyings():
    gate = GateTradfiProvider._record({"symbol": "AAPLx", "underlying_symbol": "AAPL"})
    kraken = KrakenXStocksProvider._record({"symbol": "AAPLx", "base": "AAPL", "quote": "USD"})
    assert gate.symbol == "AAPLx" and gate.underlying_symbol == "AAPL"
    assert kraken.symbol == "AAPLx" and kraken.underlying_symbol == "AAPL"


@pytest.mark.parametrize(
    ("builder", "payload"),
    [
        (lambda payload: XStocksProvider()._record(payload), {"id": "x-aapl"}),
        (lambda payload: RobinhoodTokenProvider._record(payload), {"id": "rh-aapl"}),
        (lambda payload: BybitXStocksProvider._record(payload), {}),
        (lambda payload: GateTradfiProvider._record(payload), {}),
        (lambda payload: KrakenXStocksProvider._record(payload), {}),
    ],
)
def test_tokenized_records_reject_missing_provider_identity(builder, payload):
    with pytest.raises(ProviderResponseError, match="without (symbol|asset identifier)"):
        builder(payload)


@pytest.mark.parametrize(
    ("builder", "payload", "quote"),
    [
        (
            lambda payload, quote: XStocksProvider()._record(payload, price=quote),
            {"id": "x-aapl", "symbol": "xAAPL", "name": "Apple"},
            Decimal("NaN"),
        ),
        (
            lambda payload, quote: BybitXStocksProvider._record(payload, quote),
            {"symbol": "AAPLx"},
            {"lastPrice": "Infinity"},
        ),
        (
            lambda payload, quote: GateTradfiProvider._record(payload, quote),
            {"symbol": "AAPLx"},
            {"bid": "NaN"},
        ),
        (
            lambda payload, quote: KrakenXStocksProvider._record(payload, quote),
            {"symbol": "AAPLx"},
            {"c": ["NaN"]},
        ),
    ],
)
def test_tokenized_records_reject_nonfinite_numeric_values(builder, payload, quote):
    with pytest.raises(ProviderResponseError, match="invalid"):
        builder(payload, quote)


def test_tokenized_records_reject_malformed_deployment_rows():
    with pytest.raises(ProviderResponseError, match="deployment row container"):
        XStocksProvider()._record(
            {"id": "x-aapl", "symbol": "xAAPL", "name": "Apple", "deployments": ["invalid"]}
        )


def test_gate_orderbook_null_rows_are_valid_empty_market_data():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {
        "data": {"symbol": "AA", "bids": None, "asks": None},
    }
    asset = GateTradfiProvider._record({"symbol": "AA"})
    with (
        patch.object(GateTradfiProvider, "get_tokenized_asset", return_value=asset),
        patch("app.providers.tokenized.httpx.get", return_value=response),
    ):
        result = GateTradfiProvider().get_tokenized_price("AA")
    assert result is asset
    assert result.price is None
    assert result.bid is None
    assert result.ask is None


def test_gate_orderbook_object_rows_produce_quote():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {
        "data": {
            "symbol": "AAOI",
            "bids": [{"p": "106.07", "user_order": False}],
            "asks": [{"p": "106.72", "user_order": False}],
        },
    }
    asset = GateTradfiProvider._record({"symbol": "AAOI"})
    with (
        patch.object(GateTradfiProvider, "get_tokenized_asset", return_value=asset),
        patch("app.providers.tokenized.httpx.get", return_value=response),
    ):
        result = GateTradfiProvider().get_tokenized_price("AAOI")
    assert result is asset
    assert result.bid == Decimal("106.07")
    assert result.ask == Decimal("106.72")
    assert result.price == Decimal("106.395")


def test_gate_orderbook_scalar_rows_fail_closed():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {"data": {"bids": "invalid", "asks": []}}
    with (
        patch.object(GateTradfiProvider, "get_tokenized_asset", return_value=None),
        patch("app.providers.tokenized.httpx.get", return_value=response),
    ):
        with pytest.raises(ProviderResponseError, match="invalid bids row container"):
            GateTradfiProvider().get_tokenized_price("AA")


def test_robinhood_price_retries_one_bounded_provider_throttle():
    rate_limited = httpx.Response(
        429,
        headers={"retry-after": "0"},
        request=httpx.Request("GET", "https://api.robinhood.com/rhj/prices/AAPLx"),
    )
    ok = Mock()
    ok.raise_for_status.return_value = None
    ok.json.return_value = {"quotes": [{"bid": "99", "ask": "101"}]}
    asset = RobinhoodTokenProvider._record({"id": "rh-aapl", "tokenSymbol": "AAPLx"})
    with (
        patch.object(RobinhoodTokenProvider, "get_tokenized_asset", return_value=asset),
        patch("app.providers.tokenized.httpx.get", side_effect=[rate_limited, ok]) as get,
        patch("app.providers.tokenized.time.sleep") as sleep,
    ):
        result = RobinhoodTokenProvider().get_tokenized_price("AAPLx")
    assert result is not None
    assert result.bid == Decimal("99")
    assert get.call_count == 2
    sleep.assert_called_once()


@pytest.mark.parametrize(
    ("provider_url", "payload"),
    [
        ("https://api.kraken.com/0/public/Ticker", {"error": ["EQuery:Unknown asset pair"]}),
        ("https://api.bybit.com/v5/market/tickers", {"retCode": 10001, "retMsg": "invalid symbol"}),
    ],
)
def test_tokenized_http_success_error_envelopes_do_not_create_synthetic_records(
    provider_url, payload
):
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = payload
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError) as exc_info:
            if "kraken.com" in provider_url:
                KrakenXStocksProvider().get_tokenized_price("AAPLx")
            else:
                BybitXStocksProvider().get_tokenized_price("AAPLx")
    assert exc_info.value.provider_name in {"kraken_xstocks", "bybit_xstocks"}


def test_bybit_success_retcode_and_retmsg_are_not_error_envelope():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": []},
    }
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        assert BybitXStocksProvider().discover_tokenized_assets(page=0, page_size=1) == []


def test_bybit_page_parameter_cannot_silently_truncate_cursor_catalogue():
    response = _response({"retCode": 0, "retMsg": "OK", "result": {"list": []}})
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError, match="opaque cursor pagination"):
            BybitXStocksProvider().discover_tokenized_assets(page=1, page_size=1)


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = payload
    return response


def _dinari_stock():
    return {
        "id": "7f6de6f0-8c15-4c5b-9d7d-9c8d3c16f001",
        "name": "Apple Inc.",
        "display_name": "Apple",
        "symbol": "AAPL",
        "is_fractionable": True,
        "is_tradable": True,
        "tokens": ["eip155:1/0xabc"],
        "composite_figi": "BBG000B9XRY4",
        "cusip": "037833100",
        "cik": "0000320193",
    }


def test_dinari_metadata_preserves_uuid_chain_and_issuer_identifiers(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    response = _response({"data": [_dinari_stock()], "pagination_metadata": {"next": None}})
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        rows = DinariTokenProvider().discover_tokenized_assets(page=0, page_size=25)
    assert len(rows) == 1
    record = rows[0]
    assert record.asset_id == "7f6de6f0-8c15-4c5b-9d7d-9c8d3c16f001"
    assert record.symbol == "AAPL"
    assert record.network == "eip155"
    assert record.chain_id == 1
    assert record.contract_address == "0xabc"
    assert record.collateral["composite_figi"] == "BBG000B9XRY4"
    assert record.collateral["cik"] == "0000320193"
    assert get.call_args.kwargs["headers"] == {
        "X-API-Key-Id": "id-secret",
        "X-API-Secret-Key": "secret-value",
    }
    assert get.call_args.kwargs["params"] == {"limit": 25, "order": "asc"}


def test_dinari_symbol_lookup_uses_documented_server_side_filter(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    response = _response({"data": [_dinari_stock()], "pagination_metadata": {"next": None}})
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        record = DinariTokenProvider().get_tokenized_asset("aapl")
    assert record is not None
    assert record.asset_id == _dinari_stock()["id"]
    assert get.call_args.kwargs["params"] == {
        "limit": 100,
        "order": "asc",
        "symbols": ["AAPL"],
    }


def test_dinari_uuid_lookup_fails_closed_when_catalogue_has_more_pages():
    provider = DinariTokenProvider()
    response = _response(
        {
            "data": [_dinari_stock()],
            "pagination_metadata": {"next": "catalogue-cursor"},
        }
    )
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        with pytest.raises(ProviderResponseError, match="UUID lookup requires explicit"):
            provider.get_tokenized_asset("00000000-0000-0000-0000-000000000000")
    get.assert_called_once()


def test_dinari_uuid_lookup_reuses_current_instance_catalogue_record(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    response = _response({"data": [stock], "pagination_metadata": {"next": None}})
    provider = DinariTokenProvider()
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        discovered = provider.discover_tokenized_assets(page=0, page_size=25)
        resolved = provider.get_tokenized_asset(stock["id"])
    assert discovered[0].asset_id == stock["id"]
    assert resolved is discovered[0]
    get.assert_called_once()


def test_dinari_corporate_actions_combine_symbol_scoped_dividends_and_splits(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    responses = [
        _response({"data": [stock], "pagination_metadata": {"next": None}}),
        _response([{"payment_date": "2026-01-02", "amount": "0.25"}]),
        _response({"data": [{"ex_date": "2026-02-03"}], "pagination_metadata": {"next": None}}),
    ]
    with patch("app.providers.tokenized.httpx.get", side_effect=responses) as get:
        rows = DinariTokenProvider().fetch_tokenized_corporate_actions(symbol="aapl")
    assert [row["action_type"] for row in rows] == ["dividend", "split"]
    assert all(row["stock_id"] == stock["id"] for row in rows)
    assert get.call_count == 3
    assert get.call_args_list[1].args[0].endswith(f"/stocks/{stock['id']}/dividends")
    assert get.call_args_list[2].kwargs["params"] == {"limit": 100, "order": "desc"}


def test_dinari_corporate_actions_global_path_exposes_splits_only(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    response = _response(
        {"data": [{"stock_id": _dinari_stock()["id"]}], "pagination_metadata": {"next": None}}
    )
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        rows = DinariTokenProvider().fetch_tokenized_corporate_actions()
    assert rows == [{"stock_id": _dinari_stock()["id"], "action_type": "split"}]
    assert get.call_args.kwargs["params"] == {"limit": 100, "order": "desc"}


def test_dinari_corporate_actions_reject_unsupported_upcoming_filter(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    with patch("app.providers.tokenized.httpx.get") as get:
        with pytest.raises(ProviderResponseError, match="upcoming filter"):
            DinariTokenProvider().fetch_tokenized_corporate_actions(upcoming=True)
    get.assert_not_called()


def test_dinari_stock_cursor_is_required_and_reused_for_subsequent_pages(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    provider = DinariTokenProvider()
    responses = [
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-1"}}),
        _response({"data": [], "pagination_metadata": {"next": None}}),
    ]
    with patch("app.providers.tokenized.httpx.get", side_effect=responses) as get:
        assert provider.discover_tokenized_assets(page=0, page_size=1)
        assert provider.discover_tokenized_assets(page=1, page_size=1) == []
    assert get.call_args_list[0].kwargs["params"] == {"limit": 20, "order": "asc"}
    assert get.call_args_list[1].kwargs["params"] == {
        "limit": 20,
        "order": "asc",
        "next": "cursor-1",
    }


def test_dinari_stock_cursor_cycle_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    provider = DinariTokenProvider()
    responses = [
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-a"}}),
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-b"}}),
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-a"}}),
    ]
    with patch("app.providers.tokenized.httpx.get", side_effect=responses) as get:
        assert provider.discover_tokenized_assets(page=0, page_size=1)
        assert provider.discover_tokenized_assets(page=1, page_size=1)
        with pytest.raises(ProviderResponseError, match="repeated the stock pagination cursor"):
            provider.discover_tokenized_assets(page=2, page_size=1)
    assert get.call_count == 3


def test_dinari_stock_first_page_resets_cursor_chain(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    provider = DinariTokenProvider()
    responses = [
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-a"}}),
        _response({"data": [], "pagination_metadata": {"next": None}}),
        _response({"data": [stock], "pagination_metadata": {"next": "cursor-a"}}),
    ]
    with patch("app.providers.tokenized.httpx.get", side_effect=responses) as get:
        assert provider.discover_tokenized_assets(page=0, page_size=1)
        assert provider.discover_tokenized_assets(page=1, page_size=1) == []
        assert provider.discover_tokenized_assets(page=0, page_size=1)
    assert get.call_args_list[2].kwargs["params"] == {"limit": 20, "order": "asc"}


def test_dinari_stock_page_without_preceding_cursor_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    provider = DinariTokenProvider()
    with patch("app.providers.tokenized.httpx.get") as get:
        with pytest.raises(ProviderResponseError, match="preceding page cursor"):
            provider.discover_tokenized_assets(page=1, page_size=25)
    get.assert_not_called()


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"next": True},
        {"next": ""},
    ],
)
def test_dinari_stock_cursor_metadata_is_strict(monkeypatch, metadata):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    response = _response({"data": [_dinari_stock()], "pagination_metadata": metadata})
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError, match="pagination"):
            DinariTokenProvider().discover_tokenized_assets(page=0, page_size=25)


def test_dinari_defaults_to_documented_sandbox_host(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_BASE_URL", "")
    assert DinariTokenProvider()._base_url() == "https://api-enterprise.sandbox.dinari.com/api/v2"


@pytest.mark.parametrize(
    ("provider", "settings_to_clear", "message"),
    [
        (
            DinariTokenProvider,
            ("DINARI_API_KEY_ID", "DINARI_API_SECRET_KEY"),
            "DINARI_API_KEY_ID and DINARI_API_SECRET_KEY",
        ),
        (
            OndoGlobalMarketsProvider,
            ("ONDO_GLOBAL_MARKETS_API_KEY",),
            "ONDO_GLOBAL_MARKETS_API_KEY",
        ),
    ],
)
def test_authenticated_tokenized_adapters_fail_closed_before_http(
    monkeypatch, provider, settings_to_clear, message
):
    for setting_name in settings_to_clear:
        monkeypatch.setattr(settings, setting_name, "")
    with patch("app.providers.tokenized.httpx.get") as get:
        with pytest.raises(ProviderNotConfiguredError, match=message):
            provider().discover_tokenized_assets(page=0, page_size=1)
    get.assert_not_called()


def test_dinari_current_price_quote_and_history_validate_provider_identity():
    stock = _dinari_stock()
    responses = [
        _response([stock]),
        _response(
            {
                "stock_id": stock["id"],
                "price": "201.25",
                "timestamp": "2026-09-10T12:00:00Z",
            }
        ),
    ]
    with patch("app.providers.tokenized.httpx.get", side_effect=responses) as get:
        record = DinariTokenProvider().get_tokenized_price(stock["id"])
    assert record is not None
    assert record.price == Decimal("201.25")
    assert record.observed_at == datetime(2026, 9, 10, 12, tzinfo=UTC)
    assert get.call_count == 2

    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response([stock]),
            _response(
                {
                    "stock_id": stock["id"],
                    "bid_price": "201.20",
                    "bid_size": "10",
                    "ask_price": "201.30",
                    "ask_size": "12",
                    "timestamp": "2026-09-10T12:00:01Z",
                }
            ),
        ],
    ):
        quote = DinariTokenProvider().get_tokenized_quote(stock["id"])
    assert quote is not None
    assert quote.bid == Decimal("201.20")
    assert quote.ask == Decimal("201.30")

    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response([stock]),
            _response(
                [
                    {
                        "timestamp": 1_757_500_800,
                        "open": 199,
                        "high": 203,
                        "low": 198,
                        "close": 201,
                    }
                ]
            ),
        ],
    ):
        history = DinariTokenProvider().fetch_tokenized_historical_prices(stock["id"])
    assert history[0]["stock_id"] == stock["id"]
    assert history[0]["close"] == Decimal("201")
    assert history[0]["timespan"] == "DAY"


def test_dinari_history_news_and_split_shapes_fail_closed():
    stock = _dinari_stock()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[_response([stock]), _response([{"timestamp": 1, "open": 1}])],
    ):
        with pytest.raises(ProviderResponseError, match="invalid historical price row"):
            DinariTokenProvider().fetch_tokenized_historical_prices("AAPL")
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[_response([stock]), _response([{"article_url": "https://example.test"}])],
    ):
        with pytest.raises(ProviderResponseError, match="incomplete stock news"):
            DinariTokenProvider().fetch_tokenized_news("AAPL")
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response([stock]),
            _response({"data": [], "pagination_metadata": {"next": None}}),
        ],
    ) as get:
        assert DinariTokenProvider().fetch_tokenized_splits("AAPL") == []
    assert get.call_args_list[-1].kwargs["params"] == {"limit": 100, "order": "desc"}


def test_dinari_split_cursor_continuation_is_explicitly_reused():
    stock = _dinari_stock()
    provider = DinariTokenProvider()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response({"data": [stock], "pagination_metadata": {"next": None}}),
            _response(
                {
                    "data": [{"ex_date": "2026-01-02"}],
                    "pagination_metadata": {"next": "split-cursor"},
                }
            ),
            _response({"data": [stock], "pagination_metadata": {"next": None}}),
            _response({"data": [{"ex_date": "2025-01-02"}], "pagination_metadata": {"next": None}}),
        ],
    ) as get:
        assert (
            provider.fetch_tokenized_splits("AAPL", page=1, page_size=1)[0]["ex_date"]
            == "2026-01-02"
        )
        assert (
            provider.fetch_tokenized_splits("AAPL", page=2, page_size=1)[0]["ex_date"]
            == "2025-01-02"
        )
    assert get.call_args_list[1].kwargs["params"] == {"limit": 20, "order": "desc"}
    assert get.call_args_list[3].kwargs["params"] == {
        "limit": 20,
        "order": "desc",
        "next": "split-cursor",
    }


def test_dinari_split_page_without_preceding_cursor_fails_closed():
    with patch("app.providers.tokenized.httpx.get") as get:
        with pytest.raises(ProviderResponseError, match="preceding page cursor"):
            DinariTokenProvider()._fetch_global_splits(page=2, page_size=1)
    get.assert_not_called()


def test_dinari_global_split_cursor_continuation_is_explicitly_reused():
    provider = DinariTokenProvider()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response(
                {"data": [{"stock_id": "stock-1"}], "pagination_metadata": {"next": "cursor-1"}}
            ),
            _response({"data": [{"stock_id": "stock-2"}], "pagination_metadata": {"next": None}}),
        ],
    ) as get:
        assert provider.fetch_tokenized_corporate_actions(page=1, page_size=1) == [
            {"stock_id": "stock-1", "action_type": "split"}
        ]
        assert provider.fetch_tokenized_corporate_actions(page=2, page_size=1) == [
            {"stock_id": "stock-2", "action_type": "split"}
        ]
    assert get.call_args_list[1].kwargs["params"] == {
        "limit": 20,
        "order": "desc",
        "next": "cursor-1",
    }


def test_dinari_global_split_cursor_cycle_fails_closed():
    provider = DinariTokenProvider()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response(
                {"data": [{"stock_id": "stock-1"}], "pagination_metadata": {"next": "cursor-a"}}
            ),
            _response(
                {"data": [{"stock_id": "stock-2"}], "pagination_metadata": {"next": "cursor-b"}}
            ),
            _response(
                {"data": [{"stock_id": "stock-3"}], "pagination_metadata": {"next": "cursor-a"}}
            ),
        ],
    ) as get:
        assert provider.fetch_tokenized_corporate_actions(page=1, page_size=1)
        assert provider.fetch_tokenized_corporate_actions(page=2, page_size=1)
        with pytest.raises(ProviderResponseError, match="repeated the split pagination cursor"):
            provider.fetch_tokenized_corporate_actions(page=3, page_size=1)
    assert get.call_count == 3


def test_dinari_symbol_action_pages_continue_splits_without_replaying_dividends():
    stock = _dinari_stock()
    provider = DinariTokenProvider()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response({"data": [stock], "pagination_metadata": {"next": None}}),
            _response([{"payment_date": "2026-01-01", "amount": "0.25"}]),
            _response(
                {"data": [{"ex_date": "2026-01-02"}], "pagination_metadata": {"next": "cursor-1"}}
            ),
            _response({"data": [stock], "pagination_metadata": {"next": None}}),
            _response({"data": [{"ex_date": "2025-01-02"}], "pagination_metadata": {"next": None}}),
        ],
    ) as get:
        first = provider.fetch_tokenized_corporate_actions(symbol="AAPL", page=1, page_size=1)
        second = provider.fetch_tokenized_corporate_actions(symbol="AAPL", page=2, page_size=1)
    assert [row["action_type"] for row in first] == ["dividend", "split"]
    assert second == [{"ex_date": "2025-01-02", "action_type": "split", "stock_id": stock["id"]}]
    assert get.call_args_list[4].kwargs["params"] == {
        "limit": 20,
        "order": "desc",
        "next": "cursor-1",
    }


def _ondo_metadata():
    return {
        "symbol": "AAPLon",
        "ticker": "AAPL",
        "underlyingName": "Apple",
        "displayName": "Apple (Ondo Tokenized)",
        "addresses": [
            {"networkChainId": "ethereum-1", "address": "0xdef", "decimals": 18},
        ],
        "tags": {"assetClass": "Equities", "instrumentType": "Stock"},
        "isin": "US0378331005",
    }


def test_ondo_metadata_and_price_keep_both_market_identities():
    metadata = _ondo_metadata()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[
            _response([metadata]),
            _response(
                {
                    "primaryMarket": {"symbol": "AAPLon", "price": "171.38"},
                    "underlyingMarket": {"ticker": "AAPL", "price": "228.33"},
                    "timestamp": 1_757_500_800_000,
                }
            ),
        ],
    ) as get:
        record = OndoGlobalMarketsProvider().get_tokenized_price("AAPL")
    assert record is not None
    assert record.asset_id == "AAPLon"
    assert record.underlying_symbol == "AAPL"
    assert record.underlying_isin == "US0378331005"
    assert record.network == "ethereum"
    assert record.chain_id == 1
    assert record.price == Decimal("171.38")
    assert get.call_count == 2


def test_ondo_market_summary_preserves_primary_history_and_underlying_metrics():
    metadata = _ondo_metadata()
    market = {
        "primaryMarket": {
            "symbol": "AAPLon",
            "price": "171.38",
            "priceChange24h": "1.25",
            "priceChangePct24h": "0.73",
            "priceHistory24h": [
                {"timestamp": 1_757_500_800_000, "price": "170.00"},
                {"timestamp": 1_757_504_400_000, "price": "171.38"},
            ],
            "totalHolders": 7,
            "sharesMultiplier": "1",
            "tradableSessions": ["regular", "overnight"],
        },
        "underlyingMarket": {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "price": "228.33",
            "priceHigh52w": "260.10",
            "priceLow52w": "164.08",
            "volume": "1851321",
            "averageVolume": "3610882",
            "sharesOutstanding": "15000000000",
            "marketCap": "3424950000000",
        },
        "timestamp": 1_757_504_400_000,
    }
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[_response([metadata]), _response(market)],
    ) as get:
        result = OndoGlobalMarketsProvider().fetch_tokenized_market_data("AAPLon")
    assert result is not None
    assert result["symbol"] == "AAPLon"
    assert result["primary_market"]["price"] == Decimal("171.38")
    assert result["primary_market"]["price_history_24h"][1]["price"] == Decimal("171.38")
    assert result["primary_market"]["total_holders"] == 7
    assert result["primary_market"]["tradable_sessions"] == ["regular", "overnight"]
    assert result["underlying_market"]["name"] == "Apple Inc."
    assert result["underlying_market"]["market_cap"] == Decimal("3424950000000")
    assert get.call_count == 2


@pytest.mark.parametrize(
    "market",
    [
        {
            "primaryMarket": {"symbol": "AAPLon", "price": "bad"},
            "underlyingMarket": {"ticker": "AAPL", "name": "Apple", "price": "1"},
            "timestamp": 1_757_504_400_000,
        },
        {
            "primaryMarket": {
                "symbol": "AAPLon",
                "price": "1",
                "priceHistory24h": "invalid",
            },
            "underlyingMarket": {"ticker": "AAPL", "name": "Apple", "price": "1"},
            "timestamp": 1_757_504_400_000,
        },
        {
            "primaryMarket": {"symbol": "AAPLon", "price": "1"},
            "underlyingMarket": {"ticker": "AAPL", "name": "Apple", "price": "1"},
            "timestamp": 0,
        },
    ],
)
def test_ondo_market_summary_rejects_malformed_provider_fields(market):
    metadata = _ondo_metadata()
    with patch(
        "app.providers.tokenized.httpx.get",
        side_effect=[_response([metadata]), _response(market)],
    ):
        with pytest.raises(ProviderResponseError):
            OndoGlobalMarketsProvider().fetch_tokenized_market_data("AAPLon")


def test_ondo_ohlc_requires_documented_interval_range_and_validates_both_markets():
    metadata = _ondo_metadata()
    ohlc = {
        "interval": "1day",
        "range": "3month",
        "primaryMarket": {
            "symbol": "AAPLon",
            "data": [
                {"timestamp": 1_757_500_800_000, "open": "1", "high": "2", "low": "1", "close": "2"}
            ],
        },
        "underlyingMarket": {
            "ticker": "AAPL",
            "data": [
                {"timestamp": 1_757_500_800_000, "open": "1", "high": "2", "low": "1", "close": "2"}
            ],
        },
    }
    with patch(
        "app.providers.tokenized.httpx.get", side_effect=[_response([metadata]), _response(ohlc)]
    ):
        rows = OndoGlobalMarketsProvider().fetch_tokenized_ohlc(
            "AAPLon", range_="3month", market="both"
        )
    assert {row["market"] for row in rows} == {"primary", "underlying"}
    assert rows[0]["close"] == Decimal("2")
    with pytest.raises(ProviderResponseError, match="interval/range"):
        OndoGlobalMarketsProvider().fetch_tokenized_ohlc("AAPLon", interval="1min", range_="1month")


@pytest.mark.parametrize(
    ("provider", "payload"),
    [
        (DinariTokenProvider(), {"data": "invalid", "pagination_metadata": {}}),
        (OndoGlobalMarketsProvider(), {"symbol": "AAPLon", "tags": {}, "addresses": "invalid"}),
    ],
)
def test_new_tokenized_provider_metadata_containers_fail_closed(provider, payload):
    response = _response(payload if provider.name == "dinari" else [payload])
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError):
            provider.discover_tokenized_assets(page=0, page_size=1)


@pytest.mark.parametrize(
    ("provider", "payload"),
    [
        (XStocksProvider(), {"nodes": "invalid"}),
        (RobinhoodTokenProvider(), {"assets": "invalid"}),
        (BybitXStocksProvider(), {"retCode": 0, "result": {"list": "invalid"}}),
        (GateTradfiProvider(), {"data": {"list": "invalid"}}),
        (KrakenXStocksProvider(), {"result": {"AAPLx/USD": "invalid"}}),
    ],
)
def test_tokenized_documented_row_containers_fail_closed(provider, payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = payload
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError):
            provider.discover_tokenized_assets(page=0, page_size=1)


def test_xstocks_corporate_actions_reject_invalid_rows_and_bound_history_page():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {
        "nodes": [{"id": "split-1"}, "not-an-event"],
    }
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        with pytest.raises(ProviderResponseError, match="non-object nodes row"):
            XStocksProvider().fetch_tokenized_corporate_actions(
                symbol="xAAPL", page=0, page_size=1000
            )
    get.assert_called_once()
    assert get.call_args.kwargs["params"] == {
        "page": 1,
        "pageSize": 100,
        "symbol": "xAAPL",
    }


def test_robinhood_corporate_actions_reject_invalid_rows_before_filtering():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.return_value = {
        "corpActions": [
            {"tokenSymbol": "AAPLx", "type": "dividend"},
            {"tokenSymbol": "MSFTx", "type": "dividend"},
            "not-an-event",
        ],
    }
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError, match="non-object corpActions row"):
            RobinhoodTokenProvider().fetch_tokenized_corporate_actions(symbol="aaplx")


def test_tokenized_http_rate_limit_is_typed_redacted_and_keeps_retry_metadata():
    response = httpx.Response(
        429,
        headers={"Retry-After": "7", "X-RateLimit-Remaining": "0"},
        request=httpx.Request(
            "GET", "https://api.xstocks.fi/api/v2/public/assets?apiKey=secret-token"
        ),
    )
    with (
        patch("app.providers.tokenized.settings.XSTOCKS_API_KEY", "secret-token"),
        patch("app.providers.tokenized.httpx.get", return_value=response),
    ):
        with pytest.raises(ProviderRateLimitError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.provider_name == "xstocks"
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["retry-after"] == "7"
    assert exc_info.value.retry_at is not None
    assert "secret-token" not in str(exc_info.value)


def test_tokenized_http_request_failure_is_typed():
    failure = httpx.ConnectError(
        "connection failed for https://api.xstocks.fi/api/v2/public/assets?apiKey=secret-token",
        request=httpx.Request(
            "GET", "https://api.xstocks.fi/api/v2/public/assets?apiKey=secret-token"
        ),
    )
    with patch("app.providers.tokenized.httpx.get", side_effect=failure):
        with pytest.raises(ProviderResponseError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.provider_name == "xstocks"
    assert "secret-token" not in str(exc_info.value)


def test_tokenized_http_non_rate_status_is_typed_and_redacted():
    response = httpx.Response(
        503,
        request=httpx.Request(
            "GET", "https://api.xstocks.fi/api/v2/public/assets?apiKey=secret-token"
        ),
    )
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.provider_name == "xstocks"
    assert exc_info.value.status_code == 503
    assert "secret-token" not in str(exc_info.value)


def test_dinari_sandbox_transient_500_uses_bounded_provider_specific_retry(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id-secret")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret-value")
    stock = _dinari_stock()
    failed = httpx.Response(
        500,
        request=httpx.Request("GET", "https://api-enterprise.sandbox.dinari.com/api/v2/market_data/stocks/"),
    )
    recovered = _response({"data": [stock], "pagination_metadata": {"next": None}})
    with patch("app.providers.tokenized.httpx.get", side_effect=[failed, recovered]) as get:
        rows = DinariTokenProvider().discover_tokenized_assets(page=0, page_size=1)
    assert rows[0].asset_id == stock["id"]
    assert get.call_count == 2


def test_tokenized_http_non_rate_status_does_not_retry_other_providers():
    response = httpx.Response(
        500,
        request=httpx.Request("GET", "https://api.xstocks.fi/api/v2/public/assets"),
    )
    with patch("app.providers.tokenized.httpx.get", return_value=response) as get:
        with pytest.raises(ProviderResponseError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.status_code == 500
    get.assert_called_once()


def test_tokenized_http_invalid_json_is_typed():
    response = Mock()
    response.raise_for_status.return_value = None
    response.status_code = 200
    response.json.side_effect = ValueError("malformed payload")
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.provider_name == "xstocks"
    assert str(exc_info.value) == "provider returned invalid JSON"


def test_tokenized_http_non_finite_retry_after_is_safe():
    response = httpx.Response(
        429,
        headers={"Retry-After": "NaN"},
        request=httpx.Request("GET", "https://api.xstocks.fi/api/v2/public/assets"),
    )
    with patch("app.providers.tokenized.httpx.get", return_value=response):
        with pytest.raises(ProviderRateLimitError) as exc_info:
            XStocksProvider().discover_tokenized_assets(page=0, page_size=1)
    assert exc_info.value.retry_at is None
