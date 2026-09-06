"""Curated, source-labelled US top-down taxonomy.

The taxonomy deliberately creates *relationships*, never instruments.  A missing
canonical instrument remains absent rather than being fabricated from a ticker.
ETF holdings are only added by the dedicated holdings ingestion pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.workstation import MarketGroup, MarketGroupMember

_BENCHMARKS = (
    ("SPY", "S&P 500 proxy", "representative"),
    ("RSP", "S&P 500 equal weight", "equal_weight"),
    ("QQQ", "Nasdaq-100 proxy", "representative"),
    ("DIA", "Dow 30 proxy", "representative"),
    ("IWM", "Russell 2000 proxy", "representative"),
)

_SECTORS = (
    ("XLK", "Technology"),
    ("XLY", "Consumer Discretionary"),
    ("XLC", "Communication Services"),
    ("XLF", "Financials"),
    ("XLV", "Health Care"),
    ("XLI", "Industrials"),
    ("XLP", "Consumer Staples"),
    ("XLE", "Energy"),
    ("XLU", "Utilities"),
    ("XLRE", "Real Estate"),
    ("XLB", "Materials"),
)

_SP500_IDENTITY = {
    "logical_key": "sp500",
    "official_index_symbol": "SPX",
    "default_tradable_proxy": "SPY",
    "proxy_label": "S&P 500 proxy (SPY)",
    "official_series_policy": "use_only_when_entitled",
}

# iShares exposes an explicit ``asOfDate`` parameter on the same public product
# data endpoint used by the canonical holdings adapter.  Keep this declaration
# beside the family registry so dated refresh planning can distinguish a
# verified issuer-as-of route from roles whose provider only exposes current
# holdings.  The route proves capability, not that any dated snapshot has been
# fetched or is complete.
_ISHARES_HISTORY_ROUTE = {
    "status": "issuer_as_of_date",
    "provider": "ishares",
    "policy": "issuer_public_json_api_as_of_date",
    "source_url": (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data"
    ),
}

# The family registry is deliberately metadata-first.  A configured ETF ticker
# is an identity candidate, not proof that the ETF is an official constituent
# source or that its holdings are complete at every historical date.  The
# ``verification_state`` on each mapping is therefore carried into the
# workstation response and is upgraded only by the canonical holdings/provider
# evidence pipeline.  ``derived_equal_weight`` describes the safe fallback
# methodology when no verified equal-weight ETF exists; it does not fabricate an
# instrument or imply an index-provider relationship.
BENCHMARK_FAMILY_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "logical_key": "sp500",
        "name": "S&P 500",
        "official_index_symbol": "SPX",
        "official_index_name": "S&P 500 Index",
        "cap_weight": {
            "symbol": "SPY",
            "label": "S&P 500 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy",
        },
        "equal_weight": {
            "symbol": "RSP",
            "label": "S&P 500 equal-weight ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.invesco.com/us/en/etf/rsp",
        },
        "value": {
            "symbol": "SPYV",
            "label": "S&P 500 value ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/state-street-spdr-portfolio-sp-500-value-etf-spyv",
        },
        "growth": {
            "symbol": "SPYG",
            "label": "S&P 500 growth ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-portfolio-sp-500-growth-etf-spyg",
        },
        "derived_equal_weight": {"allowed": False, "method": None},
    },
    {
        "logical_key": "sp400",
        "name": "S&P MidCap 400",
        "official_index_symbol": "MID",
        "official_index_name": "S&P MidCap 400 Index",
        "cap_weight": {
            "symbol": "MDY",
            "label": "S&P MidCap 400 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-midcap-400-etf-trust-mdy",
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": "MDYV",
            "label": "S&P MidCap 400 value ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-400-mid-cap-value-etf-mdyv",
        },
        "growth": {
            "symbol": "MDYG",
            "label": "S&P MidCap 400 growth ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-400-mid-cap-growth-etf-mdyg",
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "sp600",
        "name": "S&P SmallCap 600",
        "official_index_symbol": "SML",
        "official_index_name": "S&P SmallCap 600 Index",
        "cap_weight": {
            "symbol": "IJR",
            "label": "S&P SmallCap 600 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239774/ishares-core-sp-smallcap-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": "SLYV",
            "label": "S&P SmallCap 600 value ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-600-small-cap-value-etf-slyv",
        },
        "growth": {
            "symbol": "SLYG",
            "label": "S&P SmallCap 600 growth ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/spdr-sp-600-small-cap-growth-etf-slyg",
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "sp1500",
        "name": "S&P Composite 1500",
        "official_index_symbol": "SPSUPX",
        "official_index_name": "S&P Composite 1500 Index",
        "cap_weight": {
            "symbol": "SPTM",
            "label": "S&P Composite 1500 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ssga.com/us/en/individual/etfs/state-street-spdr-portfolio-sp-1500-composite-stock-market-etf-sptm",
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "growth": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "russell1000",
        "name": "Russell 1000",
        "official_index_symbol": "RUI",
        "official_index_name": "Russell 1000 Index",
        "cap_weight": {
            "symbol": "IWB",
            "label": "Russell 1000 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": "IWD",
            "label": "Russell 1000 value ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239708/ishares-russell-1000-value-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "growth": {
            "symbol": "IWF",
            "label": "Russell 1000 growth ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239706/ishares-russell-1000-growth-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "russell2000",
        "name": "Russell 2000",
        "official_index_symbol": "RTY",
        "official_index_name": "Russell 2000 Index",
        "cap_weight": {
            "symbol": "IWM",
            "label": "Russell 2000 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": "IWN",
            "label": "Russell 2000 value ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239712/ishares-russell-2000-value-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "growth": {
            "symbol": "IWO",
            "label": "Russell 2000 growth ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239709/ishares-russell-2000-growth-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "russell3000",
        "name": "Russell 3000",
        "official_index_symbol": "RUA",
        "official_index_name": "Russell 3000 Index",
        "cap_weight": {
            "symbol": "IWV",
            "label": "Russell 3000 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.ishares.com/us/products/239714/ishares-russell-3000-etf",
            "history_route": dict(_ISHARES_HISTORY_ROUTE),
        },
        "equal_weight": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "value": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "growth": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "derived_equal_weight": {
            "allowed": True,
            "method": "equal_start_weight_point_in_time_membership_rebalanced_on_declared_schedule",
        },
    },
    {
        "logical_key": "nasdaq100",
        "name": "Nasdaq 100",
        "official_index_symbol": "NDX",
        "official_index_name": "Nasdaq-100 Index",
        "cap_weight": {
            "symbol": "QQQ",
            "label": "Nasdaq-100 cap-weighted ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.invesco.com/qqq-etf/en/about.html",
            "history_route": {
                "status": "sec_filing_reconstruction",
                "provider": "sec",
                "policy": "latest_sec_filing_report_on_or_before_requested_date",
                "source_url": "https://data.sec.gov/submissions/CIK0001067839.json",
            },
        },
        "equal_weight": {
            "symbol": "QQQE",
            "label": "Nasdaq-100 equal-weight ETF proxy",
            "verification_state": "proxy_identity_registered",
            "source_url": "https://www.direxion.com/product/nasdaq-100-equal-weighted-index-etf",
            "history_route": {
                "status": "sec_filing_reconstruction",
                "provider": "sec",
                "policy": "latest_sec_filing_report_on_or_before_requested_date",
                "source_url": "https://data.sec.gov/submissions/CIK0001424958.json",
            },
        },
        "value": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "growth": {
            "symbol": None,
            "label": "No verified mapped proxy",
            "verification_state": "not_verified",
            "source_url": None,
        },
        "derived_equal_weight": {"allowed": False, "method": None},
    },
)


def benchmark_family_registry() -> list[dict[str, Any]]:
    """Return JSON-safe family metadata without exposing mutable module state."""

    return [
        {
            **family,
            **{
                role: dict(mapping)
                for role in (
                    "cap_weight",
                    "equal_weight",
                    "value",
                    "growth",
                    "derived_equal_weight",
                )
                if isinstance((mapping := family.get(role)), dict)
            },
        }
        for family in BENCHMARK_FAMILY_REGISTRY
    ]


def benchmark_family_proxy_symbols() -> tuple[str, ...]:
    """Return only configured tradable proxy identities, preserving registry order."""

    return tuple(
        dict.fromkeys(
            mapping["symbol"]
            for family in BENCHMARK_FAMILY_REGISTRY
            for role in ("cap_weight", "equal_weight", "value", "growth")
            if (mapping := family.get(role)) and mapping.get("symbol")
        )
    )


# A versioned candidate registry, not a name-based inference rule. Candidates become
# visible only when their own disclosed holdings independently contain classified
# constituents for the selected industry (see the market-groups proxy endpoint).
_INDUSTRY_PROXY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "Semiconductors": ("SOXX", "SMH"),
    "Biotechnology": ("XBI", "IBB"),
    "Regional Banks": ("KRE",),
    "Aerospace & Defense": ("ITA", "XAR"),
    "Homebuilding": ("XHB", "ITB"),
    "Retail": ("XRT",),
    "Oil & Gas Equipment & Services": ("OIH",),
    "Oil & Gas Exploration & Production": ("XOP",),
    "Metals & Mining": ("XME",),
    "Steel": ("SLX",),
}

# EDGAR exposes SIC descriptions as a sector-like field rather than the
# platform's shorter industry names.  These aliases are deliberately narrow
# and source-labelled; they prevent a verified semiconductor ETF from becoming
# unusable merely because free metadata says "Semiconductors & Related Devices".
_INDUSTRY_ALIASES: dict[str, str] = {
    "semiconductors": "Semiconductors",
    "semiconductors & related devices": "Semiconductors",
}


def canonical_industry_label(value: str | None) -> str | None:
    """Normalize only reviewed provider classification aliases."""

    if not value or not value.strip():
        return None
    text = " ".join(value.split())
    return _INDUSTRY_ALIASES.get(text.casefold(), text)


def source_classification_for_as_of(
    *,
    industry: str | None,
    sector: str | None,
    field_provenance: dict[str, Any] | None,
    as_of: datetime | None = None,
) -> tuple[str | None, str]:
    """Return a source-labelled classification only when its evidence is eligible.

    ``EquityDetail`` is a current canonical read model.  For an explicit historical
    request, a current value without a field-level observation timestamp cannot be
    treated as point-in-time truth, so it is excluded rather than backfilled into the
    past.  The returned system is intentionally exposed to callers; SEC SIC is not
    silently presented as GICS.
    """

    # This helper feeds the industry taxonomy. A sector label is a different
    # classification level and must never be promoted into an industry just
    # because the provider omitted the industry field.
    label = canonical_industry_label(industry)
    if not label:
        return None, "unknown"
    metadata = field_provenance or {}
    evidence = metadata.get("industry") or {}
    system = str(evidence.get("classification_system") or "unknown")
    if as_of is not None:
        observed_text = evidence.get("observed_at") or evidence.get("known_at")
        if not observed_text:
            return None, system
        try:
            observed_at = datetime.fromisoformat(str(observed_text).replace("Z", "+00:00"))
        except ValueError:
            return None, system
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        if observed_at > as_of:
            return None, system
    return label, system


def source_classification_from_profile_snapshot(
    payload: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """Read a historical provider profile snapshot without treating it as current state."""

    metadata = payload or {}
    extra = metadata.get("extra") or {}
    # Historical snapshots use the same strict industry-level contract. A
    # sector-only observation cannot establish industry membership.
    label = canonical_industry_label(extra.get("industry") or metadata.get("industry"))
    if not label:
        return None, "unknown"
    return label, str(extra.get("classification_system") or "provider_native")


def industry_proxy_candidates(industry: str) -> tuple[str, ...]:
    """Return only explicitly curated candidate symbols for an exact industry label."""
    return _INDUSTRY_PROXY_CANDIDATES.get(industry, ())


async def seed_top_down_taxonomy(db: AsyncSession) -> None:
    """Ensure the stable root groups exist and attach already-known instruments.

    The static mapping is a product taxonomy, with provenance explicit about its
    proxy nature.  It is not an assertion of official S&P constituent ownership.
    """
    existing = {
        group.stable_key: group for group in (await db.execute(select(MarketGroup))).scalars()
    }
    observed_at = datetime.now(UTC)
    roots = {
        "us-benchmarks": (
            "benchmark",
            "US Benchmarks",
            {
                "taxonomy_version": "us-top-down-v2",
                "benchmark_identities": {"sp500": _SP500_IDENTITY},
                "benchmark_families": benchmark_family_registry(),
            },
        ),
        "sp500-sectors": (
            "sector",
            "S&P 500 Select Sector ETF proxies",
            {"taxonomy_version": "us-top-down-v2"},
        ),
    }
    for stable_key, (group_type, name, taxonomy_provenance) in roots.items():
        if stable_key not in existing:
            existing[stable_key] = MarketGroup(
                stable_key=stable_key,
                group_type=group_type,
                name=name,
                source="curated_top_down_taxonomy",
                provenance={
                    "classification": "product_taxonomy",
                    "membership_semantics": "ETF proxy where applicable",
                    "official_index_constituents": False,
                    **taxonomy_provenance,
                },
                known_at=observed_at,
            )
            db.add(existing[stable_key])
        else:
            existing[stable_key].provenance = {
                **(existing[stable_key].provenance or {}),
                **taxonomy_provenance,
            }
    await db.flush()

    # Family groups are children of the root benchmark group.  They keep the
    # root's historical SPY/RSP/DIA/IWM navigation stable while making every
    # supported index/style leg selectable through the same market-group API.
    family_groups: dict[str, MarketGroup] = {}
    benchmark_root = existing["us-benchmarks"]
    for family in BENCHMARK_FAMILY_REGISTRY:
        stable_key = str(family["logical_key"])
        mappings = {
            role: dict(family.get(role) or {})
            for role in ("cap_weight", "equal_weight", "value", "growth")
        }
        provenance = {
            "classification": "product_taxonomy",
            "taxonomy_version": "us-top-down-v3",
            "family_key": stable_key,
            "official_index": {
                "symbol": family["official_index_symbol"],
                "name": family["official_index_name"],
                "series_policy": "use_only_when_entitled",
            },
            "proxy_mappings": mappings,
            "derived_equal_weight": dict(family.get("derived_equal_weight") or {}),
            "membership_semantics": "official_index_when_entitled_or_explicitly_labelled_proxy",
            "relationship_evidence_policy": "canonical_identity_and_point_in_time_source_evidence_required",
        }
        group = existing.get(stable_key)
        if group is None:
            group = MarketGroup(
                stable_key=stable_key,
                group_type="benchmark_family",
                name=str(family["name"]),
                parent_id=benchmark_root.id,
                source="curated_top_down_taxonomy",
                provenance=provenance,
                effective_at=None,
                known_at=observed_at,
            )
            db.add(group)
            existing[stable_key] = group
        else:
            group.parent_id = benchmark_root.id
            group.name = str(family["name"])
            group.group_type = "benchmark_family"
            group.provenance = {**(group.provenance or {}), **provenance}
            group.known_at = group.known_at or observed_at
        family_groups[stable_key] = group
    await db.flush()

    # Do not touch the relationship collection here.  Startup runs in an
    # AsyncSession, and a collection that was not loaded in this transaction
    # would trigger an implicit lazy query and MissingGreenlet.  Keep the
    # duplicate check explicit and queryable instead.
    member_rows = (
        await db.execute(select(MarketGroupMember.market_group_id, MarketGroupMember.instrument_id))
    ).all()
    member_ids_by_group: dict[int, set[int]] = {}
    for market_group_id, instrument_id in member_rows:
        member_ids_by_group.setdefault(market_group_id, set()).add(instrument_id)

    symbols = list(
        dict.fromkeys(
            [item[0] for item in _BENCHMARKS]
            + [item[0] for item in _SECTORS]
            + list(benchmark_family_proxy_symbols())
        )
    )
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }

    async def attach(
        group_key: str,
        symbol: str,
        relationship_type: str,
        position: int,
        *,
        verification_state: str = "proxy_verified",
        relationship_provenance: dict[str, Any] | None = None,
    ) -> None:
        instrument = instruments.get(symbol)
        if instrument is None:
            return
        group = existing[group_key]
        if instrument.id in member_ids_by_group.setdefault(group.id, set()):
            return
        db.add(
            MarketGroupMember(
                market_group_id=group.id,
                instrument_id=instrument.id,
                relationship_type=relationship_type,
                position=position,
                source="curated_top_down_taxonomy",
                verification_state=verification_state,
                known_at=observed_at,
                provenance={
                    "symbol": symbol,
                    "classification": "ETF/index proxy",
                    **(relationship_provenance or {}),
                },
            )
        )
        member_ids_by_group[group.id].add(instrument.id)

    for position, (symbol, _, relationship_type) in enumerate(_BENCHMARKS):
        await attach("us-benchmarks", symbol, relationship_type, position)
    for position, (symbol, _) in enumerate(_SECTORS):
        await attach("sp500-sectors", symbol, "sector_etf_proxy", position)

    for family in BENCHMARK_FAMILY_REGISTRY:
        family_key = str(family["logical_key"])
        group = family_groups[family_key]
        mappings = {
            role: dict(family.get(role) or {})
            for role in ("cap_weight", "equal_weight", "value", "growth")
        }
        for position, (role, mapping) in enumerate(mappings.items()):
            symbol = mapping.get("symbol")
            if not symbol:
                continue
            await attach(
                family_key,
                str(symbol),
                f"{role}_proxy",
                position,
                verification_state=str(mapping.get("verification_state") or "not_verified"),
                relationship_provenance={
                    "family_key": family_key,
                    "mapping_role": role,
                    "source_url": mapping.get("source_url"),
                    "mapping_label": mapping.get("label"),
                },
            )
            instrument = instruments.get(str(symbol).upper())
            if instrument is not None:
                if role == "cap_weight" and group.representative_instrument_id is None:
                    group.representative_instrument_id = instrument.id
                if (
                    role == "equal_weight"
                    and mapping.get("verification_state") == "proxy_identity_registered"
                    and group.equal_weight_instrument_id is None
                ):
                    group.equal_weight_instrument_id = instrument.id
