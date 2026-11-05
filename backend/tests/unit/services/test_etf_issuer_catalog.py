from __future__ import annotations

import base64
import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.provider_runtime import ProviderCapability
from app.services.etf_holdings_adapters import (
    ISHARES_PRODUCT_IDS_BY_SYMBOL,
    get_holdings_adapter,
    known_etf_route_metadata,
)
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    bind_etf_holdings_request_context,
    require_bound_etf_holdings_adapter,
)
from app.services.etf_holdings_refresh import acquire_etf_holdings_profile
from app.services.etf_issuer_catalog import (
    ISHARES_US_CATALOG_KEY,
    ISHARES_US_CATALOG_URL,
    CachedIssuerCatalog,
    IssuerCatalogError,
    _catalog_log_facts_are_trusted,
    _validated_cached_catalog_content,
    catalog_product_matches_canonical_fund,
    catalog_response_bytes,
    parse_ishares_us_product_catalog,
)


def _catalog_html(
    rows: str,
    *,
    result_count: str = "2 of 2 funds",
) -> str:
    return f"""<!doctype html>
    <html><body><p>{result_count}</p><table>
      <thead><tr><th>Ticker</th><th>Name</th><th>Asset Class</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></body></html>"""


def _row(ticker: str, name: str, product_id: str) -> str:
    href = f"/us/products/{product_id}/"
    return (
        f'<tr><td><a href="{href}">{ticker}</a></td>'
        f'<td><a href="{href}">{name}</a></td><td>Equity</td></tr>'
    )


def _row_with_paths(
    ticker: str,
    name: str,
    product_id: str,
    *,
    ticker_slug: str | None = None,
    name_slug: str | None = None,
) -> str:
    ticker_path = f"/us/products/{product_id}/{ticker_slug or ''}"
    name_path = f"/us/products/{product_id}/{name_slug or ''}"
    return (
        f'<tr><td><a href="{ticker_path}">{ticker}</a></td>'
        f'<td><a href="{name_path}">{name}</a></td><td>Equity</td></tr>'
    )


