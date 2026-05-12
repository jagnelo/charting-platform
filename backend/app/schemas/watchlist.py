from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WatchlistCreate(BaseModel):
    name: str
    description: str | None = None
    screener_id: int | None = None


class WatchlistItemCreate(BaseModel):
    instrument_id: int
    position: int = 0


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    position: int
    added_at: datetime
    left_screener_at: datetime | None = None
    symbol: str | None = None
    name: str | None = None


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_default: bool = False
    is_managed: bool = False
    is_locked: bool = False
    screener_id: int | None = None
    screener_name: str | None = None
    last_screener_run_at: datetime | None = None
    position: int = 0
    created_at: datetime
    items: list[WatchlistItemRead] = []
