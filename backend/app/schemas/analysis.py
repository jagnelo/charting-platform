"""Provider-neutral batch analysis response contracts."""

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisWarning(BaseModel):
    code: str
    message: str
    instrument_id: int | None = None


class AnalysisResponseMetadata(BaseModel):
    """Common local-data lineage for every analysis response."""

    calculation_version: str = "analysis-v1"
    data_provenance: str = "canonical_local_database"
    refreshed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness: str = "coverage_limited"
    freshness_detail: dict[str, int] = Field(default_factory=dict)


class AnalysisPoint(BaseModel):
    timestamp: datetime
    value: float


class RelativeStrengthOut(AnalysisResponseMetadata):
    symbol: str
    benchmark: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
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
    heading: float | None = None
    distance: float | None = None
    velocity: float | None = None
    transition: str | None = None
    time_in_state: int | None = None
    coverage: float = Field(ge=0, le=1)
    tail: list[RelativeRotationTailPoint] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class RelativeRotationOut(AnalysisResponseMetadata):
    group_key: str
    benchmark: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    sampling: int = Field(default=1, ge=1, le=30)
    lookback: int
    tail_length: int
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
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
    calendar_year_performance: dict[str, AnalysisCell] = Field(default_factory=dict)
    relative_to_benchmark: AnalysisCell | None = None
    relative_to_market: AnalysisCell | None = None
    technical: dict[str, AnalysisCell] = Field(default_factory=dict)


class GroupSnapshotOut(AnalysisResponseMetadata):
    group_key: str
    timeframe: str
    as_of: datetime | None
    adjustment: str
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
    rows: list[GroupSnapshotRow]


class ETFConstituentSnapshotOut(GroupSnapshotOut):
    """A point-in-time ETF-proxy constituent batch, never an official index universe."""

    etf_symbol: str
    benchmark: str
    market_benchmark: str | None = None
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


class IndustrySnapshotRow(BaseModel):
    """Equal-weight constituent aggregate for one classified ETF industry."""

    industry: str
    constituent_count: int
    resolved_count: int
    coverage: float = Field(ge=0, le=1)
    last: AnalysisCell
    performance: dict[str, AnalysisCell]
    relative_to_benchmark: AnalysisCell | None = None
    relative_to_market: AnalysisCell | None = None
    technical: dict[str, AnalysisCell] = Field(default_factory=dict)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class IndustrySnapshotOut(AnalysisResponseMetadata):
    """Top-down industry rankings derived from a dated ETF-proxy holding set."""

    group_key: str
    etf_symbol: str
    market_benchmark: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    composition_date: date
    known_at: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
    rows: list[IndustrySnapshotRow]


class BreadthOut(AnalysisResponseMetadata):
    group_key: str
    timeframe: str
    adjustment: str
    as_of: datetime | None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    evaluated_count: int
    coverage: float = Field(ge=0, le=1)
    coverage_detail: dict[str, float] = Field(default_factory=dict)
    member_metrics: dict[str, dict[str, float | int | None]] = Field(default_factory=dict)
    above_ma: dict[str, float | None]
    near_52w: dict[str, float | None] = Field(default_factory=dict)
    new_highs: dict[str, float | None] = Field(default_factory=dict)
    new_lows: dict[str, float | None] = Field(default_factory=dict)
    trend: dict[str, float | None] = Field(default_factory=dict)
    distance_from_ma: dict[str, float | None] = Field(default_factory=dict)
    new_high_lookback: int = 20
    near_threshold: float = 0.05
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthHistoryPoint(BaseModel):
    timestamp: datetime
    above_ma: dict[str, float | None]
    coverage: dict[str, float]


class BreadthHistoryOut(AnalysisResponseMetadata):
    group_key: str
    timeframe: str
    adjustment: str
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    points: list[BreadthHistoryPoint]
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthUniverseRequest(BaseModel):
    """A provider-neutral universe selector for reusable breadth studies."""

    kind: Literal["group", "etf_holdings", "symbols"]
    key: str | None = Field(default=None, min_length=1, max_length=160)
    symbols: list[str] = Field(default_factory=list, max_length=25_000)
    point_in_time: bool = True


class BreadthConditionRequest(BaseModel):
    """One condition evaluated independently for every eligible member."""

    kind: Literal[
        "above_moving_average",
        "within_52_week_high",
        "new_high_low",
        "trend",
        "rsi",
        "volume_ratio",
        "relative_strength",
    ]
    params: dict[str, object] = Field(default_factory=dict)


class BreadthDefinitionRequest(BaseModel):
    version: int = Field(default=1, ge=1, le=1)
    universe: BreadthUniverseRequest
    condition: BreadthConditionRequest
    timeframe: str = "D1"
    adjusted: bool = True
    as_of: datetime | None = None
    benchmark: str | None = Field(default=None, max_length=80)


class BreadthMemberResultOut(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    value: bool | None = None
    metric: float | None = None
    observation_time: datetime | None = None
    warning: AnalysisWarning | None = None


class BreadthDefinitionOut(AnalysisResponseMetadata):
    """Current snapshot for a reusable, condition-driven breadth definition."""

    definition_version: int
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    requested_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    percentage: float | None = Field(default=None, ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    members: list[BreadthMemberResultOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthHistoryRequest(BreadthDefinitionRequest):
    limit: int = Field(default=500, ge=1, le=5_000)


class BreadthDefinitionHistoryPointOut(BaseModel):
    timestamp: datetime
    requested_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    percentage: float | None = Field(default=None, ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    members: list[BreadthMemberResultOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthDefinitionHistoryOut(AnalysisResponseMetadata):
    """Aligned historical output for the same reusable breadth definition."""

    definition_version: int
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    points: list[BreadthDefinitionHistoryPointOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class IndicatorBatchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=10_000)
    indicator: str = Field(min_length=1, max_length=64)
    params: dict[str, object] = Field(default_factory=dict)
    timeframe: str = "D1"
    adjusted: bool = True


class IndicatorBatchValue(BaseModel):
    value: float | None = None
    observation_time: datetime | None = None
    warning: AnalysisWarning | None = None


class IndicatorBatchOut(AnalysisResponseMetadata):
    indicator: str
    timeframe: str
    adjustment: str
    params: dict[str, object] = Field(default_factory=dict)
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    values: dict[str, IndicatorBatchValue] = Field(default_factory=dict)
    requested_count: int = Field(ge=0)
    evaluated_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class TechnicalSnapshotOut(AnalysisResponseMetadata):
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


class MarketGaugeOut(AnalysisResponseMetadata):
    screener_id: int
    screener_name: str
    run_at: datetime | None
    matched_count: int
    evaluated_count: int
    universe_count: int
    percentage: float | None
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
