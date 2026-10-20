"""
Options exposure analytics service.

Computes GEX (Gamma Exposure), DEX (Delta Exposure), call/put walls,
gamma flip level, max pain, implied move, and put/call ratios from the
persisted OptionQuotePoint time-series.

GEX sign convention (SqueezeMetrics / dealer-centric):
  call_gex = +(gamma × OI × contract_size × spot²)   [positive → dealers long]
  put_gex  = -(gamma × OI × contract_size × spot²)   [negative → dealers short]
  net_gex  = call_gex + put_gex  (>0 = long gamma regime, suppresses vol)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lib.quantlib_greeks import calculate_greeks
from app.models.instrument import Instrument, OptionDetail, OptionRight
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import OptionQuotePoint
from app.services.options_data import list_option_expirations, sync_option_chain_snapshot
from app.services.risk_free_rate import get_risk_free_rate

# ── Internal raw record ───────────────────────────────────────────────────────


@dataclass
class _ContractQuote:
    strike: Decimal
    right: OptionRight
    expiry_date: date
    contract_size: Decimal
    gamma: Decimal | None
    delta: Decimal | None
    open_interest: Decimal | None
    volume: Decimal | None
    implied_vol: Decimal | None
    mark: Decimal | None
    bid: Decimal | None
    ask: Decimal | None


# ── Public result types ───────────────────────────────────────────────────────


@dataclass
class ExpiryBreakdown:
    call_gex: float
    put_gex: float
    net_gex: float
    call_dex: float
    put_dex: float
    net_dex: float
    call_oi: float
    put_oi: float


@dataclass
class ExposureLadderRow:
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_dex: float
    put_dex: float
    net_dex: float
    call_oi: float
    put_oi: float
    call_iv: float | None
    put_iv: float | None
    call_mark: float | None
    put_mark: float | None
    by_expiry: dict[str, ExpiryBreakdown] = dc_field(default_factory=dict)


@dataclass
class KeyLevels:
    call_wall: float | None = None
    put_wall: float | None = None
    gamma_flip: float | None = None
    max_pain: float | None = None


@dataclass
class ExpirationSummary:
    expiration: str
    dte: int
    total_call_oi: float
    total_put_oi: float
    pcr_oi: float | None
    total_gex: float


@dataclass
class OptionsExposureResponse:
    symbol: str
    spot: float | None
    expirations: list[str]
    active_expirations: list[str]
    computed_at: str
    ladder: list[ExposureLadderRow]
    key_levels: KeyLevels
    pcr_oi: float | None
    pcr_volume: float | None
    implied_move_pct: float | None
    total_gex: float
    total_net_dex: float
    greeks_estimated: bool = False


# ── DB helpers ────────────────────────────────────────────────────────────────


async def _fetch_latest_contract_quotes(
    db: AsyncSession,
    underlying_id: int,
    expiration: date | None = None,
) -> list[_ContractQuote]:
    """
    For each option contract of `underlying_id`, return the row with the most
    recent observed_at from OptionQuotePoint.
    """
    latest_sq = (
        select(
            OptionQuotePoint.option_instrument_id,
            func.max(OptionQuotePoint.observed_at).label("max_obs"),
        )
        .join(OptionDetail, OptionDetail.instrument_id == OptionQuotePoint.option_instrument_id)
        .where(OptionDetail.underlying_instrument_id == underlying_id)
        .group_by(OptionQuotePoint.option_instrument_id)
        .subquery()
    )

    stmt = (
        select(
            OptionDetail.strike,
            OptionDetail.right,
            OptionDetail.expiry_date,
            OptionDetail.contract_size,
            OptionQuotePoint.gamma,
            OptionQuotePoint.delta,
            OptionQuotePoint.open_interest,
            OptionQuotePoint.volume,
            OptionQuotePoint.implied_vol,
            OptionQuotePoint.mark,
            OptionQuotePoint.bid,
            OptionQuotePoint.ask,
        )
        .join(
            latest_sq,
            (OptionQuotePoint.option_instrument_id == latest_sq.c.option_instrument_id)
            & (OptionQuotePoint.observed_at == latest_sq.c.max_obs),
        )
        .join(OptionDetail, OptionDetail.instrument_id == OptionQuotePoint.option_instrument_id)
        .where(OptionDetail.underlying_instrument_id == underlying_id)
    )

    if expiration is not None:
        stmt = stmt.where(OptionDetail.expiry_date == expiration)

    rows = (await db.execute(stmt)).all()
    return [
        _ContractQuote(
            strike=row.strike,
            right=row.right,
            expiry_date=row.expiry_date,
            contract_size=row.contract_size or Decimal("100"),
            gamma=row.gamma,
            delta=row.delta,
            open_interest=row.open_interest,
            volume=row.volume,
            implied_vol=row.implied_vol,
            mark=row.mark,
            bid=row.bid,
            ask=row.ask,
        )
        for row in rows
    ]


async def _get_spot_price(db: AsyncSession, underlying_id: int) -> float | None:
    result = await db.execute(
        select(OHLCVBar.close)
        .where(
            OHLCVBar.instrument_id == underlying_id,
            OHLCVBar.timeframe == Timeframe.D1,
        )
        .order_by(OHLCVBar.ts.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None


async def _ensure_option_quotes_available(
    db: AsyncSession,
    underlying: Instrument,
    expiration: date | None = None,
) -> None:
    expirations = await list_option_expirations(db, underlying)
    if not expirations:
        return

    provider_expirations = set(expirations)
    cached_quotes = await _fetch_latest_contract_quotes(db, underlying.id)
    cached_expirations = {quote.expiry_date for quote in cached_quotes}

    target_expirations = [expiration] if expiration is not None else list(provider_expirations)
    for item in target_expirations:
        if item is None:
            continue
        if item not in provider_expirations:
            continue
        if item in cached_expirations:
            continue
        await sync_option_chain_snapshot(db, underlying, expiration=item)


# ── Computation ───────────────────────────────────────────────────────────────


def _compute_exposure(
    quotes: list[_ContractQuote],
    spot: float,
    rfr: float = 0.05,
) -> tuple[
    list[ExposureLadderRow],
    KeyLevels,
    float,  # total_gex
    float,  # total_net_dex
    float | None,  # pcr_oi
    float | None,  # pcr_volume
    float | None,  # implied_move_pct
    list[str],  # sorted expirations
    bool,  # any_estimated — True if BS fallback was used for any contract
]:
    spot_sq = spot * spot
    today = date.today()
    any_estimated = False

    # Accumulate per-(strike, expiry) for segment coloring
    by_se: dict[tuple[float, str], dict] = defaultdict(
        lambda: {
            "call_gex": 0.0,
            "put_gex": 0.0,
            "call_dex": 0.0,
            "put_dex": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
        }
    )

    # Accumulate per-strike for the main row values
    by_s: dict[float, dict] = defaultdict(
        lambda: {
            "call_gex": 0.0,
            "put_gex": 0.0,
            "call_dex": 0.0,
            "put_dex": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
            "call_iv_sum": 0.0,
            "call_iv_n": 0,
            "put_iv_sum": 0.0,
            "put_iv_n": 0,
            "call_mark": None,
            "put_mark": None,
        }
    )

    total_call_oi = 0.0
    total_put_oi = 0.0
    total_call_vol = 0.0
    total_put_vol = 0.0
    all_expirations: set[str] = set()

    for q in quotes:
        strike_f = float(q.strike)
        expiry_s = q.expiry_date.isoformat()
        cs = float(q.contract_size)
        oi_f = float(q.open_interest) if q.open_interest is not None else 0.0
        vol_f = float(q.volume) if q.volume is not None else 0.0
        iv_f = float(q.implied_vol) if q.implied_vol is not None else None
        mark_f = float(q.mark) if q.mark is not None else None

        gamma_f = float(q.gamma) if q.gamma is not None else 0.0
        delta_f = float(q.delta) if q.delta is not None else 0.0

        # Backward-compat: estimate missing greeks for rows persisted before ingestion-time estimation
        if (q.gamma is None or q.delta is None) and iv_f is not None and spot > 0:
            tte = max(0.0, (q.expiry_date - today).days / 365.25)
            if tte > 0:
                is_call = q.right == OptionRight.CALL
                estimated = calculate_greeks(
                    spot=spot,
                    strike=strike_f,
                    expiry=q.expiry_date,
                    implied_vol=iv_f,
                    risk_free_rate=rfr,
                    is_call=is_call,
                    valuation_date=today,
                )
                est_delta = float(estimated["delta"])
                est_gamma = float(estimated["gamma"])
                if q.gamma is None:
                    gamma_f = est_gamma
                if q.delta is None:
                    delta_f = est_delta
                any_estimated = True

        all_expirations.add(expiry_s)
        se_key = (strike_f, expiry_s)
        bs = by_s[strike_f]
        bse = by_se[se_key]

        base_gex = gamma_f * oi_f * cs * spot_sq
        base_dex = abs(delta_f) * oi_f * cs

        if q.right == OptionRight.CALL:
            gex, dex = base_gex, base_dex
            bs["call_gex"] += gex
            bse["call_gex"] += gex
            bs["call_dex"] += dex
            bse["call_dex"] += dex
            bs["call_oi"] += oi_f
            bse["call_oi"] += oi_f
            if iv_f is not None:
                bs["call_iv_sum"] += iv_f
                bs["call_iv_n"] += 1
            if mark_f is not None:
                bs["call_mark"] = mark_f
            total_call_oi += oi_f
            total_call_vol += vol_f
        else:
            gex, dex = -base_gex, -base_dex
            bs["put_gex"] += gex
            bse["put_gex"] += gex
            bs["put_dex"] += dex
            bse["put_dex"] += dex
            bs["put_oi"] += oi_f
            bse["put_oi"] += oi_f
            if iv_f is not None:
                bs["put_iv_sum"] += iv_f
                bs["put_iv_n"] += 1
            if mark_f is not None:
                bs["put_mark"] = mark_f
            total_put_oi += oi_f
            total_put_vol += vol_f

    # Build sorted ladder
    ladder: list[ExposureLadderRow] = []
    for strike_f in sorted(by_s.keys()):
        bs = by_s[strike_f]
        net_gex = bs["call_gex"] + bs["put_gex"]
        net_dex = bs["call_dex"] + bs["put_dex"]

        expiry_breakdowns: dict[str, ExpiryBreakdown] = {}
        for expiry_s in all_expirations:
            bse = by_se.get((strike_f, expiry_s))
            if bse:
                expiry_breakdowns[expiry_s] = ExpiryBreakdown(
                    call_gex=bse["call_gex"],
                    put_gex=bse["put_gex"],
                    net_gex=bse["call_gex"] + bse["put_gex"],
                    call_dex=bse["call_dex"],
                    put_dex=bse["put_dex"],
                    net_dex=bse["call_dex"] + bse["put_dex"],
                    call_oi=bse["call_oi"],
                    put_oi=bse["put_oi"],
                )

        ladder.append(
            ExposureLadderRow(
                strike=strike_f,
                call_gex=bs["call_gex"],
                put_gex=bs["put_gex"],
                net_gex=net_gex,
                call_dex=bs["call_dex"],
                put_dex=bs["put_dex"],
                net_dex=net_dex,
                call_oi=bs["call_oi"],
                put_oi=bs["put_oi"],
                call_iv=bs["call_iv_sum"] / bs["call_iv_n"] if bs["call_iv_n"] else None,
                put_iv=bs["put_iv_sum"] / bs["put_iv_n"] if bs["put_iv_n"] else None,
                call_mark=bs["call_mark"],
                put_mark=bs["put_mark"],
                by_expiry=expiry_breakdowns,
            )
        )

    key_levels = _compute_key_levels(ladder, quotes)
    total_gex = sum(r.net_gex for r in ladder)
    total_net_dex = sum(r.net_dex for r in ladder)

    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
    pcr_volume = total_put_vol / total_call_vol if total_call_vol > 0 else None
    implied_move_pct = _compute_implied_move(ladder, spot)

    return (
        ladder,
        key_levels,
        total_gex,
        total_net_dex,
        pcr_oi,
        pcr_volume,
        implied_move_pct,
        sorted(all_expirations),
        any_estimated,
    )


def _compute_key_levels(
    ladder: list[ExposureLadderRow],
    quotes: list[_ContractQuote],
) -> KeyLevels:
    if not ladder:
        return KeyLevels()

    call_wall_row = max(ladder, key=lambda r: r.call_oi)
    put_wall_row = max(ladder, key=lambda r: r.put_oi)

    return KeyLevels(
        call_wall=call_wall_row.strike if call_wall_row.call_oi > 0 else None,
        put_wall=put_wall_row.strike if put_wall_row.put_oi > 0 else None,
        gamma_flip=_find_gamma_flip(ladder),
        max_pain=_find_max_pain(quotes),
    )


def _find_gamma_flip(ladder: list[ExposureLadderRow]) -> float | None:
    """Interpolated zero-crossing of net_gex across ascending strikes."""
    for i in range(1, len(ladder)):
        prev, curr = ladder[i - 1], ladder[i]
        if prev.net_gex * curr.net_gex < 0:
            span = curr.strike - prev.strike
            if span == 0:
                return prev.strike
            frac = abs(prev.net_gex) / (abs(prev.net_gex) + abs(curr.net_gex))
            return round(prev.strike + frac * span, 2)
    return None


def _find_max_pain(quotes: list[_ContractQuote]) -> float | None:
    """Strike that minimises total intrinsic value remaining for option holders."""
    strikes = sorted({float(q.strike) for q in quotes})
    if not strikes:
        return None

    min_value = float("inf")
    max_pain_strike = strikes[0]

    for test_k in strikes:
        total = 0.0
        for q in quotes:
            oi = float(q.open_interest or 0)
            cs = float(q.contract_size)
            s = float(q.strike)
            if q.right == OptionRight.CALL:
                total += max(0.0, test_k - s) * oi * cs
            else:
                total += max(0.0, s - test_k) * oi * cs
        if total < min_value:
            min_value = total
            max_pain_strike = test_k

    return max_pain_strike


def _compute_implied_move(ladder: list[ExposureLadderRow], spot: float) -> float | None:
    if not ladder or spot <= 0:
        return None
    atm = min(ladder, key=lambda r: abs(r.strike - spot))
    if atm.call_mark is None or atm.put_mark is None:
        return None
    return (atm.call_mark + atm.put_mark) / spot


# ── Public API ────────────────────────────────────────────────────────────────


async def get_options_exposure(
    db: AsyncSession,
    underlying: Instrument,
    expiration: date | None = None,
) -> OptionsExposureResponse:
    """
    Full GEX/DEX ladder for `underlying`.
    `expiration=None` combines all expirations; otherwise filtered to one date.
    """
    await _ensure_option_quotes_available(db, underlying, expiration=expiration)
    quotes = await _fetch_latest_contract_quotes(db, underlying.id, expiration=expiration)
    spot = await _get_spot_price(db, underlying.id)
    provider_expirations = [
        item.isoformat() for item in await list_option_expirations(db, underlying)
    ]

    if not quotes:
        return OptionsExposureResponse(
            symbol=underlying.symbol,
            spot=spot,
            expirations=provider_expirations,
            active_expirations=[] if expiration is None else [expiration.isoformat()],
            computed_at=datetime.now(UTC).isoformat(),
            ladder=[],
            key_levels=KeyLevels(),
            pcr_oi=None,
            pcr_volume=None,
            implied_move_pct=None,
            total_gex=0.0,
            total_net_dex=0.0,
        )

    rfr = await get_risk_free_rate(db)
    spot_val = spot or 0.0
    (
        ladder,
        key_levels,
        total_gex,
        total_net_dex,
        pcr_oi,
        pcr_vol,
        implied_move,
        sorted_exps,
        any_estimated,
    ) = _compute_exposure(quotes, spot_val, rfr=rfr)

    active_expirations = [exp for exp in sorted_exps if exp in provider_expirations]

    return OptionsExposureResponse(
        symbol=underlying.symbol,
        spot=spot,
        expirations=provider_expirations,
        active_expirations=active_expirations,
        computed_at=datetime.now(UTC).isoformat(),
        ladder=ladder,
        key_levels=key_levels,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_vol,
        implied_move_pct=implied_move,
        total_gex=total_gex,
        total_net_dex=total_net_dex,
        greeks_estimated=any_estimated,
    )


async def list_exposure_expirations(
    db: AsyncSession,
    underlying: Instrument,
) -> list[ExpirationSummary]:
    """Expirations list with GEX/OI stats — used to populate the expiration selector."""
    await _ensure_option_quotes_available(db, underlying)
    provider_expirations = {
        item.isoformat() for item in await list_option_expirations(db, underlying)
    }
    quotes = await _fetch_latest_contract_quotes(db, underlying.id)
    spot = await _get_spot_price(db, underlying.id)
    spot_sq = (spot or 0.0) ** 2

    today = date.today()
    by_expiry: dict[str, dict] = defaultdict(
        lambda: {
            "call_gex": 0.0,
            "put_gex": 0.0,
            "call_oi": 0.0,
            "put_oi": 0.0,
        }
    )

    for q in quotes:
        expiry_s = q.expiry_date.isoformat()
        gamma_f = float(q.gamma) if q.gamma is not None else 0.0
        oi_f = float(q.open_interest) if q.open_interest is not None else 0.0
        cs = float(q.contract_size)
        base_gex = gamma_f * oi_f * cs * spot_sq
        v = by_expiry[expiry_s]
        if q.right == OptionRight.CALL:
            v["call_gex"] += base_gex
            v["call_oi"] += oi_f
        else:
            v["put_gex"] -= base_gex
            v["put_oi"] += oi_f

    summaries: list[ExpirationSummary] = []
    for expiry_s in sorted(by_expiry.keys()):
        if provider_expirations and expiry_s not in provider_expirations:
            continue
        v = by_expiry[expiry_s]
        expiry_d = date.fromisoformat(expiry_s)
        call_oi = v["call_oi"]
        put_oi = v["put_oi"]
        summaries.append(
            ExpirationSummary(
                expiration=expiry_s,
                dte=max(0, (expiry_d - today).days),
                total_call_oi=call_oi,
                total_put_oi=put_oi,
                pcr_oi=put_oi / call_oi if call_oi > 0 else None,
                total_gex=v["call_gex"] + v["put_gex"],
            )
        )

    return summaries
