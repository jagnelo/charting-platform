"""Provider-neutral local-dataset coverage contracts for workstation tools."""

from datetime import datetime

from pydantic import BaseModel, Field


class LocalCoverageRangeOut(BaseModel):
    oldest: datetime | None = None
    newest: datetime | None = None
    bar_count: int = Field(ge=0)


class DatasetCoverageStateOut(BaseModel):
    dataset_type: str
    dataset_key: str
    status: str
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    observed_at: datetime | None = None
    fetched_at: datetime | None = None
    stale_after: datetime | None = None
    version: int = Field(ge=1)


class InstrumentCoverageOut(BaseModel):
    instrument_id: int
    symbol: str
    adjustment: str
    local_coverage: dict[str, LocalCoverageRangeOut]
    dataset_states: list[DatasetCoverageStateOut] = Field(default_factory=list)
    refreshed_at: datetime
    provenance: str = "canonical_local_database"


class OhlcvCoverageSliceOut(BaseModel):
    start: datetime
    end: datetime


class OhlcvCoverageOut(BaseModel):
    instrument_id: int
    symbol: str
    timeframe: str
    adjusted: bool
    mode: str
    requested_start: datetime
    requested_end: datetime
    status: str
    covered_start: datetime | None = None
    covered_end: datetime | None = None
    bar_count: int = Field(ge=0)
    missing_slices: list[OhlcvCoverageSliceOut] = Field(default_factory=list)
    explanation: str
    provenance: str = "canonical_local_database"
