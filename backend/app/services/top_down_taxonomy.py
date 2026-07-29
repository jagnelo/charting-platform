"""Curated, source-labelled US top-down taxonomy.

The taxonomy deliberately creates *relationships*, never instruments.  A missing
canonical instrument remains absent rather than being fabricated from a ticker.
ETF holdings are only added by the dedicated holdings ingestion pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    ("XLK", "Technology"), ("XLY", "Consumer Discretionary"),
    ("XLC", "Communication Services"), ("XLF", "Financials"),
    ("XLV", "Health Care"), ("XLI", "Industrials"),
    ("XLP", "Consumer Staples"), ("XLE", "Energy"),
    ("XLU", "Utilities"), ("XLRE", "Real Estate"), ("XLB", "Materials"),
)


async def seed_top_down_taxonomy(db: AsyncSession) -> None:
    """Ensure the stable root groups exist and attach already-known instruments.

    The static mapping is a product taxonomy, with provenance explicit about its
    proxy nature.  It is not an assertion of official S&P constituent ownership.
    """
    existing = {
        group.stable_key: group
        for group in (
            await db.execute(select(MarketGroup).options(selectinload(MarketGroup.members)))
        ).scalars()
    }
    observed_at = datetime.now(UTC)
    roots = {
        "us-benchmarks": ("benchmark", "US Benchmarks"),
        "sp500-sectors": ("sector", "S&P 500 Select Sector ETF proxies"),
    }
    for stable_key, (group_type, name) in roots.items():
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
                },
                known_at=observed_at,
            )
            db.add(existing[stable_key])
    await db.flush()

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
        if any(member.instrument_id == instrument.id for member in group.members):
            return
        group.members.append(MarketGroupMember(
            instrument_id=instrument.id,
            relationship_type=relationship_type,
            position=position,
            source="curated_top_down_taxonomy",
            verification_state="proxy_verified",
            known_at=observed_at,
            provenance={"symbol": symbol, "classification": "ETF/index proxy"},
        ))

    for position, (symbol, _, relationship_type) in enumerate(_BENCHMARKS):
        await attach("us-benchmarks", symbol, relationship_type, position)
    for position, (symbol, _) in enumerate(_SECTORS):
        await attach("sp500-sectors", symbol, "sector_etf_proxy", position)
