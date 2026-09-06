from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.workstation import MarketGroup, MarketGroupMember
from app.services.etf_holdings_adapters import get_holdings_adapter, known_etf_route_metadata
from app.services.top_down_taxonomy import (
    _BENCHMARKS,
    _INDUSTRY_PROXY_CANDIDATES,
    _SECTORS,
    BENCHMARK_FAMILY_REGISTRY,
    benchmark_family_proxy_symbols,
    benchmark_family_registry,
    canonical_industry_label,
    industry_proxy_candidates,
    seed_top_down_taxonomy,
    source_classification_for_as_of,
    source_classification_from_profile_snapshot,
)


def test_benchmark_family_registry_is_complete_and_no_missing_mapping_is_fabricated():
    families = benchmark_family_registry()
    assert [family["logical_key"] for family in families] == [
        "sp500",
        "sp400",
        "sp600",
        "sp1500",
        "russell1000",
        "russell2000",
        "russell3000",
        "nasdaq100",
    ]
    assert {family["official_index_symbol"] for family in families} == {
        "SPX",
        "MID",
        "SML",
        "SPSUPX",
        "RUI",
        "RTY",
        "RUA",
        "NDX",
    }
    nasdaq = next(family for family in families if family["logical_key"] == "nasdaq100")
    assert nasdaq["cap_weight"]["symbol"] == "QQQ"
    assert nasdaq["equal_weight"]["symbol"] == "QQQE"
    assert nasdaq["equal_weight"]["verification_state"] == "proxy_identity_registered"
    assert (
        next(family for family in families if family["logical_key"] == "sp1500")["value"]["symbol"]
        is None
    )
    assert next(family for family in families if family["logical_key"] == "sp1500")[
        "derived_equal_weight"
    ]["allowed"]
    assert "SPYV" in benchmark_family_proxy_symbols()
    assert "IWF" in benchmark_family_proxy_symbols()
    assert "QQQE" in benchmark_family_proxy_symbols()
    assert len(BENCHMARK_FAMILY_REGISTRY) == 8


class _AsyncSessionFacade:
    """Exercise the real async taxonomy contract against the unit SQLite session."""

    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    def add(self, value):
        self.session.add(value)


def test_industry_proxy_registry_is_explicit_and_does_not_infer_unknown_labels():
    assert industry_proxy_candidates("Semiconductors") == ("SOXX", "SMH")
    assert industry_proxy_candidates("semiconductors") == ()
    assert industry_proxy_candidates("Unclassified industry") == ()


def test_every_curated_industry_proxy_has_a_canonical_issuer_route():
    """Prevent a taxonomy candidate from silently falling back to name inference."""

    expected_adapters = {
        "SOXX": "ishares",
        "SMH": "vaneck",
        "XBI": "spdr",
        "IBB": "ishares",
        "KRE": "spdr",
        "ITA": "ishares",
        "XAR": "spdr",
        "XHB": "spdr",
        "ITB": "ishares",
        "XRT": "spdr",
        "OIH": "vaneck",
        "XOP": "spdr",
        "XME": "spdr",
        "SLX": "vaneck",
    }
    candidates = {symbol for symbols in _INDUSTRY_PROXY_CANDIDATES.values() for symbol in symbols}
    assert candidates == set(expected_adapters)
    for symbol, adapter_key in expected_adapters.items():
        metadata = known_etf_route_metadata(symbol)
        assert metadata["provider_aliases"]["holdings_adapter"] == adapter_key
        assert get_holdings_adapter(adapter_key) is not None


def test_benchmark_family_style_proxies_have_explicit_free_source_routes():
    """Family drill-down proxies must enter the holdings pipeline with issuer evidence."""

    spdr_symbols = ("SPYV", "SPYG", "MDY", "MDYV", "MDYG", "SLYV", "SLYG", "SPTM")
    for symbol in spdr_symbols:
        metadata = known_etf_route_metadata(symbol)
        assert metadata["issuer"] == "State Street Global Advisors"
        assert metadata["provider_aliases"]["holdings_adapter"] == "spdr"

    for symbol, product_id in {
        "IJR": "239774",
        "IWB": "239707",
        "IWD": "239708",
        "IWF": "239706",
        "IWN": "239712",
        "IWO": "239709",
        "IWV": "239714",
    }.items():
        metadata = known_etf_route_metadata(symbol)
        assert metadata["issuer"] == "iShares"
        assert metadata["provider_aliases"]["issuer_product_id"] == product_id

    qqqe_metadata = known_etf_route_metadata("QQQE")
    assert qqqe_metadata["issuer"] == "Direxion"
    assert qqqe_metadata["provider_aliases"]["holdings_adapter"] == "direxion"
    assert qqqe_metadata["provider_aliases"]["sec_cik"] == "0001424958"
    assert qqqe_metadata["provider_aliases"]["sec_series_id"] == "S000033634"
    assert qqqe_metadata["provider_aliases"]["sec_class_id"] == "C000103352"
    assert qqqe_metadata["provider_aliases"]["issuer_product_url"].endswith(
        "/nasdaq-100-equal-weighted-index-etf"
    )
    assert get_holdings_adapter("direxion") is not None
    assert get_holdings_adapter("direxion").resolve_source_url(symbol="QQQE") == (
        "https://www.direxion.com/holdings/QQQE.csv"
    )


