from datetime import datetime

from pydantic import BaseModel


class FavoriteInstrumentOut(BaseModel):
    id: int
    instrument_id: int
    position: int
    added_at: datetime
    symbol: str
    name: str
