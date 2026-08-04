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
    list_provider_capabilities,
)


def test_backend_env_example_keeps_yfinance_out_of_new_workstation_chains():
    import json
    from pathlib import Path

    lines = Path(__file__).parents[3].joinpath(".env.example").read_text().splitlines()
    seed_line = next(line for line in lines if line.startswith("PROVIDER_CHAIN_SEEDS="))
    seeds = json.loads(seed_line.split("=", 1)[1])
    assert seeds["option_chain"] == ["yfinance"]
    assert all(
        "yfinance" not in providers
        for capability, providers in seeds.items()
        if capability != "option_chain"
    )


class TestProviderRegistry:
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

    def test_default_options_provider_matches_yfinance(self):
        provider = get_default_options_provider()
        assert provider.name == "yfinance"

    def test_yfinance_is_available_as_price_history_provider(self):
        provider = get_price_history_provider("yfinance")
        assert provider.name == "yfinance"

    def test_etf_holdings_internal_provider_is_registered_without_market_capabilities(self):
        provider = get_provider("etf_holdings_internal")
        assert provider.name == "etf_holdings_internal"
        assert list_provider_capabilities("etf_holdings_internal") == []
