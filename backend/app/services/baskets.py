from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.basket import Basket, BasketMember, BasketSnapshot, BasketSnapshotMember
from app.models.etf_holdings import (
    ETFHolding,
    ETFHoldingsAdapterState,
    ETFHoldingsSnapshot,
    ETFProfile,
)
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.schemas.basket import (
    BasketCreateRequest,
    BasketMemberInput,
    BasketMemberOut,
    BasketOut,
    BasketSnapshotOut,
    BasketUpdateRequest,
)
from app.services.etf_holdings_capability import ETFHoldingsCapability, evaluate_capability

VALID_USER_WEIGHTING_SCHEMES = {"equal", "custom"}
WEIGHT_TOLERANCE = Decimal("0.0001")


class BasketValidationError(ValueError):
    """Raised when a user-owned basket payload is not valid."""


class BasketReadOnlyError(PermissionError):
    """Raised when a caller tries to mutate a read-only/system basket."""


class ETFHoldingsCurrentDataUnavailable(ValueError):
    """Raised when current analysis requests a non-current ETF holdings snapshot."""

    def __init__(self, capability: ETFHoldingsCapability):
        self.capability = capability
        super().__init__(capability.reason)


async def create_basket(
    db: AsyncSession,
    user_id: int,
    payload: BasketCreateRequest,
) -> Basket:
    """Create a user-owned basket with validated existing instruments."""

    name = _clean_name(payload.name)
    weighting_scheme = _normalize_user_weighting_scheme(payload.weighting_scheme)
    instruments = await _resolve_member_instruments(db, payload.members)
    _validate_members(payload.members, instruments, weighting_scheme)

    basket = Basket(
        user_id=user_id,
        name=name,
        description=_clean_optional_text(payload.description),
        source_type="manual",
        weighting_scheme=weighting_scheme,
        rebalance_frequency=_clean_optional_text(payload.rebalance_frequency),
        classification_mode=_clean_optional_text(payload.classification_mode) or "auto",
        sector=_clean_optional_text(payload.sector),
        industry=_clean_optional_text(payload.industry),
        metadata_=payload.metadata,
        is_system_managed=False,
        is_read_only=False,
    )
    db.add(basket)
    await db.flush()
    _replace_members(basket, payload.members, instruments)
    _apply_auto_classification(basket, instruments)
    await db.flush()
    await _record_basket_snapshot(
        db,
        basket,
        composition_date=datetime.now(UTC).date(),
        known_at=datetime.now(UTC),
        source_type="manual",
    )
    return await _load_basket_with_members(db, basket.id)


async def update_basket(
    db: AsyncSession,
    basket_id: int,
    user_id: int,
    payload: BasketUpdateRequest,
) -> Basket | None:
    basket = await _load_user_mutable_basket(db, basket_id, user_id)
    if basket is None:
        return None
    if basket.is_read_only or basket.is_system_managed:
        raise BasketReadOnlyError("System-managed baskets cannot be edited.")

    if payload.name is not None:
        basket.name = _clean_name(payload.name)
    if payload.description is not None:
        basket.description = _clean_optional_text(payload.description)
    if payload.rebalance_frequency is not None:
        basket.rebalance_frequency = _clean_optional_text(payload.rebalance_frequency)
    if payload.classification_mode is not None:
        basket.classification_mode = _clean_optional_text(payload.classification_mode) or "auto"
    if payload.metadata is not None:
        basket.metadata_ = payload.metadata
    if payload.weighting_scheme is not None:
        basket.weighting_scheme = _normalize_user_weighting_scheme(payload.weighting_scheme)

    instruments: list[Instrument] = []
    if payload.members is not None:
        instruments = await _resolve_member_instruments(db, payload.members)
        _validate_members(payload.members, instruments, basket.weighting_scheme)
        basket.members.clear()
        await db.flush()
        _replace_members(basket, payload.members, instruments)
    else:
        instruments = [member.instrument for member in basket.members if member.instrument]

    if (basket.classification_mode or "auto") == "auto":
        _apply_auto_classification(basket, instruments)
    else:
        if payload.sector is not None:
            basket.sector = _clean_optional_text(payload.sector)
        if payload.industry is not None:
            basket.industry = _clean_optional_text(payload.industry)

    await db.flush()
    if payload.members is not None or payload.weighting_scheme is not None:
        await _record_basket_snapshot(
            db,
            basket,
            composition_date=datetime.now(UTC).date(),
            known_at=datetime.now(UTC),
            source_type="manual",
        )
    return await _load_basket_with_members(db, basket.id)


