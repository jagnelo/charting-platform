from app.services.e2e_seed import _E2E_HOLDINGS, _E2E_INDUSTRIES, _E2E_MARKET_NAMES


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
