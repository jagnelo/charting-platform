from app.services.e2e_seed import (
    _E2E_BENCHMARK_PROXY_NAMES,
    _E2E_HOLDINGS,
    _E2E_INDUSTRIES,
    _E2E_MARKET_NAMES,
)
from app.services.top_down_taxonomy import (
    BENCHMARK_FAMILY_REGISTRY,
    benchmark_family_proxy_symbols,
)


def test_controlled_top_down_fixture_covers_all_select_sector_etfs():
    expected_sectors = {
        "XLB",
        "XLC",
        "XLE",
        "XLF",
        "XLI",
        "XLK",
        "XLP",
        "XLRE",
        "XLU",
        "XLV",
        "XLY",
    }
    assert expected_sectors <= set(_E2E_HOLDINGS)
    assert all(holdings for holdings in _E2E_HOLDINGS.values())

    fixture_symbols = set(_E2E_MARKET_NAMES)
    holding_symbols = {symbol for holdings in _E2E_HOLDINGS.values() for symbol in holdings}
    assert holding_symbols <= fixture_symbols
    assert holding_symbols <= set(_E2E_INDUSTRIES)


def test_controlled_top_down_fixture_industry_labels_are_deterministic():
    assert _E2E_INDUSTRIES["NVDA"] == "Semiconductors"
    assert _E2E_INDUSTRIES["XOM"] == "Integrated Oil & Gas"
    assert _E2E_INDUSTRIES["JPM"] == "Diversified Banks"
    assert len(_E2E_INDUSTRIES) == len(set(_E2E_INDUSTRIES))


def test_controlled_fixture_covers_every_benchmark_family_leg():
    """The browser fixture must exercise the same universal source matrix as production."""

    configured_symbols = set(benchmark_family_proxy_symbols())
    assert configured_symbols <= set(_E2E_BENCHMARK_PROXY_NAMES)

    for family in BENCHMARK_FAMILY_REGISTRY:
        for role in ("cap_weight", "equal_weight", "value", "growth"):
            mapping = family.get(role) or {}
            symbol = mapping.get("symbol")
            if symbol:
                assert symbol in _E2E_HOLDINGS, (family["logical_key"], role, symbol)
                assert _E2E_HOLDINGS[symbol]
        derived_equal = family.get("derived_equal_weight") or {}
        cap_symbol = (family.get("cap_weight") or {}).get("symbol")
        if derived_equal.get("allowed"):
            assert cap_symbol in _E2E_HOLDINGS
