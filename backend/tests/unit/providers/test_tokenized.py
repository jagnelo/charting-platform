from decimal import Decimal
from unittest.mock import Mock, patch

import httpx
import pytest

from app.providers.errors import ProviderResponseError
from app.providers.registry import list_provider_capabilities
from app.providers.tokenized import (
    BybitXStocksProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    RobinhoodTokenProvider,
    XStocksProvider,
)
from app.services.tokenized_assets import tokenized_domain_key


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
            "underlying": {"symbol": "AAPL", "isin": "US0378331005"},
            "currentMultiplier": "0.97",
            "deployments": [
                {"network": "solana", "chainId": 101, "address": "So111"},
            ],
        }
    )
    assert record.asset_id == "x:AAPL"
    assert record.underlying_symbol == "AAPL"
    assert record.underlying_isin == "US0378331005"
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
    for provider in (XStocksProvider(), RobinhoodTokenProvider(), BybitXStocksProvider(), GateTradfiProvider(), KrakenXStocksProvider()):
        assert "tokenized_assets" in list_provider_capabilities(provider.name)
        assert callable(provider.discover_tokenized_assets)
        assert callable(provider.get_tokenized_asset)
        assert callable(provider.get_tokenized_price)


def test_gate_and_kraken_records_keep_provider_symbols_distinct_from_underlyings():
    gate = GateTradfiProvider._record({"symbol": "AAPLx", "underlying_symbol": "AAPL"})
    kraken = KrakenXStocksProvider._record({"symbol": "AAPLx", "base": "AAPL", "quote": "USD"})
    assert gate.symbol == "AAPLx" and gate.underlying_symbol == "AAPL"
    assert kraken.symbol == "AAPLx" and kraken.underlying_symbol == "AAPL"


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
