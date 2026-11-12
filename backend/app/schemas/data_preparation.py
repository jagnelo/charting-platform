"""Wire models for owner-scoped, durable data preparation requests."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.ohlcv import Timeframe


class PreparationDataset(str, Enum):
    IDENTITY = "identity"
    PROFILE = "profile"
    HISTORY = "history"
    HOLDINGS = "holdings"
    FUNDAMENTALS = "fundamentals"


class InstrumentPreparationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["instrument"]
    instrument_id: int | None = Field(default=None, gt=0)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_one_identity(self) -> InstrumentPreparationTarget:
        if (self.instrument_id is None) == (self.symbol is None):
            raise ValueError("provide exactly one of instrument_id or symbol")
        if self.symbol is not None:
            self.symbol = self.symbol.strip().upper()
            if not self.symbol:
                raise ValueError("symbol must not be empty")
        return self


class MarketGroupPreparationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["market_group"]
    group_key: str = Field(min_length=1, max_length=180)


class FamilyPreparationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["family"]
    family_key: str = Field(min_length=1, max_length=180)


class ScreenerPreparationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["screener"]
    screener_id: int = Field(gt=0)


PreparationTarget = Annotated[
    InstrumentPreparationTarget
    | MarketGroupPreparationTarget
    | FamilyPreparationTarget
    | ScreenerPreparationTarget,
    Field(discriminator="kind"),
]


class RatioLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: int | None = Field(default=None, gt=0)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_one_identity(self) -> RatioLeg:
        if (self.instrument_id is None) == (self.symbol is None):
            raise ValueError("each ratio leg needs exactly one instrument identity")
        if self.symbol is not None:
            self.symbol = self.symbol.strip().upper()
            if not self.symbol:
                raise ValueError("ratio leg symbol must not be empty")
        return self


class AnalysisPreparation(BaseModel):
    """Analysis inputs use the existing RRG vocabulary; warmup is derived server-side."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["ratio", "rrg"]
    lookback: int = Field(default=20, ge=2, le=252)
    sampling: int = Field(default=1, ge=1, le=30)
    tail_length: int = Field(default=10, ge=1, le=5_000)
    history_length: int = Field(default=0, ge=0, le=5_000)
    legs: list[RatioLeg] | None = None
    benchmark_symbol: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_kind_inputs(self) -> AnalysisPreparation:
        if self.kind == "ratio" and (self.legs is None or len(self.legs) != 2):
            raise ValueError("ratio analysis requires exactly two legs")
        if self.kind != "ratio" and self.legs is not None:
            raise ValueError("legs are supported only for ratio analysis")
        if self.benchmark_symbol is not None:
            self.benchmark_symbol = self.benchmark_symbol.strip().upper()
            if not self.benchmark_symbol:
                raise ValueError("benchmark_symbol must not be empty")
        return self

    @property
    def required_raw_bars(self) -> int:
        """Raw bars for both lookback windows and the requested result tail."""
        return (self.lookback * 2 + self.tail_length + self.history_length) * self.sampling


class DataEnsureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: PreparationTarget
    datasets: list[PreparationDataset] | None = None
    # Field requirements apply to the existing shared profile dependency. The
    # first supported field is industry; omitting this list preserves the
    # historical generic-profile behavior.
    required_profile_fields: list[Literal["industry"]] = Field(default_factory=list)
    timeframe: Timeframe = Timeframe.D1
    adjusted: bool = True
    start_at: datetime | None = None
    end_at: datetime | None = None
    analysis: AnalysisPreparation | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def require_and_normalize_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("range timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range_and_datasets(self) -> DataEnsureRequest:
        if self.start_at and self.end_at and self.start_at > self.end_at:
            raise ValueError("start_at must not be after end_at")
        if self.datasets is not None and len(self.datasets) != len(set(self.datasets)):
            raise ValueError("datasets must not contain duplicates")
        self.required_profile_fields = list(dict.fromkeys(self.required_profile_fields))
        if (
            isinstance(self.target, ScreenerPreparationTarget)
            and self.datasets is not None
            and PreparationDataset.HISTORY not in self.datasets
        ):
            raise ValueError("screener preparation requires the history dataset")
        if (
            self.required_profile_fields
            and self.datasets is not None
            and PreparationDataset.PROFILE not in self.datasets
        ):
            raise ValueError("required_profile_fields requires the profile dataset")
        return self


class PreparationCoveredRange(BaseModel):
    """One contiguous, single-series interval actually present in storage."""

    model_config = ConfigDict(extra="forbid")

    start_at: datetime
    end_at: datetime
    data_source_id: int | None = None
    market_series_id: int | None = None
    adjustment_basis: str
    adjustment_version: str
    is_adjusted: bool


class PreparationDependencyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependency_id: str
    depends_on: list[str] = Field(default_factory=list)
    instrument_id: int | None = None
    symbol: str | None = None
    dataset: PreparationDataset
    status: Literal["queued", "running", "partial", "ready", "waiting", "unavailable", "failed"]
    requested_start: datetime | None = None
    requested_end: datetime | None = None
    covered_start: datetime | None = None
    covered_end: datetime | None = None
    reason_code: str | None = None
    retry_at: datetime | None = None
    updated_at: datetime
    covered_ranges: list[PreparationCoveredRange] = Field(default_factory=list)


class DataEnsureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: Literal["queued", "running", "partial", "ready", "waiting", "unavailable", "failed"]
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)
    target: dict
    dependencies: list[PreparationDependencyResponse] = Field(default_factory=list)
    completed: int = Field(ge=0)
    total: int = Field(ge=0)
    last_progress_at: datetime
    # Older persisted fixtures may not include this additive field. The API
    # response builder always supplies the live queue-derived value.
    has_pending_work: bool = False
