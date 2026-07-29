"""Provider-neutral batch analysis response contracts."""

from datetime import datetime

from pydantic import BaseModel, Field


class AnalysisWarning(BaseModel):
    code: str
    message: str
    instrument_id: int | None = None


class AnalysisPoint(BaseModel):
    timestamp: datetime
    value: float


class RelativeStrengthOut(BaseModel):
    symbol: str
    benchmark: str
    timeframe: str
    adjustment: str
    points: list[AnalysisPoint]
    overlap_start: datetime | None
    overlap_end: datetime | None
    coverage: float = Field(ge=0, le=1)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class AnalysisCell(BaseModel):
    value: float | None = None
    observation_time: datetime | None = None
    warning: AnalysisWarning | None = None


class GroupSnapshotRow(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    last: AnalysisCell
    performance: dict[str, AnalysisCell]
    relative_to_benchmark: AnalysisCell | None = None


class GroupSnapshotOut(BaseModel):
    group_key: str
    timeframe: str
    as_of: datetime | None
    adjustment: str
    membership_version: int
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
    rows: list[GroupSnapshotRow]


class BreadthOut(BaseModel):
    group_key: str
    timeframe: str
    as_of: datetime | None
    evaluated_count: int
    coverage: float = Field(ge=0, le=1)
    above_ma: dict[str, float | None]
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
