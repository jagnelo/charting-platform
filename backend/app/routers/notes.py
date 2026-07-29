"""Per-user symbol notes used by the workstation and chart markers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.user import User
from app.models.workstation import InstrumentNote
from app.schemas.workstation import InstrumentNoteOut, InstrumentNoteWrite

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("/instruments/{instrument_id}", response_model=InstrumentNoteOut | None)
async def get_instrument_note(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        await db.execute(
            select(InstrumentNote).where(
                InstrumentNote.user_id == current_user.id,
                InstrumentNote.instrument_id == instrument_id,
            )
        )
    ).scalar_one_or_none()


@router.put("/instruments/{instrument_id}", response_model=InstrumentNoteOut)
async def save_instrument_note(
    instrument_id: int,
    body: InstrumentNoteWrite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    instrument = await db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    note = (
        await db.execute(
            select(InstrumentNote).where(
                InstrumentNote.user_id == current_user.id,
                InstrumentNote.instrument_id == instrument_id,
            )
        )
    ).scalar_one_or_none()
    if note is None:
        note = InstrumentNote(user_id=current_user.id, instrument_id=instrument_id, content=body.content)
        db.add(note)
    else:
        note.content = body.content
    await db.flush()
    return note
