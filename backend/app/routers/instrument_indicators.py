from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument_indicator_config import InstrumentIndicatorConfig
from app.models.user import User

router = APIRouter(prefix="/instrument-indicators", tags=["instrument-indicators"])


class IndicatorConfigBody(BaseModel):
    indicators: list[dict]


@router.get("/{instrument_id}")
async def get_indicators(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Read the identity tuple without touching expired ORM attributes. The
    # request-scoped async session can expire the dependency's User instance
    # during concurrent chart hydration; dereferencing ``current_user.id`` in
    # that state attempts implicit IO and raises MissingGreenlet.
    user_identity = inspect(current_user).identity
    user_id = int(user_identity[0]) if user_identity else current_user.id
    result = await db.execute(
        select(InstrumentIndicatorConfig).where(
            InstrumentIndicatorConfig.user_id == user_id,
            InstrumentIndicatorConfig.instrument_id == instrument_id,
        )
    )
    config = result.scalar_one_or_none()
    return {"indicators": config.indicators if config else []}


@router.put("/{instrument_id}")
async def set_indicators(
    instrument_id: int,
    body: IndicatorConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_identity = inspect(current_user).identity
    user_id = int(user_identity[0]) if user_identity else current_user.id
    # Use a single database-side upsert for PostgreSQL.  The workstation can
    # have several linked/floating charts persisting the same instrument at
    # once; a read-then-insert sequence races on the unique key and still emits
    # noisy IntegrityError records even when the request is later recovered.
    bind = getattr(db, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect_name == "postgresql":
        statement = (
            pg_insert(InstrumentIndicatorConfig)
            .values(
                user_id=user_id,
                instrument_id=instrument_id,
                indicators=body.indicators,
            )
            .on_conflict_do_update(
                constraint="uq_user_instrument_indicators",
                set_={
                    "indicators": body.indicators,
                    "updated_at": func.now(),
                },
            )
        )
        await db.execute(statement)
        await db.commit()
    else:
        # Keep the lightweight fallback usable for non-PostgreSQL development
        # sessions (for example, SQLite-based unit harnesses).
        result = await db.execute(
            select(InstrumentIndicatorConfig).where(
                InstrumentIndicatorConfig.user_id == user_id,
                InstrumentIndicatorConfig.instrument_id == instrument_id,
            )
        )
        config = result.scalar_one_or_none()
        if config:
            config.indicators = body.indicators
        else:
            config = InstrumentIndicatorConfig(
                user_id=user_id,
                instrument_id=instrument_id,
                indicators=body.indicators,
            )
            db.add(config)
        try:
            await db.commit()
        except IntegrityError:
            # A non-PostgreSQL development session may still race.  Recover the
            # same way as before, while production uses the atomic branch above.
            await db.rollback()
            config = (
                await db.execute(
                    select(InstrumentIndicatorConfig).where(
                        InstrumentIndicatorConfig.user_id == user_id,
                        InstrumentIndicatorConfig.instrument_id == instrument_id,
                    )
                )
            ).scalar_one()
            config.indicators = body.indicators
            await db.commit()

    config = (
        await db.execute(
            select(InstrumentIndicatorConfig).where(
                InstrumentIndicatorConfig.user_id == user_id,
                InstrumentIndicatorConfig.instrument_id == instrument_id,
            )
        )
    ).scalar_one()
    return {"indicators": config.indicators}
