"""TC-only opt-in fixtures for workstation scale/performance checks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_class import AssetClass, InstrumentType
from app.models.instrument import Instrument

_E2E_LARGE_UNIVERSE_PREFIX = "E2E_ROW_"


async def seed_e2e_large_universe(db: AsyncSession, count: int = 10_000) -> None:
    """Seed bounded controlled identities for the 10k-row workstation probe."""

    if count < 1 or count > 10_000:
        raise ValueError("E2E large-universe count must be between 1 and 10000")
    asset_class = await db.scalar(select(AssetClass).where(AssetClass.name == "Equity"))
    if asset_class is None:
        asset_class = AssetClass(name="Equity", description="Equity instruments")
        db.add(asset_class)
        await db.flush()
    instrument_type = await db.scalar(
        select(InstrumentType).where(
            InstrumentType.name == "Stock",
            InstrumentType.asset_class_id == asset_class.id,
        )
    )
    if instrument_type is None:
        instrument_type = InstrumentType(name="Stock", asset_class_id=asset_class.id)
        db.add(instrument_type)
        await db.flush()

    symbols = [f"{_E2E_LARGE_UNIVERSE_PREFIX}{index:05d}" for index in range(1, count + 1)]
    existing = {
        symbol.upper()
        for symbol in (
            await db.execute(select(Instrument.symbol).where(Instrument.symbol.in_(symbols)))
        )
        .scalars()
        .all()
    }
    for symbol in symbols:
        if symbol in existing:
            continue
        db.add(
            Instrument(
                symbol=symbol,
                name=f"Controlled dense-universe instrument {symbol.removeprefix(_E2E_LARGE_UNIVERSE_PREFIX)}",
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                field_provenance={
                    "seed": "e2e",
                    "controlled_fixture": True,
                    "stress_universe": "workstation_row_budget",
                },
            )
        )
    await db.flush()
