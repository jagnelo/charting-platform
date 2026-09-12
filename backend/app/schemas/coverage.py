"""Provider-neutral local-dataset coverage contracts for workstation tools."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.lib.time_utils import wire_datetime


class LocalCoverageRangeOut(BaseModel):
    oldest: datetime | None = None
    newest: datetime | None = None
    bar_count: int = Field(ge=0)

    @field_serializer("oldest", "newest")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return wire_datetime(value)


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
    extra_data: dict | None = None

    @field_serializer("coverage_start", "coverage_end", "observed_at", "fetched_at", "stale_after")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return wire_datetime(value)


class InstrumentCoverageOut(BaseModel):
    instrument_id: int
    symbol: str
    adjustment: str
    local_coverage: dict[str, LocalCoverageRangeOut]
    dataset_states: list[DatasetCoverageStateOut] = Field(default_factory=list)
    refreshed_at: datetime
    provenance: str = "canonical_local_database"

    @field_serializer("refreshed_at")
    def serialize_timestamp(self, value: datetime) -> str:
        return wire_datetime(value)


class OhlcvCoverageSliceOut(BaseModel):
    start: datetime
    end: datetime

    @field_serializer("start", "end")
    def serialize_timestamps(self, value: datetime) -> str:
        return wire_datetime(value)


class OhlcvLineageOut(BaseModel):
    provider_bar_count: int = Field(ge=0)
    derived_bar_count: int = Field(ge=0)
    unknown_bar_count: int = Field(ge=0)
    source_lineage: str
    source_timeframes: list[str] = Field(default_factory=list)


class OhlcvAdjustmentProvenanceOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: str
    source_kind: str
    factor_status: str
    factor_version: str | None = None
    contract_version: int = Field(ge=1)


class OhlcvStorageEvidenceOut(BaseModel):
    status: str
    provider_bar_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    matched_observation_count: int = Field(ge=0)
    missing_observation_count: int = Field(ge=0)
    mismatched_observation_count: int = Field(ge=0)
    orphan_observation_count: int = Field(ge=0)


class OhlcvObservedCadenceOut(BaseModel):
    """Observed spacing for returned local bars, not a provider schedule."""

    status: str
    sample_count: int = Field(default=0, ge=0)
    median_interval_days: float | None = Field(default=None, ge=0)
    min_interval_days: float | None = Field(default=None, ge=0)
    max_interval_days: float | None = Field(default=None, ge=0)
    semantics: str = "diagnostic_of_returned_bar_timestamps_only"


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
    lineage: OhlcvLineageOut
    adjustment_provenance: OhlcvAdjustmentProvenanceOut
    storage_evidence: OhlcvStorageEvidenceOut
    observed_cadence: OhlcvObservedCadenceOut
    provenance: str = "canonical_local_database"

    @field_serializer("requested_start", "requested_end", "covered_start", "covered_end")
    def serialize_timestamps(self, value: datetime | None) -> str | None:
        return wire_datetime(value)
