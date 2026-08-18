from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ETFProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    symbol: str
    name: str
    issuer: str | None = None
    sponsor: str | None = None
    fund_family: str | None = None
    index_name: str | None = None
    product_url: str | None = None
    sec_cik: str | None = None
    sec_series_id: str | None = None
    sec_class_id: str | None = None
    adapter_key: str | None = None
    adapter_confidence: Decimal | None = None
    adapter_status: str
    provider_aliases: dict | None = None
    legal_metadata: dict | None = None
    latest_composition_date: date | None = None
    latest_snapshot_id: int | None = None
    resolved_count: int = 0
    unresolved_count: int = 0


class ETFProfileUpdateRequest(BaseModel):
    issuer: str | None = None
    sponsor: str | None = None
    fund_family: str | None = None
    index_name: str | None = None
    product_url: str | None = None
    sec_cik: str | None = None
    sec_series_id: str | None = None
    sec_class_id: str | None = None
    provider_aliases: dict | None = None
    legal_metadata: dict | None = None


class ETFProfileBootstrapRequest(BaseModel):
    name: str | None = None


class ETFProfileBootstrapOut(BaseModel):
    profile: ETFProfileOut
    latest_snapshot: "ETFHoldingsSnapshotOut | None" = None
    probe: "ETFHoldingsAdapterProbeOut"
    refresh_attempted: bool = False
    refresh_succeeded: bool = False
    message: str | None = None


class ETFHoldingsAdapterProbeOut(BaseModel):
    symbol: str
    name: str
    adapter_key: str
    source_provider: str | None = None
    confidence: Decimal
    status: str
    reason: str | None = None
    source_url: str | None = None
    issuer_product_id: str | None = None
    required_identifiers: list[str] = Field(default_factory=list)


class ETFHoldingsAdapterCatalogOut(BaseModel):
    adapter_key: str
    source_provider: str
    source_access: str
    required_identifiers: list[str] = Field(default_factory=list)
    route_identifiers: list[str] = Field(default_factory=list)
    url_templates: list[str] = Field(default_factory=list)
    product_page_templates: list[str] = Field(default_factory=list)
    supported_formats: list[str] = Field(default_factory=list)
    live_tested_default_route: bool = False
    supports_sec_filing_fallback: bool = False
    support_route_types: list[str] = Field(default_factory=list)
    supports_product_page_discovery: bool = False
    supports_issuer_product_id: bool = False
    supports_dated_fetch: bool = False
    supports_etf_discovery: bool = False
    parser: str
    parser_confidence: str
    notes: str | None = None


class ETFHoldingsAdapterStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    etf_profile_id: int
    adapter_key: str
    status: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_checked_at: datetime | None = None
    failure_reason: str | None = None
    source_url: str | None = None
    source_identifier: str | None = None
    parser_version: str | None = None
    row_count: int | None = None
    resolved_count: int | None = None
    unresolved_count: int | None = None
    composition_date: date | None = None
    published_at: datetime | None = None
    completeness_status: str | None = None
    rate_limit_state: str | None = None
    extra_data: dict | None = None


class ETFHoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_id: int
    constituent_instrument_id: int | None = None
    constituent_symbol: str | None = None
    constituent_name: str | None = None
    position: int
    reported_symbol: str | None = None
    reported_name: str | None = None
    cusip: str | None = None
    isin: str | None = None
    sedol: str | None = None
    weight: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    currency: str | None = None
    country: str | None = None
    exchange: str | None = None
    holding_type: str
    row_type: str
    source_row_id: str | None = None
    source_row_hash: str
    is_resolved: bool
    resolution_confidence: Decimal | None = None
    resolution_note: str | None = None
    extra_data: dict | None = None


class ETFHoldingsSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    etf_profile_id: int
    etf_instrument_id: int
    etf_symbol: str
    etf_name: str
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    published_at: datetime | None = None
    provenance: str
    source_provider: str
    source_url: str | None = None
    source_identifier: str | None = None
    source_quality: str
    completeness_status: str
    row_count: int
    resolved_count: int
    unresolved_count: int
    total_weight: Decimal | None = None
    parser_version: str
    notes: str | None = None
    extra_data: dict | None = None
    holdings: list[ETFHoldingOut] = Field(default_factory=list)


class ETFHoldingsPageOut(BaseModel):
    snapshot: ETFHoldingsSnapshotOut
    holdings: list[ETFHoldingOut]
    total: int
    limit: int
    offset: int
    has_next: bool


