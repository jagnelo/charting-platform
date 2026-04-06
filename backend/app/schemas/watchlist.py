from datetime import datetime

from pydantic import BaseModel


class WatchlistCreate(BaseModel):
    name: str
    description: str | None = None
    screener_id: int | None = None


class WatchlistItemCreate(BaseModel):
    instrument_id: int
    position: int = 0


class WatchlistItemRead(BaseModel):
    id: int
    instrument_id: int
    position: int
    added_at: datetime
    left_screener_at: datetime | None = None
    symbol: str | None = None
    name: str | None = None

    class Config:
        from_attributes = True


class WatchlistRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_default: bool = False
    is_managed: bool = False
    is_locked: bool = False
    screener_id: int | None = None
    last_screener_run_at: datetime | None = None
    created_at: datetime
    items: list[WatchlistItemRead] = []

    class Config:
        from_attributes = True
