"""Canonical, point-in-time market-group read APIs."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import EquityDetail, Instrument
from app.models.user import User
from app.models.workstation import MarketGroup, MarketGroupMember, MarketGroupProxy
from app.schemas.workstation import (
    ETFIndustryCompositionOut,
    ETFIndustryConstituentsOut,
    ETFIndustryOut,
    InstrumentReferenceOut,
    MarketGroupOut,
)
from app.services.top_down_taxonomy import seed_top_down_taxonomy

router = APIRouter(prefix="/market-groups", tags=["market-groups"])


def _groups_query():
    return select(MarketGroup).options(
        selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument),
        selectinload(MarketGroup.proxies).selectinload(MarketGroupProxy.instrument),
    )


@router.get("/etf/{symbol}/industries", response_model=ETFIndustryCompositionOut)
async def etf_industry_composition(
    symbol: str,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Classify only constituents from an ETF snapshot known at the requested time.

    This intentionally exposes a composition proxy, never an official index universe.
    Unclassified or unresolved holding rows remain counted as exclusions instead of
    being silently assigned to an industry.
    """
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})
    profile = (
        await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == instrument.id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            404, detail={"code": "etf_profile_not_found", "symbol": instrument.symbol}
        )

    statement = select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    if as_of is not None:
        statement = statement.where(
            ETFHoldingsSnapshot.composition_date <= as_of.date(),
            (ETFHoldingsSnapshot.known_at.is_(None)) | (ETFHoldingsSnapshot.known_at <= as_of),
        )
    snapshot = (
        await db.execute(
            statement.order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(
            404, detail={"code": "etf_holdings_snapshot_not_found", "symbol": instrument.symbol}
        )

    rows = (
        await db.execute(
            select(ETFHolding, EquityDetail.industry)
            .outerjoin(
                EquityDetail, EquityDetail.instrument_id == ETFHolding.constituent_instrument_id
            )
            .where(ETFHolding.snapshot_id == snapshot.id)
        )
    ).all()
    grouped: dict[str, list[ETFHolding]] = {}
    exclusions: list[str] = []
    for row, industry in rows:
        if not row.is_resolved:
            exclusions.append("unresolved_holding")
        elif not industry:
            exclusions.append("unclassified_constituent")
        else:
            grouped.setdefault(industry, []).append(row)
    return ETFIndustryCompositionOut(
        etf_symbol=instrument.symbol,
        composition_date=snapshot.composition_date.isoformat(),
        known_at=snapshot.known_at,
        provenance=snapshot.provenance,
        source_provider=snapshot.source_provider,
        completeness_status=snapshot.completeness_status,
        industries=[
            ETFIndustryOut(
                industry=industry,
                constituent_count=len(items),
                resolved_count=sum(1 for item in items if item.is_resolved),
            )
            for industry, items in sorted(grouped.items())
        ],
        exclusions=sorted(set(exclusions)),
    )


@router.get("/etf/{symbol}/industries/{industry}", response_model=ETFIndustryConstituentsOut)
async def etf_industry_constituents(
    symbol: str,
    industry: str,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    composition = await etf_industry_composition(symbol=symbol, as_of=as_of, _=_, db=db)
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == composition.etf_symbol))
    ).scalar_one()
    profile = (
        await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == instrument.id))
    ).scalar_one()
    snapshot_query = select(ETFHoldingsSnapshot).where(
        ETFHoldingsSnapshot.etf_profile_id == profile.id
    )
    if as_of is not None:
        snapshot_query = snapshot_query.where(
            ETFHoldingsSnapshot.composition_date <= as_of.date(),
            (ETFHoldingsSnapshot.known_at.is_(None)) | (ETFHoldingsSnapshot.known_at <= as_of),
        )
    snapshot = (
        await db.execute(
            snapshot_query.order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.known_at.desc().nullslast(),
                ETFHoldingsSnapshot.id.desc(),
            ).limit(1)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(Instrument)
                .join(ETFHolding, ETFHolding.constituent_instrument_id == Instrument.id)
                .join(EquityDetail, EquityDetail.instrument_id == Instrument.id)
                .where(
                    ETFHolding.snapshot_id == snapshot.id,
                    ETFHolding.is_resolved.is_(True),
                    EquityDetail.industry == industry,
                )
                .order_by(ETFHolding.position, Instrument.symbol)
            )
        )
        .scalars()
        .all()
    )
    return ETFIndustryConstituentsOut(
        etf_symbol=composition.etf_symbol,
        industry=industry,
        composition_date=composition.composition_date,
        known_at=composition.known_at,
        provenance=composition.provenance,
        source_provider=composition.source_provider,
        constituents=[InstrumentReferenceOut.model_validate(item) for item in rows],
        exclusions=composition.exclusions,
    )


@router.get("", response_model=list[MarketGroupOut])
async def list_market_groups(
    parent_id: int | None = None,
    group_type: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await seed_top_down_taxonomy(db)
    await db.flush()
    statement = _groups_query().order_by(MarketGroup.group_type, MarketGroup.name)
    if parent_id is None:
        statement = statement.where(MarketGroup.parent_id.is_(None))
    else:
        statement = statement.where(MarketGroup.parent_id == parent_id)
    if group_type:
        statement = statement.where(MarketGroup.group_type == group_type)
    return (await db.execute(statement)).scalars().unique().all()


@router.get("/{stable_key}", response_model=MarketGroupOut)
async def get_market_group(
    stable_key: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await seed_top_down_taxonomy(db)
    await db.flush()
    group = (
        await db.execute(_groups_query().where(MarketGroup.stable_key == stable_key))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Market group not found")
    return group
