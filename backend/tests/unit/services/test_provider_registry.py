from app.config import provider_rate_limit_seed, settings
from app.providers.configured import OPTIONAL_PROVIDER_DESCRIPTORS
from app.providers.registry import (
    get_default_discovery_provider,
    get_default_event_provider,
    get_default_market_data_provider,
    get_default_metadata_provider,
    get_default_options_provider,
    get_identifier_provider,
    get_option_chain_provider,
    get_price_history_provider,
    get_provider,
    get_tokenized_corporate_action_provider,
    list_provider_capabilities,
    provider_configuration_required,
    provider_is_configured,
    provider_missing_routing_controls,
    provider_missing_settings,
    provider_required_settings,
    provider_routing_control_settings,
    provider_supports_instrument,
)


def test_backend_env_example_keeps_yfinance_out_of_new_workstation_chains():
    import json
    from pathlib import Path

    lines = Path(__file__).parents[3].joinpath(".env.example").read_text().splitlines()
    seed_line = next(line for line in lines if line.startswith("PROVIDER_CHAIN_SEEDS="))
    seeds = json.loads(seed_line.split("=", 1)[1])
    identifier_line = next(
        line for line in lines if line.startswith("IDENTIFIER_PROVIDER_PRIORITY=")
    )
    assert json.loads(identifier_line.split("=", 1)[1]) == ["openfigi"]
    assert seeds["option_chain"] == ["marketdata_app"]
    assert seeds["instrument_events"] == ["alpaca", "edgar", "finnhub", "alpha_vantage"]
    assert "finra_otc_directory" in seeds["universe_discovery"]
    assert "alpaca" not in seeds["instrument_search"]
    assert all(
        "yfinance" not in providers
        for capability, providers in seeds.items()
        if capability != "option_chain"
    )
    assert (
        next(line for line in lines if line.startswith("ENABLE_LEGACY_YFINANCE_FALLBACK="))
        == "ENABLE_LEGACY_YFINANCE_FALLBACK=false"
    )
    readme = Path(__file__).parents[4].joinpath("README.md").read_text()
    assert "DEFAULT_MARKET_DATA_PROVIDER=alpaca" in readme
    assert "DEFAULT_METADATA_PROVIDER=edgar" in readme
    assert "DEFAULT_EVENT_PROVIDER=alpaca" in readme
    assert "DEFAULT_DISCOVERY_PROVIDER=alpaca" in readme
    assert 'IDENTIFIER_PROVIDER_PRIORITY=["openfigi"]' in readme
    assert "ENABLE_LEGACY_YFINANCE_FALLBACK=false" in readme


