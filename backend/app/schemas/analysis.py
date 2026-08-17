"""Provider-neutral batch analysis response contracts."""

from datetime import UTC, date, datetime
from decimal import Decimal
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


class BenchmarkFamilyRotationRoleOut(BaseModel):
    """Transparent relative-rotation state for one family cap/style leg."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    instrument_id: int | None = None
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
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


class BenchmarkFamilyRotationOut(AnalysisResponseMetadata):
    """Relative rotation of family cap/equal/value/growth legs against cap."""

    family_key: str
    benchmark: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    sampling: int = Field(default=1, ge=1, le=30)
    lookback: int
    tail_length: int
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    roles: list[BenchmarkFamilyRotationRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyConcentrationMemberOut(BaseModel):
    """One resolved family-leg member in a concentration/dispersion summary."""

    instrument_id: int
    symbol: str
    name: str
    position: int
    weight: Decimal | None = None
    performance: float | None = None
    covered: bool


class BenchmarkFamilyConcentrationRoleOut(BaseModel):
    """Concentration and cross-sectional dispersion for one family role."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    membership_version: int | None = None
    composition_date: date | None = None
    known_at: datetime | None = None
    weight_method: str = "unavailable"
    reported_weight_coverage: float | None = Field(default=None, ge=0, le=1)
    top_n: int = Field(ge=1, le=25)
    top_n_weight: float | None = None
    hhi: float | None = None
    effective_constituents: float | None = None
    eligible_count: int = 0
    covered_count: int = 0
    excluded_count: int = 0
    coverage: float = Field(ge=0, le=1)
    mean_return: float | None = None
    median_return: float | None = None
    dispersion: float | None = None
    p10_return: float | None = None
    p25_return: float | None = None
    p75_return: float | None = None
    p90_return: float | None = None
    positive_percentage: float | None = Field(default=None, ge=0, le=1)
    negative_percentage: float | None = Field(default=None, ge=0, le=1)
    members: list[BenchmarkFamilyConcentrationMemberOut] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyConcentrationOut(AnalysisResponseMetadata):
    """Concentration/dispersion batch over independent benchmark-family legs."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    rank_period: str
    top_n: int = Field(ge=1, le=25)
    roles: list[BenchmarkFamilyConcentrationRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyConcentrationHistoryPointOut(BaseModel):
    """One point-in-time concentration observation for a family leg."""

    timestamp: datetime
    snapshot_id: int | None = None
    composition_date: date | None = None
    known_at: datetime | None = None
    membership_version: int
    membership_semantics: str | None = None
    weight_method: str = "unavailable"
    reported_weight_coverage: float | None = Field(default=None, ge=0, le=1)
    top_n_weight: float | None = None
    hhi: float | None = None
    effective_constituents: float | None = None
    eligible_count: int = 0
    covered_count: int = 0
    excluded_count: int = 0
    coverage: float = Field(ge=0, le=1)
    mean_return: float | None = None
    median_return: float | None = None
    dispersion: float | None = None
    p10_return: float | None = None
    p25_return: float | None = None
    p75_return: float | None = None
    p90_return: float | None = None
    positive_percentage: float | None = Field(default=None, ge=0, le=1)
    negative_percentage: float | None = Field(default=None, ge=0, le=1)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyConcentrationHistoryRoleOut(BaseModel):
    """Historical concentration observations for one independent family role."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    membership_semantics: str | None = None
    points: list[BenchmarkFamilyConcentrationHistoryPointOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyConcentrationHistoryOut(AnalysisResponseMetadata):
    """Point-in-time concentration/dispersion history for family roles."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    rank_period: str
    top_n: int = Field(ge=1, le=25)
    limit: int = Field(ge=1, le=5_000)
    roles: list[BenchmarkFamilyConcentrationHistoryRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


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


class BenchmarkFamilyMappingOut(BaseModel):
    """One independently tracked cap/equal/value/growth relationship."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    source_url: str | None = None
    instrument_id: int | None = None
    available: bool = False
    holdings_snapshot_id: int | None = None
    holdings_available: bool = False
    holdings_composition_date: date | None = None
    holdings_known_at: datetime | None = None
    holdings_source_provider: str | None = None
    holdings_completeness_status: str | None = None
    holdings_row_count: int | None = None
    holdings_resolved_count: int | None = None
    holdings_unresolved_count: int | None = None
    holdings_total_weight: Decimal | None = None


class BenchmarkFamilyCoverageSnapshotOut(BaseModel):
    """One dated holdings disclosure available for a family leg."""

    snapshot_id: int
    composition_date: date
    as_of_date: date | None = None
    known_at: datetime | None = None
    provenance: str
    source_provider: str
    source_quality: str
    completeness_status: str
    row_count: int
    resolved_count: int
    unresolved_count: int


class BenchmarkFamilyCoverageRoleOut(BaseModel):
    """Historical holdings coverage for one independently mapped family role."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    instrument_id: int | None = None
    available: bool = False
    status: str
    snapshots: list[BenchmarkFamilyCoverageSnapshotOut] = Field(default_factory=list)


class BenchmarkFamilyCoverageOut(AnalysisResponseMetadata):
    """Dated family-leg holdings coverage without proxy substitution."""

    family_key: str
    name: str
    official_index_symbol: str
    official_index_name: str
    as_of: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    coverage: float = Field(ge=0, le=1)
    roles: list[BenchmarkFamilyCoverageRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyOverviewOut(AnalysisResponseMetadata):
    """Proxy-leg comparison for one benchmark family, never a silent fallback."""

    family_key: str
    name: str
    official_index_symbol: str
    official_index_name: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)
    mappings: list[BenchmarkFamilyMappingOut] = Field(default_factory=list)
    derived_equal_weight: dict[str, object] = Field(default_factory=dict)
    rows: list[GroupSnapshotRow] = Field(default_factory=list)


class BenchmarkFamilyDerivedEqualWeightOut(AnalysisResponseMetadata):
    """A reproducible equal-weight series built only from eligible family members."""

    family_key: str
    name: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    method: str
    member_count: int = Field(ge=0)
    covered_member_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    points: list[AnalysisPoint] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyRatioOut(AnalysisResponseMetadata):
    """One role-labelled ratio between family legs or an explicit market benchmark."""

    family_key: str
    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str
    benchmark_role: Literal["cap_weight", "market"]
    benchmark: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    points: list[AnalysisPoint] = Field(default_factory=list)
    coverage: float = Field(ge=0, le=1)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyRatiosOut(AnalysisResponseMetadata):
    """Aligned role-aware relative-strength ratios for one benchmark family."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    ratios: list[BenchmarkFamilyRatioOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyTechnicalRoleOut(BaseModel):
    """Technical snapshot for one independently mapped family leg."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    as_of: datetime | None = None
    last: float | None = None
    rsi14: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    position_52w: float | None = None
    volume_ratio_50: float | None = None
    freshness: str = "unavailable"
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyTechnicalsOut(AnalysisResponseMetadata):
    """Role-aware technical snapshots for every mapped family proxy."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    roles: list[BenchmarkFamilyTechnicalRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyBreadthMetricOut(BaseModel):
    """One transparent current participation metric for a family role."""

    percentage: float | None = Field(default=None, ge=0, le=1)
    requested_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    coverage: float = Field(ge=0, le=1)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyBreadthRoleOut(BaseModel):
    """Role-local current participation and relative-strength metrics."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    membership_version: int | None = None
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    above_ma: dict[str, BenchmarkFamilyBreadthMetricOut] = Field(default_factory=dict)
    near_52w_high: BenchmarkFamilyBreadthMetricOut | None = None
    new_high: BenchmarkFamilyBreadthMetricOut | None = None
    trend_up: BenchmarkFamilyBreadthMetricOut | None = None
    relative_strength_to_cap: BenchmarkFamilyBreadthMetricOut | None = None
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyBreadthOut(AnalysisResponseMetadata):
    """Side-by-side current breadth for every available family role."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    near_threshold: float = Field(ge=0, le=0.5)
    new_high_lookback: int = Field(ge=2, le=252)
    membership_version: int
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    roles: list[BenchmarkFamilyBreadthRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class ETFConstituentSnapshotRowOut(GroupSnapshotRow):
    """Technical row plus disclosed point-in-time holding evidence."""

    position: int
    weight: Decimal | None = None
    shares: Decimal | None = None
    market_value: Decimal | None = None
    holding_type: str
    row_type: str
    resolution_confidence: Decimal | None = None


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
    rows: list[ETFConstituentSnapshotRowOut] = Field(default_factory=list)


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


class BenchmarkFamilyBreadthHistoryRoleOut(BaseModel):
    """Historical moving-average participation for one family role."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    membership_version: int | None = None
    universe_provenance: dict[str, object] = Field(default_factory=dict)
    points: list[BreadthHistoryPoint] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyBreadthHistoryOut(AnalysisResponseMetadata):
    """Aligned historical participation across independent family roles."""

    family_key: str
    official_index_symbol: str
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    limit: int = Field(ge=1, le=5_000)
    roles: list[BenchmarkFamilyBreadthHistoryRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyRankingRoleOut(BaseModel):
    """Transparent performance/rank cells for one benchmark-family role."""

    role: Literal["cap_weight", "equal_weight", "value", "growth"]
    symbol: str | None = None
    label: str
    verification_state: str
    available: bool
    rank: int | None = None
    performance: dict[str, float | None] = Field(default_factory=dict)
    relative_performance: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class BenchmarkFamilyRankingOut(AnalysisResponseMetadata):
    """Role ranking against the family cap proxy without hidden substitutions."""

    family_key: str
    official_index_symbol: str
    benchmark: str | None = None
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    rank_period: str
    roles: list[BenchmarkFamilyRankingRoleOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class CrossFamilyRankingRowOut(BaseModel):
    """One cap-weighted family row in a cross-family comparison."""

    family_key: str
    family_name: str
    official_index_symbol: str
    symbol: str | None = None
    label: str
    available: bool
    rank: int | None = None
    performance: dict[str, float | None] = Field(default_factory=dict)
    relative_performance: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class CrossFamilyRankingOut(AnalysisResponseMetadata):
    """Cross-family cap-weighted ranking with optional explicit benchmark."""

    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    benchmark: str | None = None
    rank_period: str
    rows: list[CrossFamilyRankingRowOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class CrossFamilyRankingHistoryPoint(BaseModel):
    """One timestamp in a historical cross-family leadership series."""

    timestamp: datetime
    rank: int | None = None
    performance: dict[str, float | None] = Field(default_factory=dict)
    relative_performance: dict[str, float | None] = Field(default_factory=dict)


class CrossFamilyRankingHistoryRowOut(BaseModel):
    """Historical cap-proxy ranking for one benchmark family."""

    family_key: str
    family_name: str
    official_index_symbol: str
    symbol: str | None = None
    label: str
    available: bool
    coverage: float = Field(ge=0, le=1)
    points: list[CrossFamilyRankingHistoryPoint] = Field(default_factory=list)
    warnings: list[AnalysisWarning] = Field(default_factory=list)


class CrossFamilyRankingHistoryOut(AnalysisResponseMetadata):
    """Historical cross-family performance and rank curves."""

    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    benchmark: str | None = None
    rank_period: str
    limit: int = Field(ge=1, le=5_000)
    rows: list[CrossFamilyRankingHistoryRowOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthUniverseRequest(BaseModel):
    """A provider-neutral universe selector for reusable breadth studies."""

    kind: Literal["group", "benchmark_family", "etf_holdings", "symbols"]
    key: str | None = Field(default=None, min_length=1, max_length=160)
    role: Literal["cap_weight", "equal_weight", "value", "growth"] = "cap_weight"
    symbols: list[str] = Field(default_factory=list, max_length=25_000)
    point_in_time: bool = True


class BreadthConditionRequest(BaseModel):
    """A member-level condition or an explicit cross-sectional target."""

    kind: Literal[
        "above_moving_average",
        "within_52_week_high",
        "new_high_low",
        "prior_high_low",
        "trend",
        "rsi",
        "volume_ratio",
        "relative_strength",
        "series_comparison",
        "event",
        "comparison",
        "range",
        "percentile",
        "all",
        "any",
        "not",
    ]
    target_scope: Literal["member", "cross_sectional"] = "member"
    params: dict[str, object] = Field(default_factory=dict)


class BreadthDefinitionRequest(BaseModel):
    version: int = Field(default=1, ge=1, le=1)
    universe: BreadthUniverseRequest
    condition: BreadthConditionRequest | None = None
    condition_asset_key: str | None = Field(default=None, min_length=1, max_length=80)
    timeframe: str = "D1"
    adjusted: bool = True
    as_of: datetime | None = None
    benchmark: str | None = Field(default=None, max_length=80)
    reference_universe: BreadthUniverseRequest | None = None


class BreadthConditionDiagnosticOut(BaseModel):
    """Structured trace entry for one breadth AST clause."""

    path: str
    kind: str
    status: Literal["pass", "fail", "excluded"]
    value: bool | None = None
    metric: float | None = None
    code: str | None = None


class BreadthMemberResultOut(BaseModel):
    instrument_id: int
    symbol: str
    name: str
    value: bool | None = None
    metric: float | None = None
    observation_time: datetime | None = None
    warning: AnalysisWarning | None = None
    diagnostics: list[BreadthConditionDiagnosticOut] = Field(default_factory=list)


class BreadthDefinitionOut(AnalysisResponseMetadata):
    """Current snapshot for a reusable, condition-driven breadth definition."""

    definition_version: int
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    condition_asset_key: str | None = None
    condition_library_version: int | None = None
    python_code_version_id: int | None = None
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


class BreadthDefinitionHistoryOccurrenceOut(BaseModel):
    """A member state transition in a historical breadth definition."""

    occurrence_id: str
    timestamp: datetime
    kind: Literal["member_entered", "member_exited"]
    instrument_id: int
    symbol: str
    name: str
    value: bool
    metric: float | None = None
    percentage: float | None = Field(default=None, ge=0, le=1)
    pass_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)


class BreadthDefinitionHistoryOut(AnalysisResponseMetadata):
    """Aligned historical output for the same reusable breadth definition."""

    definition_version: int
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    condition_asset_key: str | None = None
    condition_library_version: int | None = None
    python_code_version_id: int | None = None
    timeframe: str
    adjustment: str
    as_of: datetime | None = None
    points: list[BreadthDefinitionHistoryPointOut] = Field(default_factory=list)
    occurrences: list[BreadthDefinitionHistoryOccurrenceOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthPythonRunRequest(BaseModel):
    """Queue one user-authored Boolean predicate through the isolated runner."""

    code_version_id: int = Field(ge=1)
    universe: BreadthUniverseRequest
    parameters: dict[str, object] = Field(default_factory=dict)
    timeframe: str = "D1"
    adjusted: bool = True
    session: Literal["regular", "all"] = "regular"
    as_of: datetime | None = None
    benchmark: str | None = Field(default=None, max_length=80)
    history: bool = False
    history_limit: int = Field(default=500, ge=1, le=5_000)


class BreadthPythonRunOut(BaseModel):
    run_id: int
    code_version_id: int
    status: str
    execution_mode: Literal["breadth_current", "breadth_history"]
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    dataset_manifest: dict[str, object] = Field(default_factory=dict)
    progress: dict[str, object] = Field(default_factory=dict)
    diagnostics: list[dict[str, object]] = Field(default_factory=list)


class BreadthPythonResultPointOut(BaseModel):
    timestamp: datetime | None = None
    requested_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    percentage: float | None = Field(default=None, ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    members: list[BreadthMemberResultOut] = Field(default_factory=list)
    exclusions: list[AnalysisWarning] = Field(default_factory=list)


class BreadthPythonResultOut(AnalysisResponseMetadata):
    """Collected isolated-Python breadth output with explicit run lineage."""

    run_id: int
    code_version_id: int
    status: str
    execution_mode: Literal["breadth_current", "breadth_history"]
    definition_hash: str
    universe: dict[str, object] = Field(default_factory=dict)
    condition: dict[str, object] = Field(default_factory=dict)
    dataset_manifest: dict[str, object] = Field(default_factory=dict)
    current: BreadthPythonResultPointOut | None = None
    points: list[BreadthPythonResultPointOut] = Field(default_factory=list)
    occurrences: list[BreadthDefinitionHistoryOccurrenceOut] = Field(default_factory=list)
    progress: dict[str, object] = Field(default_factory=dict)
    diagnostics: list[dict[str, object]] = Field(default_factory=list)


class BreadthPythonPromotionRequest(BaseModel):
    """Create a reusable EasyScan from a completed historical Python breadth run."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2_000)
    schedule: str | None = Field(default=None, max_length=50)
    is_active: bool = True


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