async def delete_basket(db: AsyncSession, basket_id: int, user_id: int) -> bool:
    basket = await _load_user_mutable_basket(db, basket_id, user_id)
    if basket is None:
        return False
    if basket.is_read_only or basket.is_system_managed:
        raise BasketReadOnlyError("System-managed baskets cannot be deleted.")
    await db.delete(basket)
    await db.flush()
    return True


async def materialize_etf_holdings_basket(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    snapshot_id: int | None = None,
    snapshot_date: date | None = None,
    allow_non_current: bool = False,
) -> Basket | None:
    """Create/update a basket, requiring current capability unless historical is explicit."""

    snapshot, etf_instrument = await _load_etf_snapshot(
        db,
        symbol_or_id,
        snapshot_id=snapshot_id,
        snapshot_date=snapshot_date,
    )
    if snapshot is None or etf_instrument is None:
        return None

    if not allow_non_current and snapshot_id is None and snapshot_date is None:
        state = (
            await db.execute(
                select(ETFHoldingsAdapterState)
                .where(ETFHoldingsAdapterState.etf_profile_id == snapshot.etf_profile_id)
                .order_by(
                    ETFHoldingsAdapterState.last_checked_at.desc().nullslast(),
                    ETFHoldingsAdapterState.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        profile = await db.get(ETFProfile, snapshot.etf_profile_id)
        if profile is not None:
            capability = evaluate_capability(profile, snapshot, state)
            if not capability.usable_for_current_analysis:
                raise ETFHoldingsCurrentDataUnavailable(capability)

    existing = (
        await db.execute(
            select(Basket)
            .options(
                selectinload(Basket.members).selectinload(BasketMember.instrument),
                selectinload(Basket.snapshots),
            )
            .where(Basket.source_snapshot_id == snapshot.id)
        )
    ).scalar_one_or_none()

    basket = existing or Basket(
        source_type="etf_holdings",
        source_etf_profile_id=snapshot.etf_profile_id,
        source_snapshot_id=snapshot.id,
        is_system_managed=True,
        is_read_only=True,
    )
    basket.name = f"{etf_instrument.symbol} holdings {snapshot.composition_date.isoformat()}"
    basket.description = (
        f"System-managed basket materialized from {etf_instrument.symbol} ETF holdings."
    )
    basket.weighting_scheme = "source_weight"
    basket.composition_date = snapshot.composition_date
    basket.metadata_ = {
        "etf_symbol": etf_instrument.symbol,
        "etf_name": etf_instrument.name,
        "snapshot_id": snapshot.id,
        "provenance": snapshot.provenance,
        "source_provider": snapshot.source_provider,
        "source_quality": snapshot.source_quality,
        "completeness_status": snapshot.completeness_status,
        "resolved_count": snapshot.resolved_count,
        "unresolved_count": snapshot.unresolved_count,
    }
    if existing is None:
        db.add(basket)
        await db.flush()

    basket.members.clear()
    await db.flush()
    seen_instruments: set[int] = set()
    position = 0
    for row in snapshot.rows:
        if row.row_type != "security" or row.constituent_instrument_id is None:
            continue
        if row.constituent_instrument_id in seen_instruments:
            continue
        seen_instruments.add(row.constituent_instrument_id)
        basket.members.append(
            BasketMember(
                instrument_id=row.constituent_instrument_id,
                source_holding_id=row.id,
                position=position,
                weight=row.weight,
                label=row.reported_symbol or row.reported_name,
                metadata_={
                    "reported_symbol": row.reported_symbol,
                    "reported_name": row.reported_name,
                    "holding_type": row.holding_type,
                    "currency": row.currency,
                    "market_value": str(row.market_value) if row.market_value is not None else None,
                    "shares": str(row.shares) if row.shares is not None else None,
                },
            )
        )
        position += 1

    await db.flush()
    await _record_basket_snapshot(
        db,
        basket,
        composition_date=snapshot.composition_date,
        known_at=snapshot.known_at,
        source_type="etf_holdings",
        source_snapshot_id=snapshot.id,
    )
    return await _load_basket_with_members(db, basket.id)


async def get_basket(db: AsyncSession, basket_id: int, user_id: int) -> Basket | None:
    return (
        await db.execute(
            select(Basket)
            .options(selectinload(Basket.members).selectinload(BasketMember.instrument))
            .where(
                Basket.id == basket_id,
                (Basket.user_id == user_id) | (Basket.is_system_managed.is_(True)),
            )
        )
    ).scalar_one_or_none()


async def get_basket_synthetic_ohlcv(
    db: AsyncSession,
    basket_id: int,
    user_id: int,
    timeframe: Timeframe,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    adjusted: bool = True,
) -> list[dict]:
    """Return a rebased-to-100 synthetic OHLCV series for a basket.

    The first viable aligned bar is 100. Subsequent values are the weighted
    sum of each member's cumulative return from its own starting close.
    """

    basket = await get_basket(db, basket_id, user_id)
    if basket is None:
        raise BasketValidationError("Basket not found.")
    if not basket.members:
        return []

    member_weights = _normalized_member_weights(basket.members)
    member_ids = list(member_weights)
    stmt = (
        select(OHLCVBar)
        .where(
            OHLCVBar.instrument_id.in_(member_ids),
            OHLCVBar.timeframe == timeframe,
            OHLCVBar.is_adjusted.is_(adjusted),
        )
        .order_by(OHLCVBar.ts.asc(), OHLCVBar.instrument_id.asc())
    )
    if start is not None:
        stmt = stmt.where(OHLCVBar.ts >= start)
    if end is not None:
        stmt = stmt.where(OHLCVBar.ts <= end)

    bars = list((await db.execute(stmt)).scalars().all())
    by_member: dict[int, dict[datetime, OHLCVBar]] = {member_id: {} for member_id in member_ids}
    for bar in bars:
        by_member.setdefault(bar.instrument_id, {})[bar.ts] = bar

    common_times: set[datetime] | None = None
    for member_id in member_ids:
        times = set(by_member.get(member_id, {}))
        common_times = times if common_times is None else common_times & times
    timestamps = sorted(common_times or set())
    if limit is not None:
        timestamps = timestamps[-limit:]
    if not timestamps:
        return []

    first_ts = timestamps[0]
    bases: dict[int, Decimal] = {}
    for member_id in member_ids:
        base = by_member[member_id][first_ts].close
        if base <= 0:
            return []
        bases[member_id] = base

    output: list[dict] = []
    for ts in timestamps:
        row = {
            "ts": ts,
            "open": Decimal("0"),
            "high": Decimal("0"),
            "low": Decimal("0"),
            "close": Decimal("0"),
            "volume": Decimal("0"),
            "vwap": None,
            "is_adjusted": adjusted,
        }
        has_volume = False
        for member_id, weight in member_weights.items():
            bar = by_member[member_id][ts]
            base = bases[member_id]
            row["open"] += _rebase_price(bar.open, base, weight)
            row["high"] += _rebase_price(bar.high, base, weight)
            row["low"] += _rebase_price(bar.low, base, weight)
            row["close"] += _rebase_price(bar.close, base, weight)
            if bar.volume is not None:
                row["volume"] += bar.volume
                has_volume = True
        if not has_volume:
            row["volume"] = None
        output.append(row)
    return output


async def _load_user_mutable_basket(
    db: AsyncSession,
    basket_id: int,
    user_id: int,
) -> Basket | None:
    return (
        await db.execute(
            select(Basket)
            .options(
                selectinload(Basket.members)
                .selectinload(BasketMember.instrument)
                .selectinload(Instrument.equity_detail)
            )
            .where(Basket.id == basket_id, Basket.user_id == user_id)
        )
    ).scalar_one_or_none()


async def _load_basket_with_members(db: AsyncSession, basket_id: int) -> Basket:
    return (
        await db.execute(
            select(Basket)
            .options(
                selectinload(Basket.members)
                .selectinload(BasketMember.instrument)
                .selectinload(Instrument.equity_detail),
                selectinload(Basket.snapshots),
            )
            .where(Basket.id == basket_id)
        )
    ).scalar_one()


async def list_baskets(db: AsyncSession, user_id: int) -> list[Basket]:
    return list(
        (
            await db.execute(
                select(Basket)
                .options(
                    selectinload(Basket.members)
                    .selectinload(BasketMember.instrument)
                    .selectinload(Instrument.equity_detail),
                    selectinload(Basket.snapshots),
                )
                .where((Basket.user_id == user_id) | (Basket.is_system_managed.is_(True)))
                .order_by(Basket.updated_at.desc(), Basket.id.desc())
            )
        )
        .scalars()
        .all()
    )


def basket_to_out(basket: Basket) -> BasketOut:
    snapshots = list(getattr(basket, "snapshots", []) or [])
    latest_snapshot_date = max(
        (snapshot.composition_date for snapshot in snapshots),
        default=None,
    )
    return BasketOut(
        id=basket.id,
        user_id=basket.user_id,
        name=basket.name,
        description=basket.description,
        source_type=basket.source_type,
        weighting_scheme=basket.weighting_scheme,
        rebalance_frequency=basket.rebalance_frequency,
        classification_mode=basket.classification_mode,
        sector=basket.sector,
        industry=basket.industry,
        source_etf_profile_id=basket.source_etf_profile_id,
        source_snapshot_id=basket.source_snapshot_id,
        composition_date=basket.composition_date,
        snapshot_count=len(snapshots),
        latest_snapshot_date=latest_snapshot_date,
        is_system_managed=basket.is_system_managed,
        is_read_only=basket.is_read_only,
        metadata=basket.metadata_,
        members=[
            BasketMemberOut(
                id=member.id,
                instrument_id=member.instrument_id,
                symbol=member.instrument.symbol if member.instrument else None,
                name=member.instrument.name if member.instrument else None,
                source_holding_id=member.source_holding_id,
                position=member.position,
                weight=member.weight,
                label=member.label,
                notes=member.notes,
                metadata=member.metadata_,
                created_at=member.created_at,
                updated_at=member.updated_at,
            )
            for member in basket.members
        ],
        created_at=basket.created_at,
        updated_at=basket.updated_at,
    )


async def list_basket_snapshots(
    db: AsyncSession, basket_id: int, user_id: int
) -> list[BasketSnapshot]:
    basket = await get_basket(db, basket_id, user_id)
    if basket is None:
        raise BasketValidationError("Basket not found.")
    return list(
        (
            await db.execute(
                select(BasketSnapshot)
                .where(BasketSnapshot.basket_id == basket.id)
                .order_by(BasketSnapshot.composition_date.desc(), BasketSnapshot.id.desc())
            )
        )
        .scalars()
        .all()
    )


def basket_snapshot_to_out(snapshot: BasketSnapshot) -> BasketSnapshotOut:
    return BasketSnapshotOut(
        id=snapshot.id,
        basket_id=snapshot.basket_id,
        composition_date=snapshot.composition_date,
        known_at=snapshot.known_at,
        source_type=snapshot.source_type,
        source_snapshot_id=snapshot.source_snapshot_id,
        member_count=snapshot.member_count,
        metadata=snapshot.metadata_,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


async def _record_basket_snapshot(
    db: AsyncSession,
    basket: Basket,
    *,
    composition_date: date,
    known_at: datetime | None,
    source_type: str,
    source_snapshot_id: int | None = None,
) -> BasketSnapshot:
    existing = None
    if source_snapshot_id is not None:
        existing = (
            await db.execute(
                select(BasketSnapshot)
                .options(selectinload(BasketSnapshot.members))
                .where(
                    BasketSnapshot.basket_id == basket.id,
                    BasketSnapshot.source_snapshot_id == source_snapshot_id,
                )
            )
        ).scalar_one_or_none()
    snapshot = existing or BasketSnapshot(
        basket_id=basket.id,
        composition_date=composition_date,
        source_type=source_type,
    )
    snapshot.known_at = known_at
    snapshot.source_snapshot_id = source_snapshot_id
    snapshot.member_count = len(basket.members)
    snapshot.metadata_ = {
        "basket_name": basket.name,
        "basket_source_type": basket.source_type,
        "weighting_scheme": basket.weighting_scheme,
        "source_etf_profile_id": basket.source_etf_profile_id,
    }
    if existing is None:
        db.add(snapshot)
        await db.flush()
    snapshot.members.clear()
    await db.flush()
    for member in basket.members:
        snapshot.members.append(
            BasketSnapshotMember(
                instrument_id=member.instrument_id,
                source_holding_id=member.source_holding_id,
                position=member.position,
                weight=member.weight,
                label=member.label,
                metadata_=member.metadata_,
            )
        )
    await db.flush()
    return snapshot


def _normalized_member_weights(members: list[BasketMember]) -> dict[int, Decimal]:
    weighted: dict[int, Decimal] = {}
    explicit_weights = [member.weight for member in members if member.weight is not None]
    if len(explicit_weights) == len(members) and explicit_weights:
        total = sum(explicit_weights, Decimal("0"))
        if total > 0:
            for member in members:
                weighted[member.instrument_id] = Decimal(member.weight or 0) / total
            return weighted

    equal = Decimal("1") / Decimal(len(members))
    for member in members:
        weighted[member.instrument_id] = equal
    return weighted


def _rebase_price(value: Decimal, base: Decimal, weight: Decimal) -> Decimal:
    return (Decimal(value) / base) * Decimal("100") * weight


async def _resolve_member_instruments(
    db: AsyncSession,
    members: list[BasketMemberInput],
) -> list[Instrument]:
    if not members:
        return []
    instrument_ids = [
        member.instrument_id for member in members if member.instrument_id is not None
    ]
    symbols = [str(member.symbol).strip().upper() for member in members if member.symbol]
    stmt = select(Instrument).options(selectinload(Instrument.equity_detail))
    clauses = []
    if instrument_ids:
        clauses.append(Instrument.id.in_(instrument_ids))
    if symbols:
        clauses.append(func.upper(Instrument.symbol).in_(symbols))
    if not clauses:
        return []
    stmt = stmt.where(clauses[0] if len(clauses) == 1 else clauses[0] | clauses[1])
    instruments = list((await db.execute(stmt)).scalars().all())
    by_id = {instrument.id: instrument for instrument in instruments}
    by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
    ordered: list[Instrument] = []
    missing: list[str] = []
    seen_ids: set[int] = set()
    for member in members:
        instrument = None
        if member.instrument_id is not None:
            instrument = by_id.get(member.instrument_id)
        if instrument is None and member.symbol:
            instrument = by_symbol.get(member.symbol.strip().upper())
        if instrument is None:
            missing.append(str(member.instrument_id or member.symbol))
            continue
        if instrument.id in seen_ids:
            raise BasketValidationError(
                f"Basket contains duplicate instrument {instrument.symbol}."
            )
        seen_ids.add(instrument.id)
        ordered.append(instrument)
    if missing:
        raise BasketValidationError(
            f"Basket contains unknown instruments: {', '.join(missing[:10])}."
        )
    return ordered


def _validate_members(
    members: list[BasketMemberInput],
    instruments: list[Instrument],
    weighting_scheme: str,
) -> None:
    if len(members) != len(instruments):
        raise BasketValidationError("Basket member resolution failed.")
    if not members:
        raise BasketValidationError("A basket needs at least one instrument.")
    if weighting_scheme == "custom":
        missing = [
            instrument.symbol
            for member, instrument in zip(members, instruments)
            if member.weight is None
        ]
        if missing:
            raise BasketValidationError(
                f"Custom-weight baskets need weights for every member: {', '.join(missing[:10])}."
            )
        total = sum((member.weight or Decimal("0")) for member in members)
        if abs(total - Decimal("1")) > WEIGHT_TOLERANCE:
            raise BasketValidationError("Custom basket weights must sum to 1.0.")


def _replace_members(
    basket: Basket,
    members: list[BasketMemberInput],
    instruments: list[Instrument],
) -> None:
    for position, (member, instrument) in enumerate(zip(members, instruments)):
        basket.members.append(
            BasketMember(
                instrument_id=instrument.id,
                position=position,
                weight=member.weight if basket.weighting_scheme == "custom" else None,
                label=_clean_optional_text(member.label),
                notes=_clean_optional_text(member.notes),
                metadata_=member.metadata,
            )
        )


def _apply_auto_classification(basket: Basket, instruments: list[Instrument]) -> None:
    if (basket.classification_mode or "auto") != "auto":
        return
    sectors = {
        instrument.equity_detail.sector
        for instrument in instruments
        if instrument.equity_detail is not None and instrument.equity_detail.sector
    }
    industries = {
        instrument.equity_detail.industry
        for instrument in instruments
        if instrument.equity_detail is not None and instrument.equity_detail.industry
    }
    basket.sector = next(iter(sectors)) if len(sectors) == 1 else None
    basket.industry = next(iter(industries)) if len(industries) == 1 else None


def _normalize_user_weighting_scheme(value: str) -> str:
    normalized = (value or "equal").strip().lower()
    if normalized not in VALID_USER_WEIGHTING_SCHEMES:
        raise BasketValidationError("Basket weighting_scheme must be 'equal' or 'custom'.")
    return normalized


def _clean_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise BasketValidationError("Basket name is required.")
    return name


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


async def _load_etf_snapshot(
    db: AsyncSession,
    symbol_or_id: str | int,
    *,
    snapshot_id: int | None = None,
    snapshot_date: date | None = None,
) -> tuple[ETFHoldingsSnapshot | None, Instrument | None]:
    instrument = await _load_instrument_by_symbol_or_id(db, symbol_or_id)
    if instrument is None:
        return None, None
    profile = (
        await db.execute(
            select(ETFProfile).where(ETFProfile.instrument_id == instrument.id).limit(1)
        )
    ).scalar_one_or_none()
    if profile is None:
        return None, None
    stmt = (
        select(ETFHoldingsSnapshot)
        .options(
            selectinload(ETFHoldingsSnapshot.rows).selectinload(ETFHolding.constituent_instrument)
        )
        .where(ETFHoldingsSnapshot.etf_profile_id == profile.id)
    )
    if snapshot_id is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.id == snapshot_id)
    elif snapshot_date is not None:
        stmt = stmt.where(ETFHoldingsSnapshot.composition_date <= snapshot_date)
    snapshot = (
        await db.execute(
            stmt.order_by(
                ETFHoldingsSnapshot.composition_date.desc(),
                ETFHoldingsSnapshot.id.desc(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return snapshot, instrument


async def _load_instrument_by_symbol_or_id(
    db: AsyncSession,
    symbol_or_id: str | int,
) -> Instrument | None:
    if isinstance(symbol_or_id, int) or str(symbol_or_id).isdigit():
        return await db.get(Instrument, int(symbol_or_id))
    symbol = str(symbol_or_id).strip().upper()
    return (
        await db.execute(select(Instrument).where(func.upper(Instrument.symbol) == symbol).limit(1))
    ).scalar_one_or_none()