def _section_table(category: str, rows: str, result_count: str) -> str:
    return (
        f'<div class="category-title">{category}</div>'
        f'<div class="totals">Showing {result_count}</div>'
        f"<table><thead><tr><th>Ticker</th><th>Name</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


async def _async_value(value):
    return value


def test_ishares_catalog_parses_exact_products_without_symbol_seeds():
    html = _catalog_html(
        _row_with_paths(
            "IGV",
            "iShares Expanded Tech-Software Sector ETF",
            "239771",
            name_slug="ishares-expanded-tech-software-sector-etf",
        )
        + _row("IGM", "iShares Expanded Tech Sector ETF", "910002")
    )

    parsed = parse_ishares_us_product_catalog(html)

    assert parsed.complete is True
    assert parsed.reported_total == 2
    assert parsed.product_for("igv").as_json() == {
        "ticker": "IGV",
        "name": "iShares Expanded Tech-Software Sector ETF",
        "product_id": "239771",
        "product_url": (
            "https://www.ishares.com/us/products/239771/"
            "ishares-expanded-tech-software-sector-etf"
        ),
    }
    assert parsed.product_for("IGM").product_id == "910002"
    assert "IGV" not in ISHARES_PRODUCT_IDS_BY_SYMBOL
    assert "IGM" not in ISHARES_PRODUCT_IDS_BY_SYMBOL


@pytest.mark.parametrize("ticker", ["IGV", "IGM"])
def test_canonical_ishares_issuer_routes_unseeded_ticker_to_registered_catalog(ticker):
    issuer = SimpleNamespace(
        domain_key="ishares",
        status="active",
        provenance={"source": "verified issuer directory"},
    )

    route = known_etf_route_metadata(
        ticker,
        canonical_issuer=issuer,
        allow_catalog_route=True,
    )

    assert route["provider_aliases"] == {
        "holdings_adapter": "ishares",
        "holdings_source_provider": "ishares",
        "issuer_product_catalog_key": ISHARES_US_CATALOG_KEY,
        "issuer_catalog_discovery_hint": "trusted_canonical_issuer",
    }


@pytest.mark.parametrize(
    "issuer",
    [
        SimpleNamespace(domain_key="ishares", status="inactive", provenance={"source": "x"}),
        SimpleNamespace(domain_key="ishares", status="active", provenance={}),
        SimpleNamespace(domain_key="other", status="active", provenance={"source": "x"}),
        None,
    ],
)
def test_catalog_route_requires_trusted_canonical_issuer_record(issuer):
    assert known_etf_route_metadata("IGV", canonical_issuer=issuer, allow_catalog_route=True) == {}


def test_null_issuer_canonical_ishares_name_is_only_an_explicit_catalog_hint():
    assert (
        known_etf_route_metadata(
            "IGV", canonical_fund_name="iShares Expanded Tech-Software Sector ETF"
        )
        == {}
    )

    route = known_etf_route_metadata(
        "IGV",
        canonical_fund_name="iShares Expanded Tech-Software Sector ETF",
        allow_catalog_route=True,
    )

    assert route == {
        "issuer": None,
        "provider_aliases": {
            "holdings_adapter": "ishares",
            "holdings_source_provider": "ishares",
            "issuer_product_catalog_key": ISHARES_US_CATALOG_KEY,
            "issuer_catalog_discovery_hint": "canonical_iShares_fund_name",
        },
    }
    assert (
        known_etf_route_metadata(
            "IGV", canonical_fund_name="VanEck Oil Services ETF", allow_catalog_route=True
        )
        == {}
    )


def test_partial_catalog_can_prove_a_present_row_but_not_absence():
    parsed = parse_ishares_us_product_catalog(
        _catalog_html(
            _row("IGV", "iShares Expanded Tech-Software Sector ETF", "910001"),
            result_count="1 of 482 funds",
        )
    )

    assert parsed.complete is False
    assert parsed.product_for("IGV").product_id == "910001"
    assert parsed.product_for("IGM") is None


def test_482_of_482_label_does_not_make_a_partial_catalog_complete():
    parsed = parse_ishares_us_product_catalog(
        _catalog_html(
            _row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771"),
            result_count="Showing 482 of 482 total funds",
        )
    )

    assert parsed.reported_total == 482
    assert parsed.complete is False
    assert parsed.product_for("IGV") is not None


@pytest.mark.parametrize(
    "rows",
    [
        _row("IGV", "iShares Expanded Tech ETF", "910001")
        + _row("IGV", "Conflicting iShares ETF", "910099"),
        (
            '<tr><td><a href="/us/products/910001/">IGV</a></td>'
            '<td><a href="/us/products/910002/">iShares Expanded Tech ETF</a></td>'
            "<td>Equity</td></tr>"
        ),
        (
            '<tr><td><a href="https://attacker.example/us/products/910001/">IGV</a></td>'
            '<td><a href="https://attacker.example/us/products/910001/">iShares ETF</a></td>'
            "<td>Equity</td></tr>"
        ),
        (
            '<tr><td><a href="/us/products/not-numeric/">IGV</a></td>'
            '<td><a href="/us/products/not-numeric/">iShares ETF</a></td>'
            "<td>Equity</td></tr>"
        ),
        (
            '<tr><td><a href="/us/products/910001/">IGV</a></td>'
            "<td>iShares Expanded Tech ETF</td><td>Equity</td></tr>"
        ),
        _row("IGV", "iShares Expanded Tech ETF", "910001")
        + _row("IGM", "iShares Expanded Tech ETF", "910001"),
    ],
)
def test_ishares_catalog_rejects_ambiguous_or_untrusted_identity(rows):
    with pytest.raises(IssuerCatalogError):
        parse_ishares_us_product_catalog(_catalog_html(rows))


def test_catalog_accepts_numeric_and_official_slug_links_but_rejects_conflicting_slugs():
    actual = parse_ishares_us_product_catalog(
        _catalog_html(
            _row_with_paths(
                "IGV",
                "iShares Expanded Tech-Software Sector ETF",
                "239771",
                name_slug="ishares-expanded-tech-software-sector-etf",
            )
        )
    )
    assert actual.product_for("IGV").product_url.endswith(
        "/239771/ishares-expanded-tech-software-sector-etf"
    )

    numeric_only = parse_ishares_us_product_catalog(
        _catalog_html(_row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771"))
    )
    assert numeric_only.product_for("IGV").product_url.endswith("/239771/")

    encoded_space = parse_ishares_us_product_catalog(
        _catalog_html(
            _row_with_paths(
                "IGLB",
                "iShares 10 Year Investment Grade Corporate Bond ETF",
                "239423",
                name_slug="ishares-10%20-year-investment-grade-corporate-bond-etf",
            )
        )
    )
    assert encoded_space.product_for("IGLB").product_id == "239423"

    conflicting_slugs = _row_with_paths(
        "IGV",
        "iShares Expanded Tech-Software Sector ETF",
        "239771",
        ticker_slug="wrong-product-name",
        name_slug="ishares-expanded-tech-software-sector-etf",
    )
    with pytest.raises(IssuerCatalogError, match="conflict"):
        parse_ishares_us_product_catalog(_catalog_html(conflicting_slugs))

    unsafe_encoded_path = _row_with_paths(
        "IGV",
        "iShares Expanded Tech ETF",
        "239771",
        name_slug="ishares-expanded%2Ftech-etf",
    )
    with pytest.raises(IssuerCatalogError):
        parse_ishares_us_product_catalog(_catalog_html(unsafe_encoded_path))


def test_catalog_selects_etf_table_and_ignores_separate_mutual_fund_table():
    html = (
        "<html><body>"
        + _section_table(
            "Mutual Funds",
            _row("MUTF", "iShares Example Mutual Fund", "910044"),
            "1 of 1 total funds",
        )
        + _section_table(
            "ETFs",
            _row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771")
            + _row("IGM", "iShares Expanded Tech Sector ETF", "910002"),
            "Showing 2 of 2 total funds",
        )
        + "</body></html>"
    )

    parsed = parse_ishares_us_product_catalog(html)

    assert parsed.complete is True
    assert parsed.reported_total == 2
    assert {product.ticker for product in parsed.entries} == {"IGV", "IGM"}
    assert parsed.product_for("MUTF") is None


def test_catalog_rejects_unclassified_product_table_when_sections_are_present():
    html = (
        "<html><body>"
        + _section_table(
            "ETFs",
            _row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771"),
            "1 of 1 total funds",
        )
        + _catalog_html(_row("IGM", "iShares Expanded Tech Sector ETF", "910002"))
        + "</body></html>"
    )

    with pytest.raises(IssuerCatalogError, match="unclassified"):
        parse_ishares_us_product_catalog(html)


def test_catalog_merges_only_identity_consistent_split_product_tables():
    html = (
        "<html><body>"
        + _catalog_html(
            _row("IGV", "iShares Expanded Tech ETF", "910001"), result_count="2 of 2 funds"
        )
        + _catalog_html(
            _row("IGM", "iShares Expanded Tech Sector ETF", "910002"), result_count="2 of 2 funds"
        )
        + "</body></html>"
    )

    parsed = parse_ishares_us_product_catalog(html)

    assert parsed.complete is True
    assert parsed.reported_total == 2
    assert {product.ticker for product in parsed.entries} == {"IGV", "IGM"}


def test_catalog_rejects_conflicting_identity_across_same_scope_tables():
    html = (
        "<html><body>"
        + _catalog_html(
            _row("IGV", "iShares Expanded Tech ETF", "910001"), result_count="2 of 2 funds"
        )
        + _catalog_html(
            _row("IGV", "iShares Conflicting ETF", "910099"), result_count="2 of 2 funds"
        )
        + "</body></html>"
    )

    with pytest.raises(IssuerCatalogError, match="conflict"):
        parse_ishares_us_product_catalog(html)


def test_catalog_rejects_unlabeled_ambiguous_tables_without_authoritative_totals():
    html = (
        "<html><body>"
        + _catalog_html(_row("IGV", "iShares Expanded Tech ETF", "910001"), result_count="")
        + _catalog_html(_row("IGM", "iShares Expanded Tech Sector ETF", "910002"), result_count="")
        + "</body></html>"
    )

    with pytest.raises(IssuerCatalogError, match="ambiguous"):
        parse_ishares_us_product_catalog(html)


@pytest.mark.parametrize(
    ("catalog_name", "canonical_name", "expected"),
    [
        (
            "iShares Expanded Tech-Software Sector ETF",
            "iShares Expanded Tech-Software Sector ETF",
            True,
        ),
        (
            "iShares Expanded Tech-Software Sector ETF",
            "IGV: iShares Expanded Tech Software Sector ETF",
            True,
        ),
        (
            "iShares Expanded Tech-Software Sector ETF",
            "iShares Expanded Tech ETF",
            False,
        ),
        (
            "iShares Expanded Tech-Software Sector ETF",
            "Vanguard Expanded Tech-Software Sector ETF",
            False,
        ),
    ],
)
def test_catalog_product_must_match_exact_canonical_ticker_and_name(
    catalog_name, canonical_name, expected
):
    product = parse_ishares_us_product_catalog(
        _catalog_html(_row("IGV", catalog_name, "239771"))
    ).product_for("IGV")
    assert (
        catalog_product_matches_canonical_fund(
            product=product,
            ticker="IGV",
            canonical_name=canonical_name,
        )
        is expected
    )


def test_catalog_product_rejects_wrong_selected_ticker_even_when_name_matches():
    product = parse_ishares_us_product_catalog(
        _catalog_html(_row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771"))
    ).product_for("IGV")
    assert not catalog_product_matches_canonical_fund(
        product=product,
        ticker="IGM",
        canonical_name="iShares Expanded Tech-Software Sector ETF",
    )


def test_real_ishares_catalog_total_label_is_parsed_but_does_not_fake_completeness():
    parsed = parse_ishares_us_product_catalog(
        _catalog_html(
            _row("IGV", "iShares Expanded Tech-Software Sector ETF", "239771"),
            result_count="Showing 482 of 482 total funds",
        )
    )
    assert parsed.reported_total == 482
    assert parsed.complete is False


def test_reported_total_alone_does_not_mark_partial_catalog_complete():
    parsed = parse_ishares_us_product_catalog(
        _catalog_html(
            _row("IGV", "iShares Expanded Tech ETF", "910001"),
            result_count="482 of 482 funds",
        )
    )

    assert parsed.reported_total == 482
    assert parsed.complete is False


def test_catalog_response_hash_uses_exact_wire_bytes_and_requires_same_origin():
    body = _catalog_html(_row("IGV", "iShares Expanded Tech ETF", "910001")).encode()

    class Response:
        content = body
        encoding = "utf-8"
        headers = {"content-type": "text/html; charset=utf-8"}
        url = ISHARES_US_CATALOG_URL

    exact_body, encoding, final_url = catalog_response_bytes(Response())

    assert exact_body == body
    assert hashlib.sha256(exact_body).hexdigest() == hashlib.sha256(body).hexdigest()
    assert encoding == "utf-8"
    assert final_url == ISHARES_US_CATALOG_URL

    Response.url = "https://evil.example/us/products/etf-investments"
    with pytest.raises(IssuerCatalogError, match="redirected outside"):
        catalog_response_bytes(Response())


def test_cache_content_validation_binds_metadata_to_exact_stored_bytes():
    html = _catalog_html(_row("IGV", "iShares Expanded Tech ETF", "910001"))
    body = html.encode("utf-8")
    parsed = parse_ishares_us_product_catalog(html)
    digest = hashlib.sha256(body).hexdigest()
    now = datetime(2026, 11, 3, tzinfo=UTC)
    record = SimpleNamespace(
        provider_name="ishares",
        catalog_key=ISHARES_US_CATALOG_KEY,
        source_url=ISHARES_US_CATALOG_URL,
        final_url=ISHARES_US_CATALOG_URL,
        requested_symbol="IGV",
        response_bytes=len(body),
        content_sha256=digest,
        fetched_at=now,
        raw_body_base64=base64.b64encode(body).decode("ascii"),
        response_encoding="utf-8",
        parsed_entries=[entry.as_json() for entry in parsed.entries],
        reported_total=parsed.reported_total,
        catalog_complete=parsed.complete,
    )

    validated = _validated_cached_catalog_content(record, now=now)
    assert validated is not None
    assert validated[0] == body
    assert validated[1] == parsed

    for field, value in (
        ("provider_name", "unreviewed-provider"),
        ("source_url", "https://attacker.example/catalog"),
        ("requested_symbol", "lowercase igv"),
        ("raw_body_base64", base64.b64encode(body + b" ").decode("ascii")),
        ("parsed_entries", []),
    ):
        tampered = SimpleNamespace(**vars(record))
        setattr(tampered, field, value)
        assert _validated_cached_catalog_content(tampered, now=now) is None, field

    stale = SimpleNamespace(**vars(record))
    stale.fetched_at = now - timedelta(hours=25)
    assert _validated_cached_catalog_content(stale, now=now) is None

    future = SimpleNamespace(**vars(record))
    future.fetched_at = now + timedelta(seconds=1)
    assert _validated_cached_catalog_content(future, now=now) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"data_source_id": 99},
        {"capability": "market_data"},
        {"operation": "fetch_etf_holdings_for_date"},
        {"instrument_id": None},
        {"provider_symbol": "IGM"},
        {"success": False},
        {"completed_at": None},
    ],
)
def test_catalog_cache_lineage_rejects_unrelated_or_incomplete_provider_logs(changes):
    row = SimpleNamespace(
        id=17,
        data_source_id=4,
        capability=ProviderCapability.ETF_HOLDINGS,
        operation="fetch_etf_holdings_latest",
        instrument_id=81,
        provider_symbol="IGV",
        success=True,
        completed_at=datetime(2026, 11, 3, tzinfo=UTC),
    )
    retrieved_at = row.completed_at
    for field, value in changes.items():
        setattr(row, field, value)

    assert not _catalog_log_facts_are_trusted(
        logs=[row],
        request_log_ids=[17],
        request_urls=[ISHARES_US_CATALOG_URL],
        source_id=4,
        requested_symbol="IGV",
        retrieved_at=retrieved_at,
    )


