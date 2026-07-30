"""Provider-neutral batch analysis response contracts."""

from datetime import date, datetime

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


class RelativeRotationTailPoint(BaseModel):
    timestamp: datetime
    trend: float
    momentum: float


class RelativeRotationRow(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    trend: float | None = None
    momentum: float | None = None
    state: str | None = None
    coverage: float = Field(ge=0, le=1)
    tail: list[RelativeRotationTailPoint] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class RelativeRotationOut(BaseModel):
    group_key: str
    benchmark: str
    timeframe: str
    adjustment: str
    lookback: int
    tail_length: int
    membership_version: int
    rows: list[RelativeRotationRow]


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
    technical: dict[str, AnalysisCell] = Field(default_factory=dict)


class GroupSnapshotOut(BaseModel):
    group_key: str
    timeframe: str
    as_of: datetime | None
    adjustment: str
    membership_version: int
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
    rows: list[GroupSnapshotRow]


class ETFConstituentSnapshotOut(GroupSnapshotOut):
    """A point-in-time ETF-proxy constituent batch, never an official index universe."""

    etf_symbol: str
    composition_date: date
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    completeness_status: str


class IndustryProxySnapshotRow(GroupSnapshotRow):
    """One verified industry-proxy ETF with both sector and market comparisons."""

    relative_to_market: AnalysisCell | None = None


class IndustryProxySnapshotOut(GroupSnapshotOut):
    """Batch values for holdings-classification-verified industry ETF proxies."""

    etf_symbol: str
    industry: str
    market_benchmark: str
    rows: list[IndustryProxySnapshotRow]
    proxy_evidence: list[dict[str, object]] = Field(default_factory=list)


class BreadthOut(BaseModel):
    group_key: str
    timeframe: str
    as_of: datetime | None
    evaluated_count: int
    coverage: float = Field(ge=0, le=1)
    above_ma: dict[str, float | None]
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthHistoryPoint(BaseModel):
    timestamp: datetime
    above_ma: dict[str, float | None]
    coverage: dict[str, float]


class BreadthHistoryOut(BaseModel):
    group_key: str
    timeframe: str
    adjustment: str
    membership_version: int
    points: list[BreadthHistoryPoint]
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class TechnicalSnapshotOut(BaseModel):
    symbol: str
    timeframe: str
    as_of: datetime | None
    adjustment: str
    last: float | None
    rsi14: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    position_52w: float | None
    volume_ratio_50: float | None
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class MarketGaugeOut(BaseModel):
    screener_id: int
    screener_name: str
    run_at: datetime | None
    matched_count: int
    evaluated_count: int
    universe_count: int
    percentage: float | None
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