def test_ishares_family_roles_declare_the_supported_as_of_history_route():
    expected_symbols = {"IJR", "IWB", "IWD", "IWF", "IWM", "IWN", "IWO", "IWV"}
    observed: set[str] = set()
    for family in benchmark_family_registry():
        for role in ("cap_weight", "equal_weight", "value", "growth"):
            mapping = family[role]
            if mapping.get("symbol") not in expected_symbols:
                continue
            observed.add(mapping["symbol"])
            assert mapping["history_route"] == {
                "status": "issuer_as_of_date",
                "provider": "ishares",
                "policy": "issuer_public_json_api_as_of_date",
                "source_url": (
                    "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
                    "product-data/api/v2/get-product-data"
                ),
            }
    assert observed == expected_symbols


def test_spdr_family_roles_declare_current_only_history_route():
    expected_symbols = {"SPY", "SPYV", "SPYG", "MDY", "MDYV", "MDYG", "SLYV", "SLYG", "SPTM"}
    observed: set[str] = set()
    for family in benchmark_family_registry():
        for role in ("cap_weight", "equal_weight", "value", "growth"):
            mapping = family[role]
            if mapping.get("symbol") not in expected_symbols:
                continue
            observed.add(mapping["symbol"])
            assert mapping["history_route"] == {
                "status": "issuer_current_only",
                "provider": "spdr",
                "policy": "issuer_daily_workbook_current_snapshot_only",
                "source_url": (
                    "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
                    "products/fund-data/etfs/us/holdings-daily-us-en-"
                    f"{mapping['symbol'].lower()}.xlsx"
                ),
            }
    assert observed == expected_symbols


def test_invesco_family_roles_declare_current_only_history_route():
    mapping = next(
        family for family in benchmark_family_registry() if family["logical_key"] == "sp500"
    )["equal_weight"]
    assert mapping["symbol"] == "RSP"
    assert mapping["history_route"] == {
        "status": "issuer_current_only",
        "provider": "invesco",
        "policy": "issuer_public_json_catalog_current_monthly_only",
        "source_url": (
            "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
            "46137V357/holdings/fund?idType=cusip&interval=monthly&productType=ETF"
        ),
    }


def test_every_configured_family_role_has_explicit_route_or_is_unavailable():
    """Keep the family matrix identity-first instead of relying on issuer inference."""

    mapped_roles = 0
    unavailable_roles = 0
    for family in benchmark_family_registry():
        for role in ("cap_weight", "equal_weight", "value", "growth"):
            mapping = family[role]
            symbol = mapping.get("symbol")
            if not symbol:
                unavailable_roles += 1
                assert mapping["verification_state"] == "not_verified"
                continue

            mapped_roles += 1
            metadata = known_etf_route_metadata(symbol)
            aliases = metadata["provider_aliases"]
            adapter_key = aliases.get("holdings_adapter")
            assert metadata["issuer"]
            assert adapter_key, (family["logical_key"], role, symbol, metadata)
            assert get_holdings_adapter(adapter_key) is not None

    assert mapped_roles == 20
    assert unavailable_roles == 12


def test_canonical_industry_label_accepts_only_reviewed_provider_aliases():
    assert canonical_industry_label("Semiconductors") == "Semiconductors"
    assert canonical_industry_label("Semiconductors & Related Devices") == "Semiconductors"
    assert canonical_industry_label("Information Technology") == "Information Technology"
    assert canonical_industry_label(None) is None