def test_catalog_cache_lineage_accepts_exact_admitted_redirect_chain():
    completed = datetime(2026, 11, 3, tzinfo=UTC)
    logs = [
        SimpleNamespace(
            id=17,
            data_source_id=4,
            capability=ProviderCapability.ETF_HOLDINGS,
            operation="fetch_etf_holdings_latest",
            instrument_id=81,
            provider_symbol="IGV",
            success=True,
            completed_at=completed,
        ),
        SimpleNamespace(
            id=18,
            data_source_id=4,
            capability=ProviderCapability.ETF_HOLDINGS,
            operation="fetch_etf_holdings_latest",
            instrument_id=81,
            provider_symbol="IGV",
            success=True,
            completed_at=completed,
        ),
    ]
    request_urls = [
        ISHARES_US_CATALOG_URL,
        "https://www.ishares.com/us/products/etf-investments?locale=en_US",
    ]

    assert _catalog_log_facts_are_trusted(
        logs=logs,
        request_log_ids=[17, 18],
        request_urls=request_urls,
        source_id=4,
        requested_symbol="IGV",
        retrieved_at=completed,
    )
    assert not _catalog_log_facts_are_trusted(
        logs=logs,
        request_log_ids=[17, 18],
        request_urls=[request_urls[0], "https://attacker.example/catalog"],
        source_id=4,
        requested_symbol="IGV",
        retrieved_at=completed,
    )
    assert not _catalog_log_facts_are_trusted(
        logs=logs,
        request_log_ids=[17, 18],
        request_urls=request_urls,
        source_id=4,
        requested_symbol="IGV",
        retrieved_at=completed + timedelta(seconds=1),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("canonical_name", "stale_product_id", "expected_request_count"),
    [
        ("iShares Expanded Tech-Software Sector ETF", None, 2),
        ("iShares Expanded Tech ETF", "999999", 1),
    ],
)
async def test_ishares_selected_fetch_resolves_catalog_only_for_exact_canonical_fund(
    monkeypatch, canonical_name, stale_product_id, expected_request_count
):
    catalog_html = _catalog_html(
        _row("IGV", "iShares Expanded Tech-Software Sector ETF", "910001")
        + _row("IGM", "iShares Expanded Tech Sector ETF", "910002")
    )
    holdings_payload = {
        "componentsByNameMap": {
            "holdings": {
                "containersByNameMap": {
                    "all": {
                        "dataPointsByNameMap": {
                            "ticker": {"value": ["AAPL"]},
                            "issueName": {"value": ["Apple Inc."]},
                            "holdingPercent": {"value": [5.5]},
                            "unitsHeld": {"value": [100]},
                            "marketValue": {"value": [10000]},
                            "asOfDate": {"value": "20261030"},
                        }
                    }
                }
            }
        }
    }

    class Response:
        def __init__(self, *, text: str, url: str, payload: dict | None = None):
            self.text = text
            self.content = text.encode()
            self.encoding = "utf-8"
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.url = url
            self.status_code = 200
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    catalog_response = Response(text=catalog_html, url=ISHARES_US_CATALOG_URL)
    holdings_response = Response(
        text="{}",
        url="https://www.blackrock.com/varnish-api/fixture",
        payload=holdings_payload,
    )

    class BoundFakeClient:
        queue = [catalog_response, holdings_response]
        requested: list[tuple[str, dict]] = []
        binding = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            type(self).requested.append((url, kwargs))
            binding = type(self).binding
            request_id = len(binding.request_log_ids) + 1
            binding.request_log_ids.append(request_id)
            binding.request_urls_by_log_id[request_id] = url
            return type(self).queue.pop(0)

    async def no_cache(_db, *, ticker):
        assert ticker == "IGV"
        return None

    async def save_catalog(_db, **kwargs):
        assert kwargs["ticker"] == "IGV"
        assert kwargs["request_log_ids"] == [1]
        assert kwargs["request_urls"] == [ISHARES_US_CATALOG_URL]
        parsed = parse_ishares_us_product_catalog(catalog_html)
        return CachedIssuerCatalog(
            cache_id=44,
            catalog=parsed,
            content_sha256=hashlib.sha256(catalog_html.encode()).hexdigest(),
            retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
            request_log_ids=(1,),
            source_url=ISHARES_US_CATALOG_URL,
            final_url=ISHARES_US_CATALOG_URL,
        )

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", BoundFakeClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.load_cached_ishares_catalog", no_cache)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.store_ishares_catalog_response", save_catalog
    )
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None
    request_context = bind_etf_holdings_request_context(
        db=SimpleNamespace(),
        adapter=adapter,
        profile_id=31,
        instrument_id=81,
        provider_symbol="IGV",
        operation="fetch_etf_holdings_latest",
    )
    BoundFakeClient.queue = [catalog_response, holdings_response]
    BoundFakeClient.requested = []
    with request_context as binding:
        BoundFakeClient.binding = binding
        if expected_request_count == 2:
            result = await adapter.fetch_latest(
                symbol="IGV",
                identifiers={
                    "issuer_product_catalog_key": ISHARES_US_CATALOG_KEY,
                    "canonical_fund_name": canonical_name,
                    **({"issuer_product_id": stale_product_id} if stale_product_id else {}),
                },
            )
        else:
            with pytest.raises(ETFHoldingsRouteHeldError, match="does not exactly match"):
                await adapter.fetch_latest(
                    symbol="IGV",
                    identifiers={
                        "issuer_product_catalog_key": ISHARES_US_CATALOG_KEY,
                        "canonical_fund_name": canonical_name,
                        **({"issuer_product_id": stale_product_id} if stale_product_id else {}),
                    },
                )
            assert [url for url, _ in BoundFakeClient.requested] == [ISHARES_US_CATALOG_URL]
            assert binding.request_log_ids == [1]
            return

    assert result.rows[0].symbol == "AAPL"
    assert result.legal_metadata["issuer_product_id"] == "910001"
    assert result.legal_metadata["issuer_product_catalog"] == {
        "catalog_key": ISHARES_US_CATALOG_KEY,
        "catalog_source_url": ISHARES_US_CATALOG_URL,
        "catalog_final_url": ISHARES_US_CATALOG_URL,
        "catalog_content_sha256": hashlib.sha256(catalog_html.encode()).hexdigest(),
        "catalog_retrieved_at": "2026-11-03T00:00:00+00:00",
        "catalog_request_log_ids": [1],
        "catalog_cache_id": 44,
        "catalog_cache_hit": False,
        "ticker": "IGV",
        "name": "iShares Expanded Tech-Software Sector ETF",
        "issuer_product_id": "910001",
        "product_url": ("https://www.ishares.com/us/products/910001/"),
        "catalog_complete": True,
        "catalog_reported_total": 2,
    }
    assert [url for url, _ in BoundFakeClient.requested] == [
        ISHARES_US_CATALOG_URL,
        result.source_url,
    ]
    assert "portfolioId=910001" in result.source_url
    assert binding.operation == "fetch_etf_holdings_latest"
    assert binding.request_log_ids == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("canonical_name", "expected_outcome", "expected_urls"),
    [
        (
            "iShares Expanded Tech-Software Sector ETF",
            "acquired",
            [ISHARES_US_CATALOG_URL, "portfolioId=239771"],
        ),
        (
            "iShares Expanded Tech ETF",
            "held",
            [ISHARES_US_CATALOG_URL],
        ),
    ],
)
async def test_selected_acquire_from_null_issuer_igv_requires_official_catalog_identity(
    monkeypatch, canonical_name, expected_outcome, expected_urls
):
    """Exercise acquire route preparation and catalog identity with no static/profile seed."""

    instrument = SimpleNamespace(
        id=82,
        symbol="IGV",
        name=canonical_name,
        is_active=True,
        is_synthetic=False,
        identity_status="resolved",
        issuer_id=None,
        issuer=None,
        instrument_type=SimpleNamespace(name="ETF", asset_class=SimpleNamespace(name="Equity")),
    )
    profile = SimpleNamespace(
        id=992,
        instrument_id=instrument.id,
        instrument=instrument,
        issuer=None,
        sponsor=None,
        fund_family=None,
        product_url=None,
        sec_cik=None,
        sec_series_id=None,
        sec_class_id=None,
        provider_aliases={},
        legal_metadata={},
        adapter_key=None,
        adapter_status="unresolved",
        adapter_confidence=0,
    )

    class DB:
        def __init__(self):
            self.commit_calls = 0
            self.flush_calls = 0
            self.catalog_cache = None
            self.catalog_logs: list[Any] = []
            self.catalog_source = SimpleNamespace(id=61, name="ishares")

        async def flush(self, *_args, **_kwargs):
            self.flush_calls += 1

        async def commit(self):
            self.commit_calls += 1

        async def scalar(self, _statement):
            return self.catalog_source

        async def get(self, _model, object_id):
            assert object_id == 51
            return self.catalog_cache

        async def scalars(self, _statement):
            class Rows:
                def __init__(self, rows):
                    self.rows = rows

                def all(self):
                    return self.rows

            return Rows(self.catalog_logs)

        async def execute(self, *_args, **_kwargs):
            raise AssertionError("unexpected failed-acquire persistence in this success fixture")

        def begin_nested(self):
            class Savepoint:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *_args):
                    return False

            return Savepoint()

    db = DB()
    profile_lookups = 0
    requested_urls: list[str] = []
    response_queue: list[Any] = []

    # Keep this small controlled success fixture internally complete. The
    # separate 482/482 regression proves a truncated body cannot borrow the
    # issuer's reported total to claim catalog completeness.
    catalog_rows = _row_with_paths(
        "IGV",
        "iShares Expanded Tech-Software Sector ETF",
        "239771",
        name_slug="ishares-expanded-tech-software-sector-etf",
    ) + _row(
        "XLK",
        "iShares U.S. Technology ETF",
        "239726",
    )
    catalog_html = _catalog_html(
        catalog_rows,
        result_count="2 of 2 funds",
    )
    holding_payload = {
        # The retained authentic IGV holdings response carries both fields;
        # product identity must match the official catalog, not just its name.
        "productId": 239771,
        "fundName": "iShares Expanded Tech-Software Sector ETF",
        "componentsByNameMap": {
            "holdings": {
                "containersByNameMap": {
                    "all": {
                        "dataPointsByNameMap": {
                            "ticker": {"value": ["AAPL"]},
                            "issueName": {"value": ["Apple Inc."]},
                            "holdingPercent": {"value": [5.5]},
                            "unitsHeld": {"value": [100]},
                            "marketValue": {"value": [10000]},
                            "asOfDate": {"value": "20261030"},
                        }
                    }
                }
            }
        },
    }

    class Response:
        def __init__(self, *, text: str, url: str, payload: dict | None = None):
            self.text = text
            self.content = text.encode()
            self.encoding = "utf-8"
            self.headers = {
                "content-type": "text/html; charset=utf-8"
                if "ishares.com" in url
                else "application/json"
            }
            self.url = url
            self.status_code = 200
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    response_queue.extend(
        [
            Response(text=catalog_html, url=ISHARES_US_CATALOG_URL),
            Response(
                text=json.dumps(holding_payload),
                url="https://www.blackrock.com/varnish-api/fixture",
                payload=holding_payload,
            ),
        ]
    )

    class BoundClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            requested_urls.append(url)
            binding = require_bound_etf_holdings_adapter(get_holdings_adapter("ishares"))
            request_id = len(binding.request_log_ids) + 1
            binding.request_log_ids.append(request_id)
            binding.request_urls_by_log_id[request_id] = url
            if url == ISHARES_US_CATALOG_URL:
                self_request_log = SimpleNamespace(
                    id=request_id,
                    data_source_id=61,
                    capability=ProviderCapability.ETF_HOLDINGS,
                    operation="fetch_etf_holdings_latest",
                    instrument_id=instrument.id,
                    provider_symbol="IGV",
                    success=True,
                    completed_at=None,
                )
                db.catalog_logs.append(self_request_log)
            return response_queue.pop(0)

    async def no_cache(_db, *, ticker):
        assert ticker == "IGV"
        return None

    async def store_catalog(_db, **kwargs):
        parsed = parse_ishares_us_product_catalog(catalog_html)
        assert kwargs["ticker"] == "IGV"
        assert kwargs["request_urls"] == [ISHARES_US_CATALOG_URL]
        retrieved_at = datetime.now(UTC)
        db.catalog_cache = SimpleNamespace(
            id=51,
            provider_name="ishares",
            catalog_key=ISHARES_US_CATALOG_KEY,
            data_source_id=61,
            source_url=ISHARES_US_CATALOG_URL,
            final_url=ISHARES_US_CATALOG_URL,
            content_sha256=hashlib.sha256(catalog_html.encode()).hexdigest(),
            response_bytes=len(catalog_html.encode()),
            response_encoding="utf-8",
            raw_body_base64=base64.b64encode(catalog_html.encode()).decode("ascii"),
            parsed_entries=[entry.as_json() for entry in parsed.entries],
            reported_total=parsed.reported_total,
            catalog_complete=parsed.complete,
            requested_symbol="IGV",
            provider_request_log_ids=tuple(kwargs["request_log_ids"]),
            request_urls=tuple(kwargs["request_urls"]),
            fetched_at=retrieved_at,
        )
        db.catalog_logs[0].completed_at = retrieved_at
        return CachedIssuerCatalog(
            cache_id=51,
            catalog=parsed,
            content_sha256=hashlib.sha256(catalog_html.encode()).hexdigest(),
            retrieved_at=retrieved_at,
            request_log_ids=(kwargs["request_log_ids"][0],),
            source_url=ISHARES_US_CATALOG_URL,
            final_url=ISHARES_US_CATALOG_URL,
        )

    @contextmanager
    def selected_source_scope(**scope):
        assert scope == {
            "request_id": "b88a8eb2-238c-4e51-88ba-4d64638fbfb8",
            "instrument_id": instrument.id,
            "symbol": "IGV",
            "issuer_provider_name": "ishares",
        }
        yield

    async def profile_lookup(_db, _instrument_id):
        nonlocal profile_lookups
        profile_lookups += 1
        return None if profile_lookups == 1 else profile

    async def ingest(_db, **kwargs):
        assert kwargs["etf_instrument"] is instrument
        assert [row.symbol for row in kwargs["rows"]] == ["AAPL"]
        assert kwargs["source_identifier"] == "IGV"
        return SimpleNamespace(id=605)

    async def record_success(*_args, **_kwargs):
        return None

    async def no_rejected_artifact(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._resolve_canonical_fund_instrument",
        lambda *_args: _async_value(instrument),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_etf_profile_for_instrument", profile_lookup
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.ensure_etf_profile", lambda *_args: _async_value(profile)
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.get_latest_snapshot",
        lambda *_args, **_kwargs: _async_value(None),
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._explicit_etf_acquisition_binder",
        lambda: selected_source_scope,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._ensure_schema_fingerprint_is_stable",
        lambda *_args, **_kwargs: _async_value(None),
    )
    monkeypatch.setattr("app.services.etf_holdings_refresh.ingest_holdings_snapshot", ingest)
    monkeypatch.setattr("app.services.etf_holdings_refresh._record_success", record_success)
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._retain_rejected_fetch_artifact",
        no_rejected_artifact,
    )
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", BoundClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.load_cached_ishares_catalog", no_cache)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.store_ishares_catalog_response", store_catalog
    )

    result = await acquire_etf_holdings_profile(
        db,
        symbol="IGV",
        instrument_id=instrument.id,
        request_id="b88a8eb2-238c-4e51-88ba-4d64638fbfb8",
        refresh=True,
    )

    assert result is not None
    assert result.outcome == expected_outcome
    assert profile.adapter_key == "ishares"
    assert profile.issuer is None
    assert profile.provider_aliases["issuer_product_catalog_key"] == ISHARES_US_CATALOG_KEY
    if expected_outcome == "acquired":
        assert requested_urls[0] == expected_urls[0]
        assert len(requested_urls) == 2
        assert expected_urls[1] in requested_urls[1]
        assert result.snapshot_id == 605
        assert result.provider_request_log_ids == [1, 2]
    else:
        assert requested_urls == expected_urls
        assert result.refresh_succeeded is False
        assert result.provider_request_log_ids == [1]