class ETFHoldingsDiffRowOut(BaseModel):
    key: str
    symbol: str
    name: str
    status: str
    weight_before: Decimal | None = None
    weight_after: Decimal | None = None
    weight_delta: Decimal | None = None
    market_value_before: Decimal | None = None
    market_value_after: Decimal | None = None
    shares_before: Decimal | None = None
    shares_after: Decimal | None = None
    holding_type_before: str | None = None
    holding_type_after: str | None = None
    row_type_before: str | None = None
    row_type_after: str | None = None
    resolved_before: bool | None = None
    resolved_after: bool | None = None


class ETFHoldingsDiffSummaryOut(BaseModel):
    gross_weight_churn: Decimal | None = None
    total_added_weight: Decimal | None = None
    total_removed_weight: Decimal | None = None
    total_increased_weight: Decimal | None = None
    total_decreased_weight: Decimal | None = None
    largest_additions: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)
    largest_removals: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)
    largest_reweights: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)


class ETFHoldingsDiffOut(BaseModel):
    left_snapshot: ETFHoldingsSnapshotOut
    right_snapshot: ETFHoldingsSnapshotOut
    total_rows: int
    added: int
    removed: int
    changed: int
    unchanged: int
    summary: ETFHoldingsDiffSummaryOut
    rows: list[ETFHoldingsDiffRowOut]


class ETFHoldingsTransitionOut(BaseModel):
    left_snapshot: ETFHoldingsSnapshotOut
    right_snapshot: ETFHoldingsSnapshotOut
    added: int
    removed: int
    changed: int
    unchanged: int
    gross_weight_churn: Decimal | None = None
    total_added_weight: Decimal | None = None
    total_removed_weight: Decimal | None = None
    total_increased_weight: Decimal | None = None
    total_decreased_weight: Decimal | None = None
    largest_additions: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)
    largest_removals: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)
    largest_reweights: list[ETFHoldingsDiffRowOut] = Field(default_factory=list)


class ETFHoldingsTransitionTimelineOut(BaseModel):
    etf_symbol: str
    etf_name: str
    snapshot_count: int
    transition_count: int
    from_date: date | None = None
    to_date: date | None = None
    transitions: list[ETFHoldingsTransitionOut] = Field(default_factory=list)


class ETFHoldingsOverlapRequest(BaseModel):
    etf_symbols: list[str] = Field(default_factory=list)
    etf_instrument_ids: list[int] = Field(default_factory=list)
    snapshot_date: date | None = None
    point_in_time: bool = True
    top_n: int = Field(default=10, ge=1, le=50)


class ETFHoldingsOverlapConstituentOut(BaseModel):
    key: str
    symbol: str
    name: str
    weight_left: Decimal | None = None
    weight_right: Decimal | None = None
    min_weight: Decimal | None = None


class ETFHoldingsOverlapPairOut(BaseModel):
    left_symbol: str
    right_symbol: str
    left_snapshot: ETFHoldingsSnapshotOut
    right_snapshot: ETFHoldingsSnapshotOut
    left_count: int
    right_count: int
    shared_count: int
    left_unique_count: int
    right_unique_count: int
    jaccard_overlap: Decimal
    shared_weight_left: Decimal | None = None
    shared_weight_right: Decimal | None = None
    overlap_weight_min: Decimal | None = None
    top_shared: list[ETFHoldingsOverlapConstituentOut] = Field(default_factory=list)


class ETFHoldingsOverlapSummaryOut(BaseModel):
    requested_symbols: list[str] = Field(default_factory=list)
    snapshot_date: date | None = None
    point_in_time: bool = True
    etf_count: int
    pair_count: int
    pairs: list[ETFHoldingsOverlapPairOut] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ETFHoldingsOverlapMatrixRequest(ETFHoldingsOverlapRequest):
    metric: str = Field(default="jaccard", pattern="^(jaccard|shared_count|overlap_weight_min)$")
    issuer: str | None = None
    fund_family: str | None = None
    q: str | None = None
    limit: int = Field(default=25, ge=2, le=100)


class ETFHoldingsOverlapMatrixCellOut(BaseModel):
    row_symbol: str
    column_symbol: str
    value: Decimal
    shared_count: int
    jaccard_overlap: Decimal
    overlap_weight_min: Decimal | None = None


class ETFHoldingsOverlapMatrixRowOut(BaseModel):
    symbol: str
    name: str
    snapshot: ETFHoldingsSnapshotOut
    average_overlap: Decimal
    max_overlap: Decimal
    min_overlap: Decimal
    closest_peer: str | None = None
    most_distinct_peer: str | None = None
    cells: list[ETFHoldingsOverlapMatrixCellOut] = Field(default_factory=list)


