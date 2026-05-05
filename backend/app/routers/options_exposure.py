from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.user import User
from app.services.options_exposure import (
    ExpiryBreakdown,
    ExposureLadderRow,
    KeyLevels,
    get_options_exposure,
    list_exposure_expirations,
)

router = APIRouter(tags=["options-exposure"])


async def _load_underlying(symbol: str, db: AsyncSession) -> Instrument:
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")
    return inst


def _serialise_key_levels(kl: KeyLevels) -> dict:
    return {
        "call_wall": kl.call_wall,
        "put_wall": kl.put_wall,
        "gamma_flip": kl.gamma_flip,
        "max_pain": kl.max_pain,
    }


def _serialise_expiry_breakdown(b: ExpiryBreakdown) -> dict:
    return {
        "call_gex": b.call_gex,
        "put_gex": b.put_gex,
        "net_gex": b.net_gex,
        "call_dex": b.call_dex,
        "put_dex": b.put_dex,
        "net_dex": b.net_dex,
        "call_oi": b.call_oi,
        "put_oi": b.put_oi,
    }


def _serialise_ladder_row(row: ExposureLadderRow) -> dict:
    return {
        "strike": row.strike,
        "call_gex": row.call_gex,
        "put_gex": row.put_gex,
        "net_gex": row.net_gex,
        "call_dex": row.call_dex,
        "put_dex": row.put_dex,
        "net_dex": row.net_dex,
        "call_oi": row.call_oi,
        "put_oi": row.put_oi,
        "call_iv": row.call_iv,
        "put_iv": row.put_iv,
        "call_mark": row.call_mark,
        "put_mark": row.put_mark,
        "by_expiry": {k: _serialise_expiry_breakdown(v) for k, v in row.by_expiry.items()},
    }


@router.get("/instruments/{symbol:path}/options/exposure")
async def get_instrument_options_exposure(
    symbol: str,
    expiration: str | None = Query(None, description="ISO date — omit for combined"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    GEX/DEX ladder and key levels for `symbol`.

    - `expiration` absent  → combines all expirations (full chain view)
    - `expiration` present → filters to that single expiration date
    """
    underlying = await _load_underlying(symbol, db)

    exp_date = None
    if expiration:
        try:
            from datetime import date

            exp_date = date.fromisoformat(expiration)
        except ValueError as exc:
            raise HTTPException(400, f"Invalid expiration '{expiration}'") from exc

    result = await get_options_exposure(db, underlying, expiration=exp_date)

    return {
        "symbol": result.symbol,
        "spot": result.spot,
        "expirations": result.expirations,
        "active_expirations": result.active_expirations,
        "computed_at": result.computed_at,
        "ladder": [_serialise_ladder_row(r) for r in result.ladder],
        "key_levels": _serialise_key_levels(result.key_levels),
        "pcr_oi": result.pcr_oi,
        "pcr_volume": result.pcr_volume,
        "implied_move_pct": result.implied_move_pct,
        "total_gex": result.total_gex,
        "total_net_dex": result.total_net_dex,
    }


@router.get("/instruments/{symbol:path}/options/exposure/expirations")
async def get_instrument_exposure_expirations(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Expirations list with OI and GEX stats for the expiration selector."""
    underlying = await _load_underlying(symbol, db)
    summaries = await list_exposure_expirations(db, underlying)
    return [
        {
            "expiration": s.expiration,
            "dte": s.dte,
            "total_call_oi": s.total_call_oi,
            "total_put_oi": s.total_put_oi,
            "pcr_oi": s.pcr_oi,
            "total_gex": s.total_gex,
        }
        for s in summaries
    ]
