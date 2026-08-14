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

    symbols = [item[0] for item in _BENCHMARKS] + [item[0] for item in _SECTORS]
    instruments = {
        instrument.symbol.upper(): instrument
        for instrument in (
            await db.execute(select(Instrument).where(Instrument.symbol.in_(symbols)))
        ).scalars()
    }

    async def attach(group_key: str, symbol: str, relationship_type: str, position: int) -> None:
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
                verification_state="proxy_verified",
                known_at=observed_at,
                provenance={"symbol": symbol, "classification": "ETF/index proxy"},
            )
        )
        member_ids_by_group[group.id].add(instrument.id)

    for position, (symbol, _, relationship_type) in enumerate(_BENCHMARKS):
        await attach("us-benchmarks", symbol, relationship_type, position)
    for position, (symbol, _) in enumerate(_SECTORS):
        await attach("sp500-sectors", symbol, "sector_etf_proxy", position)