class ETFHoldingsOverlapMatrixOut(BaseModel):
    requested_symbols: list[str] = Field(default_factory=list)
    snapshot_date: date | None = None
    point_in_time: bool = True
    metric: str
    etf_count: int
    symbols: list[str] = Field(default_factory=list)
    rows: list[ETFHoldingsOverlapMatrixRowOut] = Field(default_factory=list)
    highest_overlap_pairs: list[ETFHoldingsOverlapPairOut] = Field(default_factory=list)
    lowest_overlap_pairs: list[ETFHoldingsOverlapPairOut] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ETFHoldingsDateOut(BaseModel):
    snapshot_id: int
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    row_count: int
    resolved_count: int
    unresolved_count: int
    source_quality: str


class ETFUnresolvedHoldingOut(BaseModel):
    snapshot_id: int
    composition_date: date
    reported_symbol: str | None = None
    reported_name: str | None = None
    cusip: str | None = None
    isin: str | None = None
    sedol: str | None = None
    weight: Decimal | None = None
    holding_type: str
    resolution_note: str | None = None


class ETFConstituentTimelinePoint(BaseModel):
    snapshot_id: int
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    weight: Decimal | None = None
    weight_delta_from_previous: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    source_provider: str
    provenance: str


class ETFHoldingsWeightEvolutionPointOut(BaseModel):
    snapshot_id: int
    composition_date: date
    weight: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None


class ETFHoldingsWeightEvolutionSeriesOut(BaseModel):
    key: str
    symbol: str
    name: str
    first_weight: Decimal | None = None
    last_weight: Decimal | None = None
    weight_delta: Decimal | None = None
    min_weight: Decimal | None = None
    max_weight: Decimal | None = None
    observation_count: int
    points: list[ETFHoldingsWeightEvolutionPointOut] = Field(default_factory=list)


class ETFHoldingsWeightEvolutionOut(BaseModel):
    etf_symbol: str
    etf_name: str
    snapshot_count: int
    from_date: date | None = None
    to_date: date | None = None
    series: list[ETFHoldingsWeightEvolutionSeriesOut] = Field(default_factory=list)


class ETFHoldingsCoverageRow(BaseModel):
    instrument_id: int | None = None
    symbol: str
    name: str
    requested_start: date
    requested_end: date
    first_snapshot_date: date | None = None
    last_snapshot_date: date | None = None
    snapshot_count: int
    status: str
    status_label: str
    source_quality_levels: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ETFHoldingsCoverageRequest(BaseModel):
    etf_symbols: list[str] = Field(default_factory=list)
    etf_instrument_ids: list[int] = Field(default_factory=list)
    start_date: date
    end_date: date


class ETFHoldingsCoverageSummary(BaseModel):
    requested_start: date
    requested_end: date
    total: int
    full: int
    partial: int
    none: int
    missing: int
    rows: list[ETFHoldingsCoverageRow]


class ETFHoldingIngestRow(BaseModel):
    symbol: str | None = None
    name: str | None = None
    cusip: str | None = None
    isin: str | None = None
    sedol: str | None = None
    weight: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    currency: str | None = None
    country: str | None = None
    exchange: str | None = None
    holding_type: str = "equity"
    row_type: str = "security"
    source_row_id: str | None = None
    extra_data: dict | None = None


class ETFHoldingsIngestRequest(BaseModel):
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    published_at: datetime | None = None
    provenance: str = "issuer_current_holdings"
    source_provider: str = "manual"
    source_url: str | None = None
    source_identifier: str | None = None
    source_quality: str = "issuer_current"
    completeness_status: str = "complete"
    parser_version: str = "manual-v1"
    raw_payload_text: str | None = None
    raw_payload_json: dict | None = None
    legal_metadata: dict | None = None
    notes: str | None = None
    rows: list[ETFHoldingIngestRow]


class ETFHoldingsCSVIngestRequest(BaseModel):
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    published_at: datetime | None = None
    provenance: str = "issuer_current_holdings"
    source_provider: str = "manual_csv"
    source_url: str | None = None
    source_identifier: str | None = None
    source_quality: str = "issuer_current"
    completeness_status: str = "complete"
    parser_version: str = "csv-v1"
    raw_csv: str
    legal_metadata: dict | None = None
    notes: str | None = None


class ETFHoldingsDatedRefreshRequest(BaseModel):
    requested_date: date


class BenchmarkFamilyHoldingsDatedRefreshRequest(ETFHoldingsDatedRefreshRequest):
    roles: list[str] = Field(default_factory=list)


class BenchmarkFamilyHoldingsDatedRefreshLegOut(BaseModel):
    role: str
    symbol: str | None = None
    status: str
    snapshot_id: int | None = None
    composition_date: date | None = None
    message: str | None = None


class BenchmarkFamilyHoldingsDatedRefreshSummary(BaseModel):
    family_key: str
    requested_date: date
    roles: list[str]
    refreshed: int
    unavailable: int
    failed: int
    legs: list[BenchmarkFamilyHoldingsDatedRefreshLegOut] = Field(default_factory=list)
    error: str | None = None


