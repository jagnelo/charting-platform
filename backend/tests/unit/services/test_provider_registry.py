from app.providers.registry import (
    get_default_options_provider,
    get_identifier_provider,
    get_option_chain_provider,
    get_price_history_provider,
    list_provider_capabilities,
)


class TestProviderRegistry:
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
