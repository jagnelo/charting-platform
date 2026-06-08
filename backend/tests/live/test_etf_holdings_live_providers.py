import os

import pytest

from app.services.etf_holdings_adapters import (
    ISSUER_ADAPTER_CONFIGS,
    get_holdings_adapter,
)

LIVE_BACKED_ISSUER_ADAPTERS = {
    "ark",
    "global_x",
    "ishares",
    "spdr",
    "vaneck",
}
EXPLICIT_CANDIDATE_ROUTE_GAPS = {
    "direxion",
    "fidelity",
    "franklin",
    "invesco",
    "jpmorgan",
    "proshares",
    "schwab",
    "vanguard",
    "wisdomtree",
}

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_ETF_HOLDINGS_TESTS") != "1",
        reason="Set RUN_LIVE_ETF_HOLDINGS_TESTS=1 to run live issuer holdings checks.",
    ),
]


def test_live_provider_matrix_covers_every_registered_issuer_adapter():
    registered = set(ISSUER_ADAPTER_CONFIGS)

    assert LIVE_BACKED_ISSUER_ADAPTERS <= registered
    assert EXPLICIT_CANDIDATE_ROUTE_GAPS <= registered
    assert registered == LIVE_BACKED_ISSUER_ADAPTERS | EXPLICIT_CANDIDATE_ROUTE_GAPS
    for adapter_key, config in ISSUER_ADAPTER_CONFIGS.items():
        assert config.live_tested_default_route is (adapter_key in LIVE_BACKED_ISSUER_ADAPTERS)


def _assert_live_holdings_result(result, *, adapter_key: str, min_rows: int = 10):
    assert result.source_url
    assert result.rows, f"{adapter_key} returned no parseable holdings rows"
    assert len(result.rows) >= min_rows
    assert result.raw_text
    assert result.legal_metadata
    assert result.legal_metadata["adapter_key"] == adapter_key
    assert any(row.symbol or row.name or row.cusip or row.isin for row in result.rows)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol", "issuer_product_id", "identifiers", "min_rows"),
    [
        (
            "spdr",
            "SPY",
            None,
            {},
            100,
        ),
        (
            "ishares",
            "IVV",
            "239726",
            {},
            5,
        ),
        (
            "ishares",
            "IWM",
            None,
            {},
            100,
        ),
        (
            "vaneck",
            "SMH",
            None,
            {"product_slug": "semiconductor-etf-smh"},
            20,
        ),
        (
            "ark",
            "ARKK",
            None,
            {},
            20,
        ),
    ],
)
async def test_live_issuer_direct_holdings_routes_return_parseable_rows(
    adapter_key,
    symbol,
    issuer_product_id,
    identifiers,
    min_rows,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    result = await adapter.fetch_latest(
        symbol=symbol,
        issuer_product_id=issuer_product_id,
        identifiers=identifiers,
    )

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=min_rows)


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol", "identifiers"),
    [
        (
            "global_x",
            "QYLD",
            {},
        ),
    ],
)
async def test_live_issuer_product_pages_discover_parseable_holdings_files(
    adapter_key,
    symbol,
    identifiers,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    result = await adapter.fetch_latest(symbol=symbol, identifiers=identifiers)

    _assert_live_holdings_result(result, adapter_key=adapter_key, min_rows=5)
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.parametrize(
    ("adapter_key", "symbol"),
    [
        ("direxion", "SPXL"),
        ("fidelity", "FBCG"),
        ("franklin", "FLQL"),
        ("invesco", "QQQ"),
        ("jpmorgan", "JEPI"),
        ("proshares", "TQQQ"),
        ("schwab", "SCHD"),
        ("vanguard", "VOO"),
        ("wisdomtree", "DXJ"),
    ],
)
async def test_live_candidate_route_gap_adapters_do_not_claim_default_support(
    adapter_key,
    symbol,
):
    adapter = get_holdings_adapter(adapter_key)
    assert adapter is not None

    probe = adapter.probe(symbol=symbol, name="", identifiers={})

    assert adapter_key in EXPLICIT_CANDIDATE_ROUTE_GAPS
    assert not ISSUER_ADAPTER_CONFIGS[adapter_key].live_tested_default_route
    assert probe.status == "needs_provider_implementation"
