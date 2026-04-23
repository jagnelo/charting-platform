from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.user import User
from app.services.options_data import (
    get_option_chain_rows,
    get_option_contract_summary,
    get_option_quote_history,
    list_option_expirations,
)

router = APIRouter(tags=["options"])


async def _load_instrument(symbol: str, db: AsyncSession) -> Instrument | None:
    result = await db.execute(
        select(Instrument)
        .options(selectinload(Instrument.option_detail))
        .where(Instrument.symbol == symbol.upper())
    )
    return result.scalar_one_or_none()


@router.get("/instruments/{symbol:path}/options/expirations")
async def get_instrument_option_expirations(
    symbol: str,
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    instrument = await _load_instrument(symbol, db)
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")
    expirations = await list_option_expirations(db, instrument, refresh=refresh)
    return {"symbol": instrument.symbol, "expirations": expirations}


@router.get("/instruments/{symbol:path}/options/chain")
async def get_instrument_option_chain(
    symbol: str,
    expiration: str | None = Query(None),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    instrument = await _load_instrument(symbol, db)
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")

    expirations = await list_option_expirations(db, instrument, refresh=refresh)
    if not expirations:
        return {"symbol": instrument.symbol, "expiration": None, "snapshot": None, "rows": []}

    target_expiration = expirations[0]
    if expiration:
        try:
            target_expiration = datetime.fromisoformat(expiration).date()
        except ValueError as exc:
            raise HTTPException(400, f"Invalid expiration '{expiration}'") from exc

    snapshot, rows = await get_option_chain_rows(
        db,
        instrument,
        expiration=target_expiration,
        refresh=refresh,
    )
    return {
        "symbol": instrument.symbol,
        "expiration": target_expiration,
        "available_expirations": expirations,
        "snapshot": (
            {
                "id": snapshot.id,
                "observed_at": snapshot.observed_at,
                "fetched_at": snapshot.fetched_at,
                "provider": (snapshot.raw_payload or {}).get("provider"),
                "contract_count": (snapshot.raw_payload or {}).get("contract_count", len(rows)),
            }
            if snapshot is not None
            else None
        ),
        "rows": rows,
    }


@router.get("/options/contracts/{instrument_id:int}")
async def get_option_contract(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = await get_option_contract_summary(db, instrument_id)
    if contract is None:
        raise HTTPException(404, f"Option contract '{instrument_id}' not found")
    return contract


@router.get("/options/contracts/{instrument_id:int}/quote-history")
async def get_option_contract_quote_history(
    instrument_id: int,
    start: str | None = Query(None),
    end: str | None = Query(None),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else datetime.now(UTC) - timedelta(days=30)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.now(UTC)
    return await get_option_quote_history(db, instrument_id, start=start_dt, end=end_dt, refresh=refresh)
