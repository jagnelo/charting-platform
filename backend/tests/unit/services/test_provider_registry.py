from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import (
    FRED_MAPPED_SERIES_IDS,
    alpaca_persistent_storage_authority_missing,
    alpha_vantage_persistent_storage_authority_missing,
    binance_persistent_storage_authority_missing,
    bybit_xstocks_market_data_use_authority_missing,
    coinbase_market_data_use_authority_missing,
    coingecko_market_data_use_authority_missing,
    eodhd_persistent_storage_authority_missing,
    finnhub_persistent_storage_authority_missing,
    finra_equity_data_use_authority_missing,
    fmp_persistent_storage_authority_missing,
    fred_data_use_controls_missing,
    fred_series_rights_authorized,
    fred_series_rights_missing,
    gate_tradfi_persistent_storage_authority_missing,
    ibkr_persistent_storage_authority_missing,
    kraken_market_data_use_authority_missing,
    kraken_persistent_storage_authority_missing,
    marketdata_app_persistent_storage_authority_missing,
    marketstack_persistent_storage_authority_missing,
    nasdaq_directory_persistent_storage_authority_missing,
    ondo_global_markets_persistent_storage_authority_missing,
    provider_rate_limit_seed,
    provider_terms_exception_missing,
    robinhood_tokens_persistent_storage_authority_missing,
    settings,
    tiingo_persistent_storage_authority_missing,
    tradier_persistent_storage_authority_missing,
    twelve_data_persistent_storage_authority_missing,
    xstocks_market_data_use_authority_missing,
    yfinance_persistent_storage_authority_missing,
)
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
    get_provider_usage_profile,
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
    assert seeds["instrument_events"] == [
        "alpaca",
        "massive",
        "edgar",
        "finnhub",
        "alpha_vantage",
    ]
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


def test_marketstack_does_not_advertise_data_read_as_account_usage():
    capabilities = set(list_provider_capabilities("marketstack"))

    assert "price_history" in capabilities
    assert "latest_price" in capabilities
    assert "universe_discovery" in capabilities
    assert "account_usage" not in capabilities


def test_owner_storage_approval_is_global_and_legacy_attestations_are_ignored():
    cases = (
        (alpaca_persistent_storage_authority_missing, "ALPACA"),
        (alpha_vantage_persistent_storage_authority_missing, "ALPHA_VANTAGE"),
        (binance_persistent_storage_authority_missing, "BINANCE"),
        (eodhd_persistent_storage_authority_missing, "EODHD"),
        (finnhub_persistent_storage_authority_missing, "FINNHUB"),
        (kraken_persistent_storage_authority_missing, "KRAKEN"),
        (marketstack_persistent_storage_authority_missing, "MARKETSTACK"),
    )
    for check, prefix in cases:
        source = SimpleNamespace(
            **{
                f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED": False,
                f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE": "",
                f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE": "",
                f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT": None,
                f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT": datetime.now(UTC) - timedelta(seconds=1),
            }
        )
        assert check(source=source) == []


def test_binance_and_kraken_routes_do_not_require_owner_storage_attestations(monkeypatch):
    # Exercise both default-deny behavior and the owner's explicit blanket
    # private-use decision independently of this machine's runtime setting.
    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
    # The Binance time/header read reconciles quota state only; it does not
    # persist provider market data and is needed to bootstrap safe admission.
    assert provider_missing_routing_controls("binance", "fetch_account_usage") == []
    assert provider_missing_routing_controls("binance") == []
    kraken_controls = (
        "KRAKEN_MARKET_DATA_USE_AUTHORIZED",
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "KRAKEN_MARKET_DATA_USE_REVIEWED_AT",
    )
    assert provider_missing_routing_controls("kraken") == list(kraken_controls)
    assert provider_missing_routing_controls("kraken_xstocks") == list(kraken_controls)

    monkeypatch.setattr(settings, "KRAKEN_MARKET_DATA_USE_AUTHORIZED", True)
    monkeypatch.setattr(settings, "KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE", "unit-test grant")
    monkeypatch.setattr(
        settings,
        "KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "single_user_personal_automated_internal_persistent_archive_nonredistributed",
    )
    monkeypatch.setattr(
        settings, "KRAKEN_MARKET_DATA_USE_REVIEWED_AT", datetime.now(UTC) - timedelta(minutes=1)
    )
    monkeypatch.setattr(settings, "KRAKEN_MARKET_DATA_USE_EXPIRES_AT", None)

    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", True)
    assert provider_missing_routing_controls("binance") == []
    assert provider_missing_routing_controls("kraken") == []
    assert provider_missing_routing_controls("kraken_xstocks") == []


def test_kraken_xstocks_entitlement_discloses_eea_api_and_live_coverage_limit():
    entitlement = settings.PROVIDER_ENTITLEMENT_SEEDS["kraken_xstocks"]

    assert (
        "EEA clients cannot access xStocks order-book trading through Kraken API"
        in (entitlement["usage_terms"])
    )
    assert "API Partner Program" in entitlement["usage_terms"]
    assert (
        "does not establish a standalone read-only xStocks entitlement"
        in (entitlement["usage_terms"])
    )
    assert (
        "2026-10-09 live AssetPairs read from Portugal returned no xStocks pairs"
        in (entitlement["venue_coverage"])
    )


def test_kraken_written_authority_expiry_is_enforced():
    now = datetime.now(UTC)
    authority = SimpleNamespace(
        KRAKEN_MARKET_DATA_USE_AUTHORIZED=True,
        KRAKEN_MARKET_DATA_USE_AUTHORITY_REFERENCE="unit-test grant",
        KRAKEN_MARKET_DATA_USE_AUTHORITY_SCOPE=(
            "single_user_personal_automated_internal_persistent_archive_nonredistributed"
        ),
        KRAKEN_MARKET_DATA_USE_REVIEWED_AT=now - timedelta(minutes=1),
        KRAKEN_MARKET_DATA_USE_EXPIRES_AT=now - timedelta(seconds=1),
    )
    assert kraken_market_data_use_authority_missing(now, source=authority) == [
        "KRAKEN_MARKET_DATA_USE_EXPIRES_AT"
    ]


