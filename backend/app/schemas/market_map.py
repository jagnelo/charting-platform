"""Provider-neutral contracts for the workstation's universe performance map."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.watchlist import WatchlistSourceRead

MarketMapGroupBy = Literal["none", "sector", "industry", "sector_industry"]
MarketMapAreaMetric = Literal["equal", "market_cap", "weight", "volume"]
MarketMapColorMetric = Literal[
    "return",
    "relative_return",
    "rsi_14",
    "relative_volume",
    "distance_52w_high",
    "distance_52w_low",
]


class MarketMapRequest(BaseModel):
    """A bounded, reproducible map calculation over one canonical source."""

    source_id: str = Field(min_length=1, max_length=240)
    group_by: MarketMapGroupBy = "sector_industry"
    period: str = Field(default="1D", min_length=1, max_length=24)
    start: datetime | None = None
    end: datetime | None = None
    timeframe: str = "D1"
    adjusted: bool = True
    area_metric: MarketMapAreaMetric = "market_cap"
    color_metric: MarketMapColorMetric = "return"
    reference_symbol: str | None = Field(default=None, max_length=80)
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
            raise ValueError("relative_return requires reference_symbol")
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
    group_path: list[str] = Field(default_factory=list)
    area_value: float | None = None
    color_value: float | None = None
    return_value: float | None = None
    observation_time: datetime | None = None
    coverage: float = Field(ge=0, le=1)
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
    color_metric: MarketMapColorMetric
    reference_symbol: str | None = None
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
    nodes: list[MarketMapNode] = Field(default_factory=list)
    cells: list[MarketMapCell] = Field(default_factory=list)
    exclusions: list[MarketMapWarning] = Field(default_factory=list)
    warnings: list[MarketMapWarning] = Field(default_factory=list)
