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
    ETFIndustryProxyListOut,
    ETFIndustryProxyOut,
    InstrumentReferenceOut,
    MarketGroupOut,
)
from app.services.top_down_taxonomy import industry_proxy_candidates, seed_top_down_taxonomy

router = APIRouter(prefix="/market-groups", tags=["market-groups"])


def _holdings_snapshot_at(statement, as_of: datetime | None):
    """Apply historical-safe holdings eligibility to a snapshot query.

    A disclosure without ``known_at`` cannot prove that it was available at a
    historical evaluation time. It remains eligible for the current/latest view,
    but is excluded from every explicit point-in-time request.
    """
    if as_of is None:
        return statement
    return statement.where(
        ETFHoldingsSnapshot.composition_date <= as_of.date(),
        ETFHoldingsSnapshot.known_at.is_not(None),
        ETFHoldingsSnapshot.known_at <= as_of,
    )


def _groups_query():
    return select(MarketGroup).options(
        selectinload(MarketGroup.members).selectinload(MarketGroupMember.instrument),
        selectinload(MarketGroup.proxies).selectinload(MarketGroupProxy.instrument),
    )


async def _ensure_taxonomy_if_empty(db: AsyncSession) -> None:
    """Support empty test/bootstrap databases without mutating normal reads.

    Production startup and scheduled maintenance own taxonomy refreshes. The
    one-time empty-database fallback keeps a freshly created database usable,
    while avoiding the previous relationship-heavy seed on every workstation
    request.
    """
    result = await db.execute(select(MarketGroup.id).limit(1))
    if result.scalar_one_or_none() is None:
        await seed_top_down_taxonomy(db)
        await db.flush()


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

    statement = _holdings_snapshot_at(
        select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id),
        as_of,
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


@router.get("/etf/{symbol}/industries/{industry}/proxies", response_model=ETFIndustryProxyListOut)
async def etf_industry_proxies(
    symbol: str,
    industry: str,
    as_of: datetime | None = Query(default=None),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return explicitly curated proxies only after holdings/classification proof.

    A curated symbol never becomes a visible proxy merely because its name sounds
    related. The proxy ETF must have a local, point-in-time holdings disclosure with
    resolved constituents classified into the exact requested industry.
    """
    composition = await etf_industry_composition(symbol=symbol, as_of=as_of, _=_, db=db)
    candidates = industry_proxy_candidates(industry)
    if not candidates:
        return ETFIndustryProxyListOut(
            etf_symbol=composition.etf_symbol,
            industry=industry,
            exclusions=["no_curated_proxy_candidate"],
        )
    instruments = (
        (await db.execute(select(Instrument).where(Instrument.symbol.in_(candidates))))
        .scalars()
        .all()
    )
    by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
    proxies: list[ETFIndustryProxyOut] = []
    exclusions: list[str] = []
    for candidate in candidates:
        instrument = by_symbol.get(candidate)
        if instrument is None:
            exclusions.append(f"candidate_not_canonical:{candidate}")
            continue
        profile = (
            await db.execute(select(ETFProfile).where(ETFProfile.instrument_id == instrument.id))
        ).scalar_one_or_none()
        if profile is None:
            exclusions.append(f"candidate_not_etf_profile:{candidate}")
            continue
        statement = _holdings_snapshot_at(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id),
            as_of,
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
            exclusions.append(f"candidate_no_point_in_time_holdings:{candidate}")
            continue
        classifications = (
            (
                await db.execute(
                    select(EquityDetail.industry)
                    .join(
                        ETFHolding,
                        ETFHolding.constituent_instrument_id == EquityDetail.instrument_id,
                    )
                    .where(
                        ETFHolding.snapshot_id == snapshot.id,
                        ETFHolding.is_resolved.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        classified_count = sum(1 for value in classifications if value)
        matching_count = sum(1 for value in classifications if value == industry)
        if not matching_count:
            exclusions.append(f"candidate_not_holdings_verified:{candidate}")
            continue
        proxies.append(
            ETFIndustryProxyOut(
                symbol=instrument.symbol,
                name=instrument.name,
                composition_date=snapshot.composition_date.isoformat(),
                known_at=snapshot.known_at,
                provenance=snapshot.provenance,
                source_provider=snapshot.source_provider,
                matching_constituent_count=matching_count,
                classified_constituent_count=classified_count,
                classification_coverage=matching_count / classified_count
                if classified_count
                else 0,
            )
        )
    return ETFIndustryProxyListOut(
        etf_symbol=composition.etf_symbol,
        industry=industry,
        candidate_symbols=list(candidates),
        proxies=proxies,
        exclusions=exclusions,
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
    snapshot_query = _holdings_snapshot_at(
        select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id),
        as_of,
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
    await _ensure_taxonomy_if_empty(db)
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
    await _ensure_taxonomy_if_empty(db)
    group = (
        await db.execute(_groups_query().where(MarketGroup.stable_key == stable_key))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Market group not found")
    return group