class BenchmarkFamilyHoldingsRangeRefreshRequest(BaseModel):
    """Bounded historical dates for independent family-leg backfill."""

    requested_dates: list[date] = Field(min_length=1, max_length=64)
    roles: list[str] = Field(default_factory=list)


class BenchmarkFamilyHoldingsRangeRefreshSummary(BaseModel):
    family_key: str
    requested_dates: list[date]
    roles: list[str]
    refreshed: int
    unavailable: int
    failed: int
    runs: list[BenchmarkFamilyHoldingsDatedRefreshSummary] = Field(default_factory=list)


class BenchmarkFamiliesHoldingsDatedRefreshRequest(BaseModel):
    """Bounded all-family refresh request for locked benchmark universes."""

    requested_date: date
    family_keys: list[str] = Field(default_factory=list, max_length=8)
    roles: list[str] = Field(default_factory=list)


class BenchmarkFamiliesHoldingsDatedRefreshSummary(BaseModel):
    requested_date: date
    family_keys: list[str]
    roles: list[str]
    refreshed: int
    unavailable: int
    failed: int
    families: list[BenchmarkFamilyHoldingsDatedRefreshSummary] = Field(default_factory=list)


class BenchmarkFamiliesHoldingsRangeRefreshRequest(BaseModel):
    """Bounded historical all-family refresh request."""

    requested_dates: list[date] = Field(min_length=1, max_length=64)
    family_keys: list[str] = Field(default_factory=list, max_length=8)
    roles: list[str] = Field(default_factory=list)


class BenchmarkFamiliesHoldingsRangeRefreshSummary(BaseModel):
    requested_dates: list[date]
    family_keys: list[str]
    roles: list[str]
    refreshed: int
    unavailable: int
    failed: int
    runs: list[BenchmarkFamiliesHoldingsDatedRefreshSummary] = Field(default_factory=list)


class ETFHoldingsDiscoveryRequest(BaseModel):
    adapter_key: str
    source_url: str
    issuer: str | None = None
    fund_family: str | None = None


class ETFHoldingsDiscoverySummary(BaseModel):
    adapter_key: str
    source_url: str
    discovered: int
    created: int
    updated: int
    skipped: int
    symbols: list[str] = Field(default_factory=list)


class ETFHoldingsSECIngestRequest(BaseModel):
    composition_date: date | None = None
    as_of_date: date | None = None
    known_at: datetime | None = None
    published_at: datetime | None = None
    accession_number: str | None = None
    filing_url: str | None = None
    source_provider: str = "sec"
    completeness_status: str = "filing_reconstructed"
    parser_version: str = "sec-nport-v1"
    raw_xml: str
    legal_metadata: dict | None = None
    notes: str | None = None


class ETFHoldingsSECLegacyIngestRequest(ETFHoldingsSECIngestRequest):
    parser_version: str = "sec-legacy-v1"


class ETFHoldingsSECBackfillRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    max_filings: int = Field(default=20, ge=1, le=200)


class ETFHoldingsSECBulkBackfillRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    max_profiles: int = Field(default=50, ge=1, le=500)
    max_filings_per_etf: int = Field(default=20, ge=1, le=200)


class ETFHoldingsSECBackfillSummary(BaseModel):
    job_id: int | None = None
    status: str
    discovered: int
    ingested: int
    skipped: int
    failed: int
    failures: list[dict] = Field(default_factory=list)


class ETFHoldingsSECBulkBackfillSummary(BaseModel):
    status: str
    profiles: int
    discovered: int
    ingested: int
    skipped: int
    failed: int
    results: list[dict] = Field(default_factory=list)


class ETFHoldingsBackfillFilingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    etf_profile_id: int
    last_job_id: int | None = None
    snapshot_id: int | None = None
    accession_number: str
    form: str
    filing_date: date | None = None
    report_date: date | None = None
    acceptance_datetime: datetime | None = None
    primary_document: str | None = None
    filing_url: str | None = None
    status: str
    failure_reason: str | None = None
    ingested_at: datetime | None = None
    extra_data: dict | None = None


class ETFHoldingsBackfillJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    etf_profile_id: int
    requested_by_user_id: int | None = None
    source_provider: str
    job_type: str
    status: str
    start_date: date | None = None
    end_date: date | None = None
    max_filings: int | None = None
    discovered_count: int
    ingested_count: int
    skipped_count: int
    failed_count: int
    started_at: datetime
    completed_at: datetime | None = None
    failure_reason: str | None = None
    summary: dict | None = None
    extra_data: dict | None = None
    filings: list[ETFHoldingsBackfillFilingOut] = Field(default_factory=list)