class TestProviderRegistry:
    def test_descriptor_base_urls_match_concrete_adapters(self):
        """Admin-facing descriptor URLs must not drift from transport hosts."""

        concrete_names = {
            name
            for name in OPTIONAL_PROVIDER_DESCRIPTORS
            if getattr(get_provider(name), "base_url", None)
        }
        assert concrete_names == set(OPTIONAL_PROVIDER_DESCRIPTORS)
        for name in sorted(concrete_names):
            assert OPTIONAL_PROVIDER_DESCRIPTORS[name].base_url == get_provider(name).base_url

    def test_new_workstation_defaults_are_free_source_first(self):
        assert get_default_market_data_provider().name == "alpaca"
        assert get_default_metadata_provider().name == "edgar"
        assert get_default_event_provider().name == "alpaca"
        assert get_default_discovery_provider().name == "alpaca"

    def test_yfinance_exposes_price_and_options_capabilities(self):
        capabilities = set(list_provider_capabilities("yfinance"))
        assert "price_history" in capabilities
        assert "instrument_metadata" in capabilities
        assert "option_chain" in capabilities
        assert "options_current" in capabilities
        assert "futures_history" in capabilities

    def test_crypto_provider_exposes_explicit_crypto_history_capability(self):
        assert "crypto_history" in list_provider_capabilities("binance")

    def test_instrument_routing_does_not_treat_crypto_ohlcv_as_equity_support(self):
        assert provider_supports_instrument(
            "alpaca", asset_class="Equity", instrument_type="Stock"
        )
        assert not provider_supports_instrument(
            "kraken", asset_class="Equity", instrument_type="Stock"
        )
        assert provider_supports_instrument(
            "kraken", asset_class="Cryptocurrency", instrument_type="Crypto Spot"
        )
        assert not provider_supports_instrument(
            "unknown_provider", asset_class="Equity", instrument_type="Stock"
        )

    def test_tokenized_provider_routing_is_class_aware(self):
        for provider in (
            "xstocks",
            "robinhood_tokens",
            "bybit_xstocks",
            "gate_tradfi",
            "kraken_xstocks",
            "dinari",
            "ondo_global_markets",
        ):
            assert provider_supports_instrument(
                provider,
                asset_class="Tokenized Securities",
                instrument_type="Tokenized Security",
            )
            assert not provider_supports_instrument(
                provider, asset_class="Equity", instrument_type="Stock"
            )

    def test_tokenized_corporate_action_registry_is_capability_specific(self):
        assert get_tokenized_corporate_action_provider("xstocks").name == "xstocks"
        assert get_tokenized_corporate_action_provider("robinhood_tokens").name == "robinhood_tokens"
        try:
            get_tokenized_corporate_action_provider("bybit_xstocks")
        except KeyError:
            pass
        else:
            raise AssertionError("bybit_xstocks should not expose corporate-action capability")

    def test_tokenized_provider_credentials_are_explicit_and_fail_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "")
        monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "")
        assert provider_required_settings("dinari") == (
            "DINARI_API_KEY_ID",
            "DINARI_API_SECRET_KEY",
        )
        assert provider_is_configured("dinari") is False
        monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "id")
        monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "secret")
        assert provider_is_configured("dinari") is True

        monkeypatch.setattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "")
        assert provider_required_settings("ondo_global_markets") == (
            "ONDO_GLOBAL_MARKETS_API_KEY",
        )
        assert provider_is_configured("ondo_global_markets") is False
        monkeypatch.setattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "key")
        assert provider_is_configured("ondo_global_markets") is True

    def test_openfigi_is_registered_as_identifier_provider(self):
        provider = get_identifier_provider("openfigi")
        assert provider.name == "openfigi"

    def test_openfigi_is_not_an_option_chain_provider(self):
        try:
            get_option_chain_provider("openfigi")
        except KeyError:
            pass
        else:
            raise AssertionError("openfigi should not expose option-chain capability")

    def test_default_options_provider_is_api_first(self):
        provider = get_default_options_provider()
        assert provider.name == "marketdata_app"

    def test_otc_directory_is_in_the_default_universe_chain_but_requires_source_config(self):
        assert "finra_otc_directory" in settings.PROVIDER_CHAIN_SEEDS["universe_discovery"]
        assert provider_configuration_required("finra_otc_directory") is True
        assert provider_configuration_required("marketstack") is True

    def test_ibkr_gateway_requires_url_and_session_cookie(self, monkeypatch):
        monkeypatch.setattr(settings, "IBKR_READ_ONLY_URL", "")
        monkeypatch.setattr(settings, "IBKR_READ_ONLY_SESSION_COOKIE", "")
        assert provider_configuration_required("ibkr") is True
        assert provider_required_settings("ibkr") == (
            "IBKR_READ_ONLY_URL",
            "IBKR_READ_ONLY_SESSION_COOKIE",
        )
        assert provider_is_configured("ibkr") is False
        monkeypatch.setattr(settings, "IBKR_READ_ONLY_URL", "https://gateway.test")
        assert provider_is_configured("ibkr") is False
        monkeypatch.setattr(settings, "IBKR_READ_ONLY_SESSION_COOKIE", "session")
        assert provider_is_configured("ibkr") is True

    def test_otc_directory_configuration_is_fail_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
        assert provider_is_configured("finra_otc_directory") is False
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://example.test/otc-directory.txt",
        )
        assert provider_is_configured("finra_otc_directory") is True

    def test_marketstack_discovery_configuration_is_fail_closed(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "demo")
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")
        assert provider_is_configured("marketstack") is False
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "XNAS")
        assert provider_is_configured("marketstack") is True
        assert provider_required_settings("marketstack") == (
            "MARKETSTACK_API_KEY",
            "MARKETSTACK_DISCOVERY_EXCHANGE",
        )
        assert provider_missing_settings("marketstack") == []

    def test_marketstack_history_does_not_require_discovery_scope(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "demo")
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")
        assert provider_required_settings("marketstack", "fetch_ohlcv:D1") == (
            "MARKETSTACK_API_KEY",
        )
        assert provider_missing_settings("marketstack", "fetch_ohlcv:D1") == []
        assert provider_is_configured("marketstack", "fetch_ohlcv:D1") is True
        assert provider_is_configured("marketstack", "bulk_fetch:D1") is True
        assert provider_is_configured("marketstack", "discover_universe_page") is False
        assert provider_missing_settings("marketstack", "discover_universe_page") == [
            "MARKETSTACK_DISCOVERY_EXCHANGE",
        ]

    def test_provider_missing_settings_reports_names_only(self, monkeypatch):
        monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "")
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")
        assert provider_missing_settings("marketstack") == [
            "MARKETSTACK_API_KEY",
            "MARKETSTACK_DISCOVERY_EXCHANGE",
        ]

    def test_massive_legacy_alias_satisfies_required_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "MASSIVE_API_KEY", "")
        monkeypatch.setattr(settings, "MARKETDATA_API_KEY", "legacy-key")
        assert provider_required_settings("massive") == (
            "MASSIVE_API_KEY",
            "MARKETDATA_API_KEY",
        )
        assert provider_missing_settings("massive") == []

    def test_routing_control_diagnostics_report_names_without_values(self, monkeypatch):
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 0)
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 0)
        monkeypatch.setattr(settings, "FINRA_OTC_OPERATION_COSTS", {})
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 0)
        monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "")
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", False)
        monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {})
        monkeypatch.setattr(settings, "FMP_OPERATION_BYTE_BOUNDS", {})
        assert provider_routing_control_settings("finra") == (
            "FINRA_ASYNC_MAX_RESULT_BYTES",
        )
        assert provider_missing_routing_controls("finra") == [
            "FINRA_ASYNC_MAX_RESULT_BYTES"
        ]
        assert provider_routing_control_settings("alpaca") == (
            "ALPACA_CORPORATE_ACTIONS_MAX_PAGES",
        )
        assert provider_missing_routing_controls("alpaca") == [
            "ALPACA_CORPORATE_ACTIONS_MAX_PAGES"
        ]
        assert provider_missing_routing_controls("alpaca", "fetch_ohlcv:D1") == []
        assert provider_missing_routing_controls(
            "alpaca", "fetch_instrument_events"
        ) == ["ALPACA_CORPORATE_ACTIONS_MAX_PAGES"]
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", True)
        assert provider_missing_routing_controls("alpaca") == [
            "ALPACA_CORPORATE_ACTIONS_MAX_PAGES"
        ]
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 4)
        assert provider_missing_routing_controls("alpaca") == []
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", True)
        assert provider_missing_routing_controls("finra") == [
            "FINRA_ASYNC_MAX_RESULT_BYTES"
        ]
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 1024)
        assert provider_routing_control_settings("finra_otc_directory") == (
            "FINRA_OTC_OPERATION_COSTS",
            "FINRA_OTC_TERMS_REVIEWED",
            "FINRA_OTC_COMPLETENESS_REVIEWED",
            "FINRA_OTC_REDISTRIBUTION_REVIEWED",
            "FINRA_OTC_POLL_INTERVAL_SECONDS",
        )
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_OPERATION_COSTS",
            "FINRA_OTC_TERMS_REVIEWED",
            "FINRA_OTC_COMPLETENESS_REVIEWED",
            "FINRA_OTC_REDISTRIBUTION_REVIEWED",
            "FINRA_OTC_POLL_INTERVAL_SECONDS",
        ]
        assert provider_routing_control_settings("fred") == (
            "FRED_REVIEWED_LIMIT_SCOPE",
            "FRED_REVIEWED_REQUESTS_PER_MINUTE",
            "FRED_SERIES_TERMS_REVIEWED",
        )
        assert provider_missing_routing_controls("fred") == [
            "FRED_REVIEWED_LIMIT_SCOPE",
            "FRED_REVIEWED_REQUESTS_PER_MINUTE",
            "FRED_SERIES_TERMS_REVIEWED",
        ]
        assert provider_missing_routing_controls("tiingo") == [
            "TIINGO_OPERATION_BYTE_BOUNDS"
        ]
        assert provider_missing_routing_controls("fmp") == ["FMP_OPERATION_BYTE_BOUNDS"]
        assert provider_routing_control_settings("marketdata_app") == (
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        )
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        ]

        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 1024)
        monkeypatch.setattr(
            settings,
            "TIINGO_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
            },
        )
        monkeypatch.setattr(
            settings,
            "FMP_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "get_instrument_profile": 1,
                "fetch_market_events": 1,
                "discover_universe_page": 1,
            },
        )
        assert provider_missing_routing_controls("finra") == []
        monkeypatch.setattr(
            settings,
            "TIINGO_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
            },
        )
        assert provider_missing_routing_controls("tiingo") == [
            "TIINGO_OPERATION_BYTE_BOUNDS"
        ]
        monkeypatch.setattr(
            settings,
            "TIINGO_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": True,
                "bulk_fetch": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
            },
        )
        assert provider_missing_routing_controls("tiingo") == [
            "TIINGO_OPERATION_BYTE_BOUNDS"
        ]
        monkeypatch.setattr(
            settings,
            "TIINGO_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1,
                "fetch_latest_ohlcv": 1,
                "get_current_price": 1,
                "bulk_fetch": 1,
                "search_instruments": 1,
                "get_instrument_profile": 1,
            },
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_OPERATION_COSTS",
            {"discover_universe_page": 3, "reconcile_universe_page": 3},
        )
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
        assert provider_missing_routing_controls("finra_otc_directory") == []
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", "true")
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_TERMS_REVIEWED"
        ]
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", True)
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_POLL_INTERVAL_SECONDS"
        ]
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_OPERATION_COSTS",
            {"discover_universe_page": True, "reconcile_universe_page": 3},
        )
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_OPERATION_COSTS"
        ]
        monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 60)
        monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", True)
        assert provider_missing_routing_controls("fred") == []
        monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", "true")
        assert provider_missing_routing_controls("fred") == [
            "FRED_SERIES_TERMS_REVIEWED"
        ]
        monkeypatch.setattr(settings, "FRED_SERIES_TERMS_REVIEWED", True)
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", True)
        assert provider_missing_routing_controls("fred") == [
            "FRED_REVIEWED_REQUESTS_PER_MINUTE"
        ]
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 60)
        fred_seed = provider_rate_limit_seed("fred")
        assert fred_seed["quota_scope"] == "api_key"
        assert fred_seed["quota_contract"]["unknown_dimensions"] == []
        assert fred_seed["quota_contract"]["dimensions"][0]["limit"] == 60
        assert fred_seed["quota_contract"]["dimensions"][0]["scope"] == "api_key"
        assert provider_missing_routing_controls("tiingo") == []
        assert provider_missing_routing_controls("fmp") == []
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
        assert provider_missing_routing_controls("marketdata_app") == []
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", True)
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        ]

    def test_yfinance_is_available_as_price_history_provider(self):
        provider = get_price_history_provider("yfinance")
        assert provider.name == "yfinance"

    def test_etf_holdings_internal_provider_is_registered_without_market_capabilities(self):
        provider = get_provider("etf_holdings_internal")
        assert provider.name == "etf_holdings_internal"
        assert list_provider_capabilities("etf_holdings_internal") == []
