from datetime import datetime

from pydantic import BaseModel


class WatchlistCreate(BaseModel):
    name: str
    description: str | None = None


class WatchlistItemCreate(BaseModel):
    instrument_id: int
    position: int = 0


class WatchlistItemRead(BaseModel):
    id: int
    instrument_id: int
    position: int
    added_at: datetime
    symbol: str | None = None
    name: str | None = None

    class Config:
        from_attributes = True


class WatchlistRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime
    items: list[WatchlistItemRead] = []

    class Config:
        from_attributes = True
