"""Provider-neutral contracts for the workstation's universe performance map."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.watchlist import WatchlistSourceRead

MarketMapGroupBy = Literal["none", "sector", "industry", "sector_industry"]
MarketMapAreaMetric = Literal["equal", "market_cap", "weight", "volume", "field", "python"]
MarketMapNumericAreaField = Literal[
    "avg_volume_30d",
    "pe_ratio",
    "beta",
    "dividend_yield",
    "week52_high",
    "week52_low",
]
MarketMapColorMetric = Literal[
    "return",
    "relative_return",
    "breadth",
    "python",
    "rsi_14",
    "relative_volume",
    "distance_52w_high",
    "distance_52w_low",
]


class MarketMapRequest(BaseModel):
    """A bounded, reproducible map calculation over one canonical source."""

    source_id: str = Field(min_length=1, max_length=4096)
    group_by: MarketMapGroupBy = "sector_industry"
    period: str = Field(default="1D", min_length=1, max_length=24)
    start: datetime | None = None
    end: datetime | None = None
    timeframe: str = "D1"
    adjusted: bool = True
    area_metric: MarketMapAreaMetric = "market_cap"
    area_field: MarketMapNumericAreaField | None = None
    color_metric: MarketMapColorMetric = "return"
    condition: dict[str, object] | None = None
    python_run_id: int | None = Field(default=None, ge=1)
    reference_symbol: str | None = Field(default=None, max_length=80)
    # Keep reference sources on the same bounded canonical-source contract as
    # the primary source.  In particular, an ephemeral explicit source can
    # contain up to 500 canonical IDs and is therefore legitimately longer
    # than a ticker-like identifier.  The cache/snapshot models already use
    # the same 4096-character bound; a shorter request-only bound would make
    # otherwise valid source-polymorphic maps impossible to compare.
    reference_source_id: str | None = Field(default=None, max_length=4096)
    as_of: datetime | None = None
    limit: int = Field(default=10_000, ge=1, le=50_000)

    @model_validator(mode="after")
    def validate_period(self) -> "MarketMapRequest":
        presets = {"1D", "1W", "MTD", "1M", "3M", "6M", "YTD", "1Y", "CUSTOM"}
        if self.period.upper() not in presets:
            raise ValueError("period must be a supported preset or CUSTOM")
        if self.period.upper() == "CUSTOM" and (self.start is None or self.end is None):
            raise ValueError("CUSTOM period requires start and end")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        if self.color_metric == "relative_return" and not self.reference_symbol:
            if not self.reference_source_id:
                raise ValueError("relative_return requires reference_symbol or reference_source_id")
        if self.reference_symbol and self.reference_source_id:
            raise ValueError("reference_symbol and reference_source_id are mutually exclusive")
        if self.color_metric == "breadth" and not self.condition:
            raise ValueError("breadth requires condition")
        if (
            self.color_metric == "python" or self.area_metric == "python"
        ) and self.python_run_id is None:
            raise ValueError("python map output requires python_run_id")
        if self.area_metric == "field" and self.area_field is None:
            raise ValueError("field area requires area_field")
        if self.area_metric != "field" and self.area_field is not None:
            raise ValueError("area_field requires field area metric")
        return self


class MarketMapWarning(BaseModel):
    code: str
    message: str
    instrument_id: int | None = None
    node_id: str | None = None


class MarketMapCell(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    sector: str | None = None
    industry: str | None = None
    classification_provenance: dict[str, object] | None = None
    group_path: list[str] = Field(default_factory=list)
    area_value: float | None = None
    area_provenance: dict[str, object] | None = None
    color_value: float | None = None
    return_value: float | None = None
    condition_value: bool | None = None
    condition_metric: float | None = None
    observation_time: datetime | None = None
    coverage: float = Field(ge=0, le=1)
    color_coverage: float = Field(default=0, ge=0, le=1)
    area_coverage: float = Field(default=0, ge=0, le=1)
    warnings: list[MarketMapWarning] = Field(default_factory=list)


class MarketMapNode(BaseModel):
    node_id: str
    parent_id: str | None = None
    level: str
    label: str
    group_path: list[str] = Field(default_factory=list)
    member_count: int = 0
    covered_count: int = 0
    area_total: float | None = None
    color_value: float | None = None
    coverage: float = Field(ge=0, le=1)
    color_coverage: float = Field(default=0, ge=0, le=1)
    area_coverage: float = Field(default=0, ge=0, le=1)
    aggregation_method: str
    warnings: list[MarketMapWarning] = Field(default_factory=list)


class MarketMapOut(BaseModel):
    source: WatchlistSourceRead
    group_by: MarketMapGroupBy
    period: str
    period_start: datetime | None = None
    period_end: datetime | None = None
    timeframe: str
    adjustment: str
    area_metric: MarketMapAreaMetric
    area_field: MarketMapNumericAreaField | None = None
    color_metric: MarketMapColorMetric
    condition: dict[str, object] | None = None
    python_run_id: int | None = None
    reference_symbol: str | None = None
    reference_source: WatchlistSourceRead | None = None
    reference_source_id: str | None = None
    reference_membership_version: str | None = None
    reference_series_method: str | None = None
    membership_version: str | None = None
    calculation_version: str = "market-map-v1"
    cache_key: str
    cache_hit: bool = False
    cached_at: datetime | None = None
    freshness: str
    freshness_detail: dict[str, int] = Field(default_factory=dict)
    requested_count: int = 0
    evaluated_count: int = 0
    coverage: float = Field(ge=0, le=1)
    color_coverage: float = Field(default=0, ge=0, le=1)
    area_coverage: float = Field(default=0, ge=0, le=1)
    nodes: list[MarketMapNode] = Field(default_factory=list)
    cells: list[MarketMapCell] = Field(default_factory=list)
    exclusions: list[MarketMapWarning] = Field(default_factory=list)
    warnings: list[MarketMapWarning] = Field(default_factory=list)


class MarketMapSnapshotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    cache_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class MarketMapSnapshotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_id: str
    membership_version: str | None = None
    cache_key: str
    snapshot_hash: str
    created_at: datetime
    updated_at: datetime


class MarketMapSnapshotOut(MarketMapSnapshotSummary):
    map: MarketMapOut
