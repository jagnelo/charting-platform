from datetime import datetime

from pydantic import BaseModel, Field


class BenchmarkFamilyHistoryRefreshRequest(BaseModel):
    """Bounded admin maintenance request for canonical family-member OHLCV."""

    family_keys: list[str] = Field(default_factory=list, max_length=8)
    roles: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list, max_length=12)
    as_of: datetime | None = None
    max_instruments: int = Field(default=5000, ge=1, le=5000)


class BenchmarkFamilyHistoryRefreshLegOut(BaseModel):
    source_id: str
    family_key: str
    role: str
    status: str
    member_count: int = 0
    selected_count: int = 0
    deduplicated_count: int = 0
    excluded_count: int = 0
    membership_version: str | None = None
    message: str | None = None


class BenchmarkFamilyHistoryRefreshSummary(BaseModel):
    family_keys: list[str]
    roles: list[str]
    timeframes: list[str]
    as_of: datetime | None = None
    max_instruments: int
    available_instrument_count: int
    selected_instrument_count: int
    limited: bool
    queued: int
    already_queued: int = 0
    queue_unavailable: bool = False
    legs: list[BenchmarkFamilyHistoryRefreshLegOut] = Field(default_factory=list)
    message: str | None = None

