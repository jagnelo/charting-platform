"""Canonical, point-in-time market-group read APIs."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.etf_holdings import ETFHolding, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import EquityDetail, Instrument
from app.models.provider_observation import InstrumentProfileSnapshot
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
from app.services.top_down_taxonomy import (
    industry_proxy_candidates,
    seed_top_down_taxonomy,
    source_classification_for_as_of,
    source_classification_from_profile_snapshot,
)

router = APIRouter(prefix="/market-groups", tags=["market-groups"])


def _holding_exclusion_code(row: ETFHolding) -> str | None:
    """Return the explicit reason a holding cannot be an equity taxonomy member."""

    holding_type = str(row.holding_type or "").strip().casefold()
    row_type = str(row.row_type or "").strip().casefold()
    if row_type == "cash" or holding_type in {"cash", "currency", "collateral"}:
        return "cash_holding"
    if holding_type in {"derivative", "derivatives", "option", "future", "swap"}:
        return "derivative_holding"
    # A resolved flag without a canonical instrument ID is internally
    # inconsistent. Treat it as unresolved rather than allowing it into the
    # coverage denominator where the constituent endpoint cannot return it.
    if not row.is_resolved or row.constituent_instrument_id is None:
        return "unresolved_holding"
    if row_type != "security" or holding_type not in {"equity", "stock", "common_stock"}:
        return "non_equity_holding"
    return None


async def _historical_profile_payloads(
    db: AsyncSession,
    instrument_ids: set[int],
    as_of: datetime | None,
) -> dict[int, dict]:
    """Load the latest provider profile known by an explicit historical cutoff."""

    if as_of is None or not instrument_ids:
        return {}
    snapshots = (
        (
            await db.execute(
                select(InstrumentProfileSnapshot)
                .where(
                    InstrumentProfileSnapshot.instrument_id.in_(instrument_ids),
                    InstrumentProfileSnapshot.observed_at <= as_of,
                )
                .order_by(
                    InstrumentProfileSnapshot.instrument_id,
                    InstrumentProfileSnapshot.observed_at.desc(),
                    InstrumentProfileSnapshot.id.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    result: dict[int, dict] = {}
    for snapshot in snapshots:
        result.setdefault(snapshot.instrument_id, snapshot.payload)
    return result


def holdings_snapshot_source_filter(statement):
    """Keep controlled browser fixtures out of normal workstation reads.

    E2E data is opt-in and deterministic.  When the backend is serving the
    canonical free-source database, a fixture snapshot must not win merely
    because it has a newer composition date than a real disclosure.
    """
    if settings.E2E_SEED_MARKET_DATA:
        # Seeded browser acceptance must be deterministic even when it is run
        # against a persistent database that already contains newer canonical
        # disclosures.  Selecting the fixture source explicitly prevents a
        # mixed canonical/fixture composition from silently changing the
        # visual and drill-down oracle.
        return statement.where(
            ETFHoldingsSnapshot.provenance == "controlled_fixture",
            ETFHoldingsSnapshot.source_provider == "e2e_reference",
        )
    return statement.where(
        ETFHoldingsSnapshot.provenance != "controlled_fixture",
        ETFHoldingsSnapshot.source_provider != "e2e_reference",
    )


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

    statement = holdings_snapshot_source_filter(
        _holdings_snapshot_at(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id),
            as_of,
        )
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
            select(
                ETFHolding,
                EquityDetail.industry,
                EquityDetail.sector,
                EquityDetail.field_provenance,
            )
            .outerjoin(
                EquityDetail, EquityDetail.instrument_id == ETFHolding.constituent_instrument_id
            )
            .where(ETFHolding.snapshot_id == snapshot.id)
        )
    ).all()
    historical_profiles = await _historical_profile_payloads(
        db,
        {
            row.constituent_instrument_id
            for row, *_ in rows
            if row.is_resolved and row.constituent_instrument_id is not None
        },
        as_of,
    )
    grouped: dict[str, list[tuple[ETFHolding, str]]] = {}
    exclusions: list[str] = []
    classified_rows = 0
    classification_systems_seen: set[str] = set()
    for row, industry, sector, field_provenance in rows:
        exclusion = _holding_exclusion_code(row)
        if exclusion:
            exclusions.append(exclusion)
        else:
            label, classification_system = source_classification_for_as_of(
                industry=industry,
                sector=sector,
                field_provenance=field_provenance,
                as_of=as_of,
            )
            if label is None and row.constituent_instrument_id in historical_profiles:
                label, classification_system = source_classification_from_profile_snapshot(
                    historical_profiles[row.constituent_instrument_id]
                )
            # Preserve an explicit unknown source when a provider supplies a
            # label without a classification namespace. The frontend must not
            # render that row as if it had no classification at all.
            classification_systems_seen.add(classification_system)
            if not label:
                exclusions.append(
                    "classification_not_known_at_as_of"
                    if as_of is not None
                    else "unclassified_constituent"
                )
                continue
            classified_rows += 1
            grouped.setdefault(label, []).append((row, classification_system))
    industries = []
    for label, items in sorted(grouped.items()):
        systems = sorted({system for _, system in items})
        industries.append(
            ETFIndustryOut(
                industry=label,
                constituent_count=len(items),
                resolved_count=sum(1 for row, _ in items if row.is_resolved),
                classification_systems=systems,
            )
        )
    return ETFIndustryCompositionOut(
        etf_symbol=instrument.symbol,
        composition_date=snapshot.composition_date.isoformat(),
        known_at=snapshot.known_at,
        provenance=snapshot.provenance,
        source_provider=snapshot.source_provider,
        completeness_status=snapshot.completeness_status,
        industries=industries,
        exclusions=sorted(set(exclusions)),
        classification_systems=sorted(classification_systems_seen),
        classification_coverage=classified_rows
        / sum(1 for row, *_ in rows if _holding_exclusion_code(row) is None)
        if any(_holding_exclusion_code(row) is None for row, *_ in rows)
        else 0,
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
    # Constituents are intentionally sourced from the same filtered taxonomy
    # contract; cash/derivative/non-equity rows stay exclusions, never members.
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
        # Controlled E2E holdings are a deliberate test-only source.  They must
        # never leak into the canonical workstation when the backend is serving
        # the free-source database, even if an older fixture snapshot is newer
        # than an issuer disclosure.  The seeded browser suite opts in through
        # the explicit setting and retains its deterministic proxy evidence.
        statement = holdings_snapshot_source_filter(statement)
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
            await db.execute(
                select(
                    ETFHolding,
                    EquityDetail.instrument_id,
                    EquityDetail.industry,
                    EquityDetail.sector,
                    EquityDetail.field_provenance,
                )
                .outerjoin(
                    EquityDetail,
                    EquityDetail.instrument_id == ETFHolding.constituent_instrument_id,
                )
                .where(ETFHolding.snapshot_id == snapshot.id)
            )
        ).all()
        classified_instrument_ids = {
            instrument_id
            for _row, instrument_id, *_ in classifications
            if instrument_id is not None
        }
        historical_profiles = await _historical_profile_payloads(
            db, classified_instrument_ids, as_of
        )
        classification_labels = [
            (
                source_classification_for_as_of(
                    industry=industry_value,
                    sector=sector_value,
                    field_provenance=field_provenance,
                    as_of=as_of,
                )[0]
                or (
                    source_classification_from_profile_snapshot(
                        historical_profiles.get(instrument_id)
                    )[0]
                    if instrument_id in historical_profiles
                    else None
                )
            )
            if _holding_exclusion_code(row) is None
            else None
            for row, instrument_id, industry_value, sector_value, field_provenance in classifications
        ]
        classified_count = sum(1 for value in classification_labels if value)
        matching_count = sum(1 for value in classification_labels if value == industry)
        for row, *_ in classifications:
            exclusion = _holding_exclusion_code(row)
            if exclusion and exclusion not in exclusions:
                exclusions.append(f"candidate_{exclusion}:{candidate}")
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
    snapshot_query = holdings_snapshot_source_filter(
        _holdings_snapshot_at(
            select(ETFHoldingsSnapshot).where(ETFHoldingsSnapshot.etf_profile_id == profile.id),
            as_of,
        )
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
    classified_rows = (
        await db.execute(
            select(
                ETFHolding,
                Instrument,
                EquityDetail.industry,
                EquityDetail.sector,
                EquityDetail.field_provenance,
            )
            .join(ETFHolding, ETFHolding.constituent_instrument_id == Instrument.id)
            # Keep eligible holdings even when the canonical profile is not
            # classified.  Dropping them with an inner join would inflate
            # classification_coverage and hide the exact exclusion that the
            # composition endpoint already discloses.
            .outerjoin(EquityDetail, EquityDetail.instrument_id == Instrument.id)
            .where(
                ETFHolding.snapshot_id == snapshot.id,
            )
            .order_by(ETFHolding.position, Instrument.symbol)
        )
    ).all()
    historical_profiles = await _historical_profile_payloads(
        db,
        {
            instrument.id
            for row, instrument, *_ in classified_rows
            if _holding_exclusion_code(row) is None
        },
        as_of,
    )
    rows: list[Instrument] = []
    systems: set[str] = set()
    eligible_rows = 0
    classified_rows_count = 0
    for row, constituent, industry_value, sector_value, field_provenance in classified_rows:
        if _holding_exclusion_code(row) is not None:
            continue
        eligible_rows += 1
        label, system = source_classification_for_as_of(
            industry=industry_value,
            sector=sector_value,
            field_provenance=field_provenance,
            as_of=as_of,
        )
        if label is None and constituent.id in historical_profiles:
            label, system = source_classification_from_profile_snapshot(
                historical_profiles[constituent.id]
            )
        if system:
            systems.add(system)
        if label:
            classified_rows_count += 1
        if label == industry:
            rows.append(constituent)
    return ETFIndustryConstituentsOut(
        etf_symbol=composition.etf_symbol,
        industry=industry,
        composition_date=composition.composition_date,
        known_at=composition.known_at,
        provenance=composition.provenance,
        source_provider=composition.source_provider,
        constituents=[InstrumentReferenceOut.model_validate(item) for item in rows],
        exclusions=composition.exclusions,
        classification_systems=sorted(systems),
        classification_coverage=classified_rows_count / eligible_rows if eligible_rows else 0,
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


@router.get("/{stable_key}/children", response_model=list[MarketGroupOut])
async def list_market_group_children(
    stable_key: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List selectable child universes without flattening them into the root.

    Benchmark-family children carry independent cap/equal/style mappings.  They
    are deliberately fetched through an explicit endpoint so the existing root
    SPY/RSP/sector workflow keeps its stable ordering and denominator semantics.
    """

    await _ensure_taxonomy_if_empty(db)
    parent = (
        await db.execute(select(MarketGroup).where(MarketGroup.stable_key == stable_key))
    ).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="Market group not found")
    statement = _groups_query().where(MarketGroup.parent_id == parent.id).order_by(MarketGroup.name)
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