def test_alpaca_and_alpha_vantage_routes_ignore_legacy_owner_storage_flags(monkeypatch):
    for provider, prefix in (("alpaca", "ALPACA"), ("alpha_vantage", "ALPHA_VANTAGE")):
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)
        assert provider_missing_routing_controls(provider) == []

    # Alpaca's bounded usage snapshot is control-plane evidence, not a
    # persistent market-data route, so it remains usable to reconcile limits.
    assert provider_missing_routing_controls("alpaca", "fetch_account_usage") == []

    for prefix in ("ALPACA", "ALPHA_VANTAGE"):
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "unit-test provider grant",
        )
        monkeypatch.setattr(
            settings,
            f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_automated_internal_display_perpetual_archive",
        )
        monkeypatch.setattr(
            settings,
            f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT",
            datetime.now(UTC) - timedelta(minutes=1),
        )
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)

    assert provider_missing_routing_controls("alpaca") == []
    assert provider_missing_routing_controls("alpha_vantage") == []


def test_nasdaq_directory_archive_does_not_require_owner_storage_authority(monkeypatch):
    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORIZED", False)
    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_REVIEWED_AT", None)
    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_EXPIRES_AT", None)
    assert provider_missing_routing_controls("nasdaq") == []

    monkeypatch.setattr(settings, "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
        "unit-test source grant",
    )
    monkeypatch.setattr(
        settings,
        "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
        "written_internal_noncommercial_automated_perpetual_directory_archive",
    )
    monkeypatch.setattr(
        settings,
        "NASDAQ_DIRECTORY_PERSISTENT_STORAGE_REVIEWED_AT",
        datetime.now(UTC) - timedelta(minutes=1),
    )
    assert nasdaq_directory_persistent_storage_authority_missing() == []
    assert provider_missing_routing_controls("nasdaq") == []


