import os

import pytest

from app.services.etf_holdings_adapters import get_holdings_adapter

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_ETF_HOLDINGS_TESTS") != "1",
        reason="Set RUN_LIVE_ETF_HOLDINGS_TESTS=1 to run live issuer holdings checks.",
    ),
]


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
            "vaneck",
            "SMH",
            None,
            {"product_slug": "semiconductor-etf-smh"},
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
