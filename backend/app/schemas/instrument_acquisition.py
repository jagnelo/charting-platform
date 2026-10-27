"""Wire contracts for explicit, user-requested instrument acquisition."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.ohlcv import Timeframe
from app.schemas.ohlcv import OHLCVBarOut


class InstrumentAcquisitionSourceOutcome(BaseModel):
    provider: str
    capability: str
    operation: str
    status: Literal[
        "eligible",
        "held",
        "attempted",
        "returned",
        "no_match",
        "failed",
        "used",
        "cache_hit",
    ]
    reason_code: str | None = None
    result_count: int | None = Field(default=None, ge=0)
    error_type: str | None = None


class InstrumentDiscoveryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    types: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=10, ge=1, le=10)
    request_id: str = Field(min_length=1, max_length=120)

    @field_validator("query", "request_id")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class InstrumentDiscoveryCandidate(BaseModel):
    symbol: str
    name: str
    exchange: str = ""
    type: str
    provider: str
    instrument_id: int | None = None
    identity_status: str = "provider_candidate"


class InstrumentDiscoveryResponse(BaseModel):
    request_id: str
    status: Literal["complete", "partial", "held", "unavailable", "no_match"]
    candidates: list[InstrumentDiscoveryCandidate] = Field(default_factory=list)
    source_outcomes: list[InstrumentAcquisitionSourceOutcome] = Field(default_factory=list)


class ProviderCandidateBinding(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=80)
    exchange: str | None = Field(default=None, max_length=80)

    @field_validator("provider", "symbol", "exchange")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class InstrumentAcquireRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=80)
    provider_candidate: ProviderCandidateBinding | None = None
    request_id: str = Field(min_length=1, max_length=120)

    @field_validator("symbol", "request_id")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def candidate_must_match_requested_symbol(self):
        if (
            self.provider_candidate is not None
            and self.provider_candidate.symbol.strip().upper() != self.symbol.strip().upper()
        ):
            raise ValueError("provider candidate symbol must match requested symbol")
        return self


class QualifiedInstrumentIdentity(BaseModel):
    instrument_id: int
    symbol: str
    identity_status: str
    domain_key: str | None = None
    primary_identifier_type: str | None = None
    primary_identifier_value: str | None = None
    primary_listing_mic: str | None = None


class InstrumentAcquireResponse(BaseModel):
    request_id: str
    status: Literal["resolved", "no_match", "identity_conflict", "held", "failed"]
    reason_code: str | None = None
    instrument: QualifiedInstrumentIdentity | None = None
    source_outcomes: list[InstrumentAcquisitionSourceOutcome] = Field(default_factory=list)


class HistoryCoverageSlice(BaseModel):
    start: datetime
    end: datetime


class HistoryCoverageSummary(BaseModel):
    status: Literal["ready", "partial", "missing", "stale"]
    covered_start: datetime | None = None
    covered_end: datetime | None = None
    bar_count: int = Field(ge=0)
    missing_slices: list[HistoryCoverageSlice] = Field(default_factory=list)


class HistoryAcquisitionRequest(BaseModel):
    timeframe: Timeframe
    adjusted: bool = True
    start: datetime
    end: datetime
    source_provider: str | None = Field(default=None, min_length=1, max_length=80)
    request_id: str = Field(min_length=1, max_length=120)

    @field_validator("request_id")
    @classmethod
    def require_nonblank_request_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_id must not be blank")
        return value.strip()

    @field_validator("source_provider")
    @classmethod
    def normalize_source_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized or normalized in {"*", "all", "any"}:
            raise ValueError("source_provider must name one exact provider")
        return normalized

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("history bounds must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class HistoryAcquisitionResponse(BaseModel):
    request_id: str
    status: Literal["complete", "partial", "held", "no_data", "failed"]
    reason_code: str | None = None
    instrument_id: int
    symbol: str
    timeframe: Timeframe
    adjusted: bool
    requested_start: datetime
    requested_end: datetime
    coverage: HistoryCoverageSummary
    bars: list[OHLCVBarOut] = Field(default_factory=list)
    source_outcomes: list[InstrumentAcquisitionSourceOutcome] = Field(default_factory=list)