def test_tokenized_and_deferred_provider_routes_do_not_require_owner_storage_authority(
    monkeypatch,
):
    providers = (
        (
            "robinhood_tokens",
            "ROBINHOOD_TOKENS",
            robinhood_tokens_persistent_storage_authority_missing,
            "written_single_user_automated_internal_display_perpetual_archive",
        ),
        (
            "gate_tradfi",
            "GATE_TRADFI",
            gate_tradfi_persistent_storage_authority_missing,
            "written_single_user_automated_internal_display_perpetual_archive",
        ),
        (
            "tradier",
            "TRADIER",
            tradier_persistent_storage_authority_missing,
            "written_single_user_automated_internal_display_perpetual_archive_with_upstream_market_data_rights",
        ),
        (
            "ibkr",
            "IBKR",
            ibkr_persistent_storage_authority_missing,
            "written_single_user_automated_internal_display_perpetual_archive_with_exchange_rights",
        ),
        (
            "ondo_global_markets",
            "ONDO_GLOBAL_MARKETS",
            ondo_global_markets_persistent_storage_authority_missing,
            "written_approved_api_client_automated_internal_display_perpetual_archive",
        ),
        (
            "yfinance",
            "YFINANCE",
            yfinance_persistent_storage_authority_missing,
            "written_yahoo_automated_collection_internal_display_perpetual_archive",
        ),
    )
    reviewed_at = datetime.now(UTC) - timedelta(minutes=1)
    for provider, prefix, checker, scope in providers:
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)
        assert checker() == []
        assert provider_missing_routing_controls(provider) == []
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "unit-test, provider-specific written archive grant",
        )
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE", scope)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT", reviewed_at)
        monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)
        assert checker() == []
        assert provider_missing_routing_controls(provider) == []

    for provider in (
        "robinhood_tokens",
        "gate_tradfi",
        "tradier",
        "ibkr",
        "ondo_global_markets",
        "yfinance",
    ):
        assert provider_routing_control_settings(provider) == ()


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
        assert provider_supports_instrument("alpaca", asset_class="Equity", instrument_type="Stock")
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
        assert (
            get_tokenized_corporate_action_provider("robinhood_tokens").name == "robinhood_tokens"
        )
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
        assert provider_required_settings("ondo_global_markets") == ("ONDO_GLOBAL_MARKETS_API_KEY",)
        assert provider_is_configured("ondo_global_markets") is False
        monkeypatch.setattr(settings, "ONDO_GLOBAL_MARKETS_API_KEY", "key")
        assert provider_is_configured("ondo_global_markets") is True

    def test_dinari_canary_requires_complete_explicit_sandbox_quota_profile(self, monkeypatch):
        monkeypatch.setattr(settings, "DINARI_SANDBOX_QUOTA_PROFILE", {})
        assert provider_routing_control_settings("dinari") == ("DINARI_SANDBOX_QUOTA_PROFILE",)
        assert provider_missing_routing_controls("dinari") == ["DINARI_SANDBOX_QUOTA_PROFILE"]

        operation_costs = {
            "discover_tokenized_assets": 3,
            "get_tokenized_asset": 3,
            "get_tokenized_price": 6,
            "get_tokenized_quote": 6,
            "fetch_tokenized_historical_prices": 6,
            "fetch_tokenized_news": 6,
            "fetch_tokenized_dividends": 6,
            "fetch_tokenized_splits": 6,
            "fetch_tokenized_corporate_actions": 9,
        }
        reviewed_profile = {
            "quota_scope": "api_key",
            "quota_source": "unit-test provider account quota review",
            "quota_contract": {
                "reset": "rolling",
                "unknown_dimensions": [],
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 60,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "source": "unit-test provider account quota review",
                        "reset": "rolling",
                    }
                ],
            },
            "operation_costs": operation_costs,
        }
        monkeypatch.setattr(settings, "DINARI_SANDBOX_QUOTA_PROFILE", reviewed_profile)
        seed = provider_rate_limit_seed("dinari")
        assert seed["quota_contract"] == reviewed_profile["quota_contract"]
        assert get_provider_usage_profile("dinari")["operation_costs"] == operation_costs
        assert provider_missing_routing_controls("dinari") == []

        reviewed_profile["operation_costs"]["get_tokenized_price"] = 2
        assert (
            "DINARI_SANDBOX_QUOTA_PROFILE.operation_costs.get_tokenized_price.minimum_6_requests"
            in provider_missing_routing_controls("dinari")
        )
        reviewed_profile["operation_costs"]["get_tokenized_price"] = 6

        reviewed_profile["operation_costs"].pop("fetch_tokenized_corporate_actions")
        assert "DINARI_SANDBOX_QUOTA_PROFILE.operation_costs.fetch_tokenized_corporate_actions" in (
            provider_missing_routing_controls("dinari")
        )

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
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://example.test/otc-directory.txt",
        )
        assert provider_is_configured("finra_otc_directory") is False
        assert "FINRA_OTC_SOURCE_KIND" in provider_missing_routing_controls("finra_otc_directory")
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
        )
        monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "/tmp/orf-state.json")
        assert provider_is_configured("finra_otc_directory") is True

    def test_orf_otc_source_requires_complete_pair_and_traqs_credentials(self, monkeypatch):
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://apidownload.finratraqs.org/active",
        )
        monkeypatch.setattr(settings, "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", "")
        monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "")
        assert provider_required_settings("finra_otc_directory") == (
            "FINRA_OTC_SOURCE_KIND",
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "FINRA_ORF_USERNAME",
            "FINRA_ORF_REFRESH_TOKEN",
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
        )
        assert provider_missing_settings("finra_otc_directory") == [
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "FINRA_ORF_USERNAME",
            "FINRA_ORF_REFRESH_TOKEN",
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
        ]
        assert "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL" in provider_routing_control_settings(
            "finra_otc_directory"
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
            "https://apidownload.finratraqs.org/inactive",
        )
        monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
        monkeypatch.setattr(
            settings,
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
            "/run/provider-secrets/finra-orf/refresh-token.json",
        )
        assert provider_missing_settings("finra_otc_directory") == []
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", False)
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "")
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "")
        assert "FINRA_ORF_REFRESH_TOKEN_STATE_FILE" in provider_missing_routing_controls(
            "finra_otc_directory"
        )
        monkeypatch.setattr(
            settings,
            "FINRA_ORF_REFRESH_TOKEN_STATE_FILE",
            "/run/provider-secrets/finra-orf/refresh-token.json",
        )
        assert "FINRA_ORF_CUSIP_LICENSE_EVIDENCE" not in provider_missing_routing_controls(
            "finra_otc_directory"
        )
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
        assert "FINRA_ORF_CUSIP_LICENSE_EVIDENCE" in provider_missing_routing_controls(
            "finra_otc_directory"
        )
        monkeypatch.setattr(
            settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "unit-test CGS license reference"
        )
        assert "FINRA_ORF_CUSIP_LICENSE_EVIDENCE" not in provider_missing_routing_controls(
            "finra_otc_directory"
        )

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
        monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 0)
        monkeypatch.setattr(settings, "MASSIVE_CORPORATE_ACTIONS_MAX_PAGES", 0)
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 0)
        monkeypatch.setattr(settings, "FINRA_EQUITY_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FINRA_EQUITY_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "FINRA_EQUITY_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "FINRA_EQUITY_DATA_USE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FINRA_OTC_OPERATION_COSTS", {})
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "")
        monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
        monkeypatch.setattr(settings, "FINRA_OTC_REVIEWED_SOURCE_URL", "")
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 0)
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", False)
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "")
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
        monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "")
        monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_APPLICATION_USER_SCOPE", "")
        monkeypatch.setattr(settings, "FRED_APPLICATION_USER_SCOPE_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "")
        monkeypatch.setattr(settings, "FRED_SERIES_RIGHTS_EVIDENCE", {})
        monkeypatch.setattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "")
        monkeypatch.setattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "ALPACA_REVIEWED_RESET", "")
        monkeypatch.setattr(settings, "ALPACA_QUOTA_EVIDENCE", "")
        for prefix in ("ALPACA", "ALPHA_VANTAGE"):
            monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", True)
            monkeypatch.setattr(
                settings,
                f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
                "unit-test reviewed grant",
            )
            monkeypatch.setattr(
                settings,
                f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
                "written_single_user_automated_internal_display_perpetual_archive",
            )
            monkeypatch.setattr(
                settings,
                f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT",
                datetime.now(UTC) - timedelta(minutes=1),
            )
            monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FINNHUB_REVIEWED_MINUTE_RESET", "")
        monkeypatch.setattr(settings, "FINNHUB_REVIEWED_SECOND_RESET", "")
        monkeypatch.setattr(settings, "FINNHUB_MINUTE_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "FINNHUB_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FINNHUB_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "FINNHUB_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "FINNHUB_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "FINNHUB_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 0)
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "")
        monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED", False)
        monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE", "")
        monkeypatch.setattr(settings, "EODHD_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "EODHD_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "EODHD_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "EODHD_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "EODHD_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "COINGECKO_MARKET_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "COINGECKO_MARKET_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "COINGECKO_MARKET_DATA_USE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", False)
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", "")
        monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {})
        monkeypatch.setattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "")
        monkeypatch.setattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "")
        monkeypatch.setattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FMP_OPERATION_BYTE_BOUNDS", {})
        monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "")
        monkeypatch.setattr(settings, "FMP_STOCK_LIST_ENTITLED", False)
        monkeypatch.setattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "")
        monkeypatch.setattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_EXPIRES_AT", None)
        # The local worktree may be configured with an active MarketData.app
        # trial. This diagnostics test verifies the unconfigured path, so keep
        # its account-plan inputs hermetic instead of inheriting local env.
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_REVIEWED_AT", None)
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_EXPIRES_AT", None)
        assert provider_routing_control_settings("finra") == ("FINRA_ASYNC_MAX_RESULT_BYTES",)
        assert provider_missing_routing_controls("finra") == ["FINRA_ASYNC_MAX_RESULT_BYTES"]
        assert provider_routing_control_settings("finra", "fetch_short_interest") == ()
        assert provider_missing_routing_controls("finra", "fetch_short_interest") == []
        assert provider_routing_control_settings("finra", "fetch_market_events") == ()
        assert provider_missing_routing_controls("finra", "fetch_market_events") == []
        assert provider_routing_control_settings("alpaca") == ()
        assert provider_missing_routing_controls("alpaca") == []
        assert provider_routing_control_settings("alpaca", "fetch_ohlcv:D1") == ()
        assert provider_missing_routing_controls("alpaca", "fetch_ohlcv:D1") == []
        assert provider_missing_routing_controls("alpaca", "fetch_instrument_events") == []
        assert provider_routing_control_settings("alpaca", "fetch_account_usage") == ()
        assert provider_missing_routing_controls("alpaca", "fetch_account_usage") == []
        assert provider_routing_control_settings("massive") == (
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
            "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
        )
        assert provider_missing_routing_controls("massive") == [
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
        ]
        massive_missing = [
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
        ]
        assert provider_missing_routing_controls("massive", "get_instrument_profile") == (
            massive_missing
        )
        assert provider_missing_routing_controls("massive", "fetch_instrument_events") == (
            massive_missing
        )
        assert provider_missing_routing_controls("massive", "discover_universe_page:OTC:0") == (
            massive_missing
        )
        assert provider_missing_routing_controls("massive", "fetch_ohlcv:D1") == [
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
        ]
        assert provider_routing_control_settings("massive", "fetch_market_holidays") == (
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
            "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
        )
        assert provider_missing_routing_controls("massive", "fetch_market_holidays") == [
            "MASSIVE_MARKET_DATA_USE_AUTHORIZED",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
        ]
        coingecko_controls = (
            "COINGECKO_MARKET_DATA_USE_AUTHORIZED",
            "COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "COINGECKO_MARKET_DATA_USE_REVIEWED_AT",
            "COINGECKO_MARKET_DATA_USE_EXPIRES_AT",
        )
        assert provider_routing_control_settings("coingecko") == coingecko_controls
        assert provider_missing_routing_controls("coingecko") == list(coingecko_controls[:4])
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", True)
        assert provider_missing_routing_controls("alpaca") == []
        monkeypatch.setattr(settings, "ALPACA_CORPORATE_ACTIONS_MAX_PAGES", 4)
        assert provider_missing_routing_controls("alpaca") == []
        monkeypatch.setattr(settings, "ALPACA_REVIEWED_RESET", "fixed_minute")
        monkeypatch.setattr(settings, "ALPACA_QUOTA_EVIDENCE", "operator review")
        assert provider_missing_routing_controls("alpaca") == []
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", True)
        assert provider_missing_routing_controls("finra") == ["FINRA_ASYNC_MAX_RESULT_BYTES"]
        monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 1024)
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
        controls = provider_routing_control_settings("finra_otc_directory")
        assert "FINRA_OTC_PERSISTENT_STORAGE_AUTHORIZED" not in controls
        assert not any("PERSISTENT_STORAGE" in name for name in controls)

        required = set(provider_missing_routing_controls("finra_otc_directory"))
        assert {
            "FINRA_OTC_OPERATION_COSTS",
            "FINRA_OTC_SOURCE_REVIEWED",
            "FINRA_OTC_SOURCE_EVIDENCE",
            "FINRA_OTC_SOURCE_KIND",
            "FINRA_OTC_TERMS_REVIEWED",
        }.issubset(required)

        active_url = (
            "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
            "action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF"
        )
        inactive_url = (
            "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
            "action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF"
        )
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_OPERATION_COSTS",
            {"discover_universe_page": 3, "reconcile_universe_page": 3},
        )
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "FINRA ORF terms reference")
        monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", active_url)
        monkeypatch.setattr(settings, "FINRA_OTC_REVIEWED_SOURCE_URL", active_url)
        monkeypatch.setattr(settings, "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", inactive_url)
        monkeypatch.setattr(settings, "FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL", inactive_url)
        monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "/tmp/orf-token-state")
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", False)
        monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "")
        # No CUSIP license is needed when FINRA returns that field blank.
        # The legacy owner-storage settings deliberately remain unset.
        assert provider_missing_routing_controls("finra_otc_directory") == []
        assert provider_routing_control_settings("fred") == (
            "FRED_REVIEWED_LIMIT_SCOPE",
            "FRED_REVIEWED_REQUESTS_PER_MINUTE",
            "FRED_REVIEWED_QUOTA_EVIDENCE",
            "FRED_REVIEWED_RESET",
            "FRED_RESET_EVIDENCE",
            "FRED_APPLICATION_USER_SCOPE",
            "FRED_APPLICATION_USER_SCOPE_EVIDENCE",
            "FRED_AUTOMATED_USE_AUTHORIZED",
            "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
            "FRED_SERIES_RIGHTS_EVIDENCE",
        )
        assert provider_missing_routing_controls("fred") == [
            "FRED_REVIEWED_LIMIT_SCOPE",
            "FRED_REVIEWED_REQUESTS_PER_MINUTE",
            "FRED_REVIEWED_QUOTA_EVIDENCE",
            "FRED_REVIEWED_RESET",
            "FRED_RESET_EVIDENCE",
            "FRED_APPLICATION_USER_SCOPE",
            "FRED_APPLICATION_USER_SCOPE_EVIDENCE",
            "FRED_AUTOMATED_USE_AUTHORIZED",
            "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
            "FRED_SERIES_RIGHTS_EVIDENCE",
        ]
        assert provider_routing_control_settings("alpha_vantage") == (
            "ALPHA_VANTAGE_REVIEWED_RESET",
            "ALPHA_VANTAGE_QUOTA_EVIDENCE",
        )
        # The documented numeric daily cap is admission-safe through the
        # provider-scoped rolling envelope; native-reset settings remain
        # optional overrides rather than mandatory controls.
        assert provider_missing_routing_controls("alpha_vantage") == []
        assert provider_routing_control_settings("finnhub") == (
            "FINNHUB_REVIEWED_MINUTE_RESET",
            "FINNHUB_REVIEWED_SECOND_RESET",
            "FINNHUB_MINUTE_QUOTA_EVIDENCE",
            "FINNHUB_SECOND_QUOTA_EVIDENCE",
        )
        assert provider_missing_routing_controls("finnhub") == []
        assert provider_routing_control_settings("coinbase") == (
            "COINBASE_MARKET_DATA_USE_AUTHORIZED",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        )
        assert provider_missing_routing_controls("coinbase") == [
            "COINBASE_MARKET_DATA_USE_AUTHORIZED",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
        ]
        assert provider_routing_control_settings("xstocks") == (
            "XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        )
        assert provider_missing_routing_controls("xstocks") == [
            "XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
        ]
        # This diagnostic test exercises the deliberately unconfigured path;
        # keep it independent of per-worktree jurisdiction settings.
        monkeypatch.setattr(settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", False)
        monkeypatch.setattr(settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "")
        monkeypatch.setattr(settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE", "")
        monkeypatch.setattr(settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", None)
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", False
        )
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE", ""
        )
        assert provider_routing_control_settings("bybit_xstocks") == (
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
        )
        assert provider_missing_routing_controls("bybit_xstocks") == [
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
        ]
        assert provider_missing_routing_controls("tiingo") == [
            "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "TIINGO_OPERATION_BYTE_BOUNDS",
        ]
        assert provider_missing_routing_controls("fmp") == [
            "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "FMP_OPERATION_BYTE_BOUNDS",
        ]
        assert provider_routing_control_settings("marketstack") == (
            "MARKETSTACK_REVIEWED_MONTHLY_LIMIT",
            "MARKETSTACK_REVIEWED_MONTHLY_RESET",
            "MARKETSTACK_QUOTA_EVIDENCE",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "MARKETSTACK_DISCOVERY_MAX_PAGE_COST",
            "MARKETSTACK_DISCOVERY_COST_EVIDENCE",
        )
        assert provider_routing_control_settings("marketstack", "fetch_ohlcv:D1") == (
            "MARKETSTACK_REVIEWED_MONTHLY_LIMIT",
            "MARKETSTACK_REVIEWED_MONTHLY_RESET",
            "MARKETSTACK_QUOTA_EVIDENCE",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
        )
        # Pin quota inputs here so local account configuration cannot affect
        # the assertion about missing provider-specific discovery controls.
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 100)
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "calendar_month_utc")
        monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "unit test account review")
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_MAX_PAGE_COST", 0)
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_COST_EVIDENCE", "")
        assert provider_missing_routing_controls("marketstack") == [
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "MARKETSTACK_DISCOVERY_MAX_PAGE_COST",
            "MARKETSTACK_DISCOVERY_COST_EVIDENCE",
        ]
        # The uncertain page charge is discovery-only; it must not block a
        # separate, appropriately entitled history operation.
        assert provider_missing_routing_controls("marketstack", "fetch_ohlcv:D1") == [
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
        ]
        assert provider_routing_control_settings("eodhd") == (
            "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED",
            "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
        )
        assert provider_routing_control_settings("marketdata_app") == (
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED",
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
        )
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED",
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        ]
        assert (
            provider_routing_control_settings("marketdata_app", operation="fetch_account_usage")
            == ()
        )
        assert (
            provider_missing_routing_controls("marketdata_app", operation="fetch_account_usage")
            == []
        )
        assert provider_routing_control_settings("twelve_data") == (
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
        )
        assert provider_missing_routing_controls("twelve_data") == [
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
            "TWELVE_DATA_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
        ]
        assert provider_routing_control_settings("twelve_data", "fetch_account_usage") == ()
        assert provider_missing_routing_controls("twelve_data", "fetch_account_usage") == []

        reviewed_at = datetime.now(UTC) - timedelta(minutes=1)
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "written tier override",
        )
        monkeypatch.setattr(
            settings,
            "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_internal_display_non_display_perpetual_retention",
        )
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_REVIEWED_AT", reviewed_at)
        assert twelve_data_persistent_storage_authority_missing() == []
        monkeypatch.setattr(
            settings,
            "TWELVE_DATA_PERSISTENT_STORAGE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        assert twelve_data_persistent_storage_authority_missing() == []
        monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_EXPIRES_AT", None)

        reviewed_at = datetime.now(UTC) - timedelta(minutes=1)
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "TIINGO_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "written approval"
        )
        monkeypatch.setattr(
            settings,
            "TIINGO_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_perpetual_archive_retention",
        )
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_REVIEWED_AT", reviewed_at)
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "FMP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE", "written approval"
        )
        monkeypatch.setattr(
            settings,
            "FMP_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_perpetual_archive",
        )
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_REVIEWED_AT", reviewed_at)
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
                "fetch_account_usage": 1,
            },
        )
        monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "calendar_day_utc")
        monkeypatch.setattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "rolling_30_days")
        monkeypatch.setattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "daily review")
        monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "bandwidth review")
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 100)
        monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "calendar_month_utc")
        monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "current account review")
        monkeypatch.setattr(settings, "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "MARKETSTACK_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "reviewed provider archive terms",
        )
        monkeypatch.setattr(settings, "MARKETSTACK_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "provider and upstream written archive grant",
        )
        monkeypatch.setattr(
            settings,
            "MARKETSTACK_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_automated_internal_display_perpetual_archive",
        )
        monkeypatch.setattr(
            settings,
            "MARKETSTACK_PERSISTENT_STORAGE_REVIEWED_AT",
            datetime.now(UTC) - timedelta(minutes=1),
        )
        monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_MAX_PAGE_COST", 1000)
        monkeypatch.setattr(
            settings, "MARKETSTACK_DISCOVERY_COST_EVIDENCE", "reviewed unit-test evidence"
        )
        assert provider_missing_routing_controls("marketstack") == []
        assert provider_missing_routing_controls("finra") == []
        monkeypatch.setattr(settings, "TIINGO_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "TIINGO_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "reviewed provider archive terms",
        )
        monkeypatch.setattr(settings, "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
            "reviewed provider archive terms",
        )
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
            "TIINGO_OPERATION_BYTE_BOUNDS",
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
        monkeypatch.setattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "calendar_month_est")
        monkeypatch.setattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "rolling")
        monkeypatch.setattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "symbol review")
        monkeypatch.setattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "hourly review")
        assert provider_missing_routing_controls("tiingo") == ["TIINGO_OPERATION_BYTE_BOUNDS"]
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
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "FINRA support case 123")
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_REVIEWED_SOURCE_URL",
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
        monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
        monkeypatch.setattr(settings, "FINRA_OTC_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "signed FINRA authority",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_automated_internal_display_perpetual_archive",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_PERSISTENT_STORAGE_REVIEWED_AT",
            datetime(2026, 10, 1, tzinfo=UTC),
        )
        assert provider_missing_routing_controls("finra_otc_directory") == []
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://api.finra.org/data/group/otcMarket/name/anotherDataset",
        )
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_REVIEWED_SOURCE_URL"
        ]
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "http://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_REVIEWED_SOURCE_URL",
            "http://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        assert provider_missing_routing_controls("finra_otc_directory") == [
            "FINRA_OTC_REVIEWED_SOURCE_URL"
        ]
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_SYMBOL_DIRECTORY_URL",
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
        monkeypatch.setattr(
            settings,
            "FINRA_OTC_REVIEWED_SOURCE_URL",
            "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
        )
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
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 120)
        monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "provider-confirmed scope")
        monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "rolling")
        monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "current provider/account review")
        monkeypatch.setattr(settings, "FRED_APPLICATION_USER_SCOPE", "owner_personal_only")
        monkeypatch.setattr(
            settings,
            "FRED_APPLICATION_USER_SCOPE_EVIDENCE",
            "single-owner private application",
        )
        monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE",
            "written permission for persisted data",
        )
        monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
            "written automated-use permission",
        )
        monkeypatch.setattr(
            settings,
            "FRED_SERIES_RIGHTS_EVIDENCE",
            {series_id: "written series terms" for series_id in FRED_MAPPED_SERIES_IDS},
        )
        assert provider_missing_routing_controls("fred") == []
        monkeypatch.setattr(settings, "FRED_APPLICATION_USER_SCOPE", "public")
        assert provider_missing_routing_controls("fred") == ["FRED_APPLICATION_USER_SCOPE"]
        monkeypatch.setattr(settings, "FRED_APPLICATION_USER_SCOPE", "owner_personal_only")
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", True)
        assert provider_missing_routing_controls("fred") == ["FRED_REVIEWED_REQUESTS_PER_MINUTE"]
        monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 120)
        fred_seed = provider_rate_limit_seed("fred")
        assert fred_seed["quota_scope"] == "api_key"
        assert fred_seed["quota_contract"]["unknown_dimensions"] == []
        assert fred_seed["quota_contract"]["dimensions"][0]["limit"] == 120
        assert fred_seed["quota_contract"]["dimensions"][0]["scope"] == "api_key"
        monkeypatch.setattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "calendar_day_utc")
        monkeypatch.setattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "operator review")
        assert provider_missing_routing_controls("alpha_vantage") == []
        alpha_seed = provider_rate_limit_seed("alpha_vantage")
        assert alpha_seed["quota_contract"]["reset"] == "calendar_day_utc"
        assert alpha_seed["quota_contract"]["unknown_dimensions"] == [
            "requests_per_second_reset_boundary",
            "requests_per_minute_reset_boundary",
        ]
        alpha_dimensions = {
            dimension["name"]: dimension for dimension in alpha_seed["quota_contract"]["dimensions"]
        }
        assert alpha_dimensions["requests_per_day"]["reset"] == "calendar_day_utc"
        assert alpha_dimensions["requests_per_second"]["reset"] == "provider_defined"
        assert alpha_dimensions["requests_per_minute"]["reset"] == "provider_defined"
        monkeypatch.setattr(settings, "FINNHUB_REVIEWED_MINUTE_RESET", "fixed_minute")
        monkeypatch.setattr(settings, "FINNHUB_REVIEWED_SECOND_RESET", "rolling")
        monkeypatch.setattr(settings, "FINNHUB_MINUTE_QUOTA_EVIDENCE", "minute review")
        monkeypatch.setattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "second review")
        assert provider_missing_routing_controls("finnhub") == []
        finnhub_seed = provider_rate_limit_seed("finnhub")
        assert finnhub_seed["quota_contract"]["reset"] == "per_dimension"
        assert finnhub_seed["quota_contract"]["unknown_dimensions"] == []
        assert {
            dimension["reset"] for dimension in finnhub_seed["quota_contract"]["dimensions"]
        } == {"fixed_minute", "rolling"}
        monkeypatch.setattr(settings, "COINBASE_MARKET_DATA_USE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "COINBASE_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment"
        )
        monkeypatch.setattr(
            settings,
            "COINBASE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "internal_ai_automated_persistent_nonredistributed",
        )
        monkeypatch.setattr(
            settings,
            "COINBASE_MARKET_DATA_USE_REVIEWED_AT",
            datetime.now(UTC) - timedelta(minutes=1),
        )
        assert coinbase_market_data_use_authority_missing() == []
        monkeypatch.setattr(
            settings,
            "COINBASE_MARKET_DATA_USE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        assert coinbase_market_data_use_authority_missing() == [
            "COINBASE_MARKET_DATA_USE_EXPIRES_AT"
        ]
        coingecko_authority = SimpleNamespace(
            COINGECKO_MARKET_DATA_USE_AUTHORIZED=True,
            COINGECKO_MARKET_DATA_USE_AUTHORITY_REFERENCE="written provider amendment",
            COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE=(
                "written_api_use_archive_audience_attribution_and_retention_after_termination"
            ),
            COINGECKO_MARKET_DATA_USE_REVIEWED_AT=datetime.now(UTC) - timedelta(minutes=1),
            COINGECKO_MARKET_DATA_USE_EXPIRES_AT=None,
        )
        assert coingecko_market_data_use_authority_missing(source=coingecko_authority) == []
        coingecko_authority.COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE = "personal_use_only"
        assert coingecko_market_data_use_authority_missing(source=coingecko_authority) == [
            "COINGECKO_MARKET_DATA_USE_AUTHORITY_SCOPE"
        ]
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", False)
        assert tiingo_persistent_storage_authority_missing() == []
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        assert tiingo_persistent_storage_authority_missing() == []
        monkeypatch.setattr(settings, "TIINGO_PERSISTENT_STORAGE_EXPIRES_AT", None)
        monkeypatch.setattr(settings, "FMP_PERSISTENT_STORAGE_AUTHORITY_SCOPE", "plan_only")
        assert fmp_persistent_storage_authority_missing() == []
        monkeypatch.setattr(
            settings,
            "FMP_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_perpetual_archive",
        )
        assert provider_missing_routing_controls("tiingo") == []
        assert provider_missing_routing_controls("fmp") == []
        assert provider_missing_routing_controls("eodhd") == [
            "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED",
            "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
        ]
        monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
            "reviewed provider display terms",
        )
        assert provider_missing_routing_controls("eodhd") == []
        assert provider_routing_control_settings("eodhd", "fetch_account_usage") == ()
        assert provider_missing_routing_controls("eodhd", "fetch_account_usage") == []
        # These assertions cover the documented default. A developer's local
        # reviewed key-specific override must not leak into the default case.
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "")
        monkeypatch.setattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "")
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
        default_eodhd_seed = provider_rate_limit_seed("eodhd")
        assert default_eodhd_seed["tokens_per_minute"] == 1000
        assert default_eodhd_seed["quota_contract"]["unknown_dimensions"] == []
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 20)
        assert provider_missing_routing_controls("eodhd") == [
            "EODHD_REVIEWED_MINUTE_RESET",
            "EODHD_MINUTE_QUOTA_EVIDENCE",
        ]
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "rolling")
        monkeypatch.setattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "account dashboard")
        assert provider_missing_routing_controls("eodhd") == []
        eodhd_seed = provider_rate_limit_seed("eodhd")
        eodhd_contract = eodhd_seed["quota_contract"]
        assert eodhd_contract["unknown_dimensions"] == []
        assert eodhd_contract["dimensions"][0]["limit"] == 20
        assert eodhd_contract["dimensions"][0]["reset"] == "rolling"
        assert eodhd_seed["tokens_per_minute"] == 20
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 1200)
        assert provider_missing_routing_controls("eodhd") == []
        eodhd_seed = provider_rate_limit_seed("eodhd")
        eodhd_contract = eodhd_seed["quota_contract"]
        assert eodhd_contract["dimensions"][0]["limit"] == 1200
        assert eodhd_contract["unknown_dimensions"] == []
        assert eodhd_seed["tokens_per_minute"] == 1200
        monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", -1)
        assert provider_missing_routing_controls("eodhd") == ["EODHD_REVIEWED_MINUTE_LIMIT"]
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
        monkeypatch.setattr(settings, "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_PROVIDER_RETENTION_TERMS_EVIDENCE",
            "reviewed provider retention terms",
        )
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
            "written approval",
        )
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
            "written_single_user_personal_nonprofessional_automated_perpetual_archive",
        )
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_PERSISTENT_STORAGE_REVIEWED_AT",
            datetime.now(UTC) - timedelta(minutes=1),
        )
        assert marketdata_app_persistent_storage_authority_missing() == []
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_PERSISTENT_STORAGE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        assert marketdata_app_persistent_storage_authority_missing() == []
        monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_EXPIRES_AT", None)
        assert provider_missing_routing_controls("marketdata_app") == []
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment"
        )
        monkeypatch.setattr(
            settings,
            "XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "internal_automated_persistent_nonredistributed",
        )
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", datetime.now(UTC))
        monkeypatch.setattr(settings, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "XSTOCKS_MARKET_DATA_USE_JURISDICTION_EVIDENCE", "deployment review"
        )
        assert provider_missing_routing_controls("xstocks") == []
        monkeypatch.setattr(settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_REFERENCE", "terms amendment"
        )
        monkeypatch.setattr(
            settings,
            "BYBIT_XSTOCKS_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "internal_automated_persistent_nonredistributed",
        )
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_REVIEWED_AT", datetime.now(UTC)
        )
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED", True
        )
        monkeypatch.setattr(
            settings,
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
            "deployment review",
        )
        monkeypatch.setattr(
            settings, "BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_AUTHORIZED", True
        )
        monkeypatch.setattr(
            settings,
            "BYBIT_XSTOCKS_MARKET_DATA_USE_USER_JURISDICTION_EVIDENCE",
            "verified user jurisdiction review",
        )
        assert bybit_xstocks_market_data_use_authority_missing() == []
        assert provider_missing_routing_controls("bybit_xstocks") == []
        monkeypatch.setattr(
            settings,
            "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT",
            datetime.now(UTC) - timedelta(seconds=1),
        )
        assert provider_missing_routing_controls("xstocks") == [
            "XSTOCKS_MARKET_DATA_USE_EXPIRES_AT"
        ]
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT"
        ]
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
            datetime(2030, 1, 1, tzinfo=UTC),
        )
        assert provider_missing_routing_controls("marketdata_app") == []
        monkeypatch.setattr(
            settings,
            "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
            datetime(2020, 1, 1, tzinfo=UTC),
        )
        assert provider_missing_routing_controls("marketdata_app") == []
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100)
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        ]
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
        monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", True)
        assert provider_missing_routing_controls("marketdata_app") == [
            "MARKETDATA_APP_REVIEWED_PLAN",
            "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT",
        ]

    def test_massive_optional_expiry_is_reported_when_invalid(self, monkeypatch):
        monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
        # This test isolates the optional expiry control. All stock operations,
        # including reference data, share Massive's documented Stocks bucket.
        monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_AUTHORIZED", True)
        monkeypatch.setattr(
            settings,
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
            "reviewed terms",
        )
        monkeypatch.setattr(
            settings,
            "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
            "written_automated_persistent_archive_and_audience",
        )
        monkeypatch.setattr(
            settings,
            "MASSIVE_MARKET_DATA_USE_REVIEWED_AT",
            datetime(2026, 9, 15, tzinfo=UTC),
        )
        monkeypatch.setattr(
            settings,
            "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
            datetime(2026, 9, 16, tzinfo=UTC),
        )
        assert provider_missing_routing_controls("massive", "get_instrument_profile") == [
            "MASSIVE_MARKET_DATA_USE_EXPIRES_AT",
        ]

    def test_yfinance_is_available_as_price_history_provider(self):
        provider = get_price_history_provider("yfinance")
        assert provider.name == "yfinance"

    def test_etf_holdings_internal_provider_is_registered_without_market_capabilities(self):
        provider = get_provider("etf_holdings_internal")
        assert provider.name == "etf_holdings_internal"
        assert list_provider_capabilities("etf_holdings_internal") == []

    def test_finra_owner_storage_approval_is_not_a_provider_routing_gate(self):
        now = datetime(2026, 10, 4, tzinfo=UTC)
        source = SimpleNamespace(
            FINRA_EQUITY_DATA_USE_AUTHORIZED=True,
            FINRA_EQUITY_DATA_USE_AUTHORITY_REFERENCE="https://developer.finra.org/specific-terms-equity-data",
            FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE=(
                "internal_noncommercial_persisted_nonredistributed"
            ),
            FINRA_EQUITY_DATA_USE_REVIEWED_AT=now - timedelta(days=1),
            FINRA_EQUITY_DATA_USE_EXPIRES_AT=now + timedelta(days=1),
        )
        assert finra_equity_data_use_authority_missing(now, source=source) == []

        source.FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE = "redistributed"
        assert finra_equity_data_use_authority_missing(now, source=source) == []

        source.FINRA_EQUITY_DATA_USE_AUTHORITY_SCOPE = (
            "internal_noncommercial_persisted_nonredistributed"
        )
        source.FINRA_EQUITY_DATA_USE_EXPIRES_AT = now
        assert finra_equity_data_use_authority_missing(now, source=source) == []

    def test_owner_terms_risk_setting_skips_terms_and_product_user_eligibility(self):
        owner_decision = SimpleNamespace(PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK=True)
        assert (
            provider_terms_exception_missing(
                "FMP_PROVIDER_ARCHIVE_TERMS_AUTHORIZED",
                "FMP_PROVIDER_ARCHIVE_TERMS_EVIDENCE",
                source=owner_decision,
            )
            == []
        )
        assert coinbase_market_data_use_authority_missing(source=owner_decision) == []
        assert coingecko_market_data_use_authority_missing(source=owner_decision) == []
        assert kraken_market_data_use_authority_missing(source=owner_decision) == []
        assert fred_data_use_controls_missing(source=owner_decision) == []
        assert fred_series_rights_missing(source=owner_decision) == []
        assert all(
            fred_series_rights_authorized(series_id, owner_decision)
            for series_id in FRED_MAPPED_SERIES_IDS
        )
        xstocks_missing = xstocks_market_data_use_authority_missing(source=owner_decision)
        assert xstocks_missing == []
        bybit_missing = bybit_xstocks_market_data_use_authority_missing(source=owner_decision)
        assert bybit_missing == [
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_AUTHORIZED",
            "BYBIT_XSTOCKS_MARKET_DATA_USE_EGRESS_JURISDICTION_EVIDENCE",
        ]

    def test_fmp_rolling_daily_safety_does_not_require_native_reset_override(self, monkeypatch):
        monkeypatch.setattr(settings, "FMP_REVIEWED_PLAN", "basic")
        monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", True)
        monkeypatch.setattr(
            settings,
            "FMP_OPERATION_BYTE_BOUNDS",
            {
                "fetch_ohlcv": 1_000_000,
                "fetch_latest_ohlcv": 1_000_000,
                "get_current_price": 100_000,
                "bulk_fetch": 1_000_000,
                "get_instrument_profile": 100_000,
                "fetch_market_events": 100_000,
                "discover_universe_page": 100_000,
                "fetch_account_usage": 65_536,
            },
        )
        monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "")
        monkeypatch.setattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "")
        monkeypatch.setattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "current plan and usage evidence")
        monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "current plan evidence")

        assert provider_missing_routing_controls("fmp") == []
        stock_list_missing = provider_missing_routing_controls("fmp", "discover_universe_page")
        assert "FMP_STOCK_LIST_ENTITLED" in stock_list_missing
        monkeypatch.setattr(settings, "FMP_STOCK_LIST_ENTITLED", True)
        assert "FMP_STOCK_LIST_ENTITLED" not in provider_missing_routing_controls(
            "fmp", "discover_universe_page"
        )
        contract = provider_rate_limit_seed("fmp")["quota_contract"]
        calls_per_day = next(
            item for item in contract["dimensions"] if item["name"] == "calls_per_day"
        )
        assert calls_per_day["reset"] == "provider_defined"
        assert calls_per_day["safety_reset"] == "rolling"
        assert contract["unknown_dimensions"] == []

        monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "unreviewed_reset")
        assert "FMP_REVIEWED_DAILY_RESET" in provider_missing_routing_controls("fmp")

    def test_fmp_invalid_selected_plan_is_provider_local_blocker(self, monkeypatch):
        monkeypatch.setattr(settings, "FMP_REVIEWED_PLAN", "unsupported_plan")
        missing = provider_missing_routing_controls("fmp")
        assert "FMP_REVIEWED_PLAN" in missing