def test_source_classification_preserves_system_and_rejects_future_historical_metadata():
    provenance = {
        "industry": {
            "classification_system": "SEC_SIC",
            "observed_at": "2026-08-10T12:00:00+00:00",
        }
    }

    label, system = source_classification_for_as_of(
        industry="Semiconductors & Related Devices",
        sector=None,
        field_provenance=provenance,
        as_of=None,
    )
    assert (label, system) == ("Semiconductors", "SEC_SIC")

    label, system = source_classification_for_as_of(
        industry="Semiconductors & Related Devices",
        sector=None,
        field_provenance=provenance,
        as_of=datetime.fromisoformat("2026-08-09T23:59:59+00:00"),
    )
    assert label is None
    assert system == "SEC_SIC"


def test_source_classification_requires_timestamp_for_point_in_time_reads():
    label, system = source_classification_for_as_of(
        industry="Semiconductors",
        sector=None,
        field_provenance={"industry": {"classification_system": "SEC_SIC"}},
        as_of=datetime.fromisoformat("2026-08-09T23:59:59+00:00"),
    )
    assert label is None
    assert system == "SEC_SIC"


def test_source_classification_keeps_unknown_namespace_visible_for_current_reads():
    label, system = source_classification_for_as_of(
        industry="Unmapped Provider Label",
        sector=None,
        field_provenance={"industry": {"observed_at": "2026-08-09T23:59:59+00:00"}},
        as_of=None,
    )
    assert (label, system) == ("Unmapped Provider Label", "unknown")


def test_source_classification_never_promotes_sector_to_industry():
    label, system = source_classification_for_as_of(
        industry=None,
        sector="Information Technology",
        field_provenance={"sector": {"classification_system": "provider_native"}},
        as_of=None,
    )
    assert label is None
    assert system == "unknown"


def test_profile_snapshot_classification_is_source_labelled():
    assert source_classification_from_profile_snapshot(
        {
            "extra": {
                "industry": "Semiconductors & Related Devices",
                "classification_system": "SEC_SIC",
            }
        }
    ) == ("Semiconductors", "SEC_SIC")
    assert source_classification_from_profile_snapshot({}) == (None, "unknown")
    assert source_classification_from_profile_snapshot(
        {"extra": {"sector": "Information Technology", "classification_system": "provider_native"}}
    ) == (None, "unknown")


def test_seed_top_down_taxonomy_attaches_known_proxies_and_is_idempotent(db, instrument_type):
    symbols = [(symbol, name) for symbol, name, *_ in _BENCHMARKS] + list(_SECTORS)
    symbols.extend((symbol, f"{symbol} proxy") for symbol in benchmark_family_proxy_symbols())
    db.add_all(
        [
            Instrument(
                symbol=symbol,
                name=name,
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            for symbol, name in symbols
        ]
    )
    db.flush()
    facade = _AsyncSessionFacade(db)

    asyncio.run(seed_top_down_taxonomy(facade))
    asyncio.run(seed_top_down_taxonomy(facade))

    groups = db.execute(select(MarketGroup)).scalars().all()
    assert {group.stable_key for group in groups} == {
        "us-benchmarks",
        "sp500-sectors",
        "sp500",
        "sp400",
        "sp600",
        "sp1500",
        "russell1000",
        "russell2000",
        "russell3000",
        "nasdaq100",
    }
    members = db.execute(select(MarketGroupMember)).scalars().all()
    assert len(members) == len(_BENCHMARKS) + len(_SECTORS) + sum(
        sum(
            1
            for role in ("cap_weight", "equal_weight", "value", "growth")
            if family[role]["symbol"]
        )
        for family in BENCHMARK_FAMILY_REGISTRY
    )
    assert {member.source for member in members} == {"curated_top_down_taxonomy"}
    assert {member.verification_state for member in members} == {
        "proxy_verified",
        "proxy_identity_registered",
    }
    benchmark = next(group for group in groups if group.stable_key == "us-benchmarks")
    assert benchmark.provenance["benchmark_identities"]["sp500"]["official_index_symbol"] == "SPX"
    assert benchmark.provenance["benchmark_identities"]["sp500"]["default_tradable_proxy"] == "SPY"
    family_by_key = {
        group.stable_key: group for group in groups if group.group_type == "benchmark_family"
    }
    assert family_by_key["nasdaq100"].parent_id == benchmark.id
    assert family_by_key["nasdaq100"].representative_instrument_id is not None
    assert family_by_key["nasdaq100"].equal_weight_instrument_id is not None
    assert {
        member.relationship_type
        for member in members
        if member.market_group_id == family_by_key["sp500"].id
    } == {
        "cap_weight_proxy",
        "equal_weight_proxy",
        "value_proxy",
        "growth_proxy",
    }
