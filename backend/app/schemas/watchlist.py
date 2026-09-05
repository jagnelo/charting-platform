from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    name: str
    description: str | None = None
    screener_id: int | None = None


class WatchlistItemCreate(BaseModel):
    instrument_id: int
    position: int = 0


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    position: int
    added_at: datetime
    flagged: bool = False
    left_screener_at: datetime | None = None
    symbol: str | None = None
    name: str | None = None


class WatchlistItemUpdate(BaseModel):
    flagged: bool | None = None
    notes: str | None = None


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    is_default: bool = False
    is_managed: bool = False
    is_locked: bool = False
    screener_id: int | None = None
    screener_name: str | None = None
    last_screener_run_at: datetime | None = None
    position: int = 0
    created_at: datetime
    items: list[WatchlistItemRead] = []


WatchlistSourceKind = str


class WatchlistSourceRead(BaseModel):
    """Common descriptor for every selectable list universe."""

    source_id: str
    source_kind: WatchlistSourceKind
    name: str
    description: str | None = None
    locked: bool = False
    can_follow: bool = True
    can_clone: bool = True
    can_edit_membership: bool = False
    watchlist_id: int | None = None
    stable_key: str | None = None
    instrument_id: int | None = None
    symbol: str | None = None
    membership_version: str | None = None
    member_count: int | None = None
    source: str | None = None
    provenance: dict = {}
    effective_at: datetime | None = None
    known_at: datetime | None = None
    composition_date: str | None = None


class SavedExplicitWatchlistSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    instrument_ids: list[int] = Field(min_length=1, max_length=500)
    parent_source_id: str | None = Field(default=None, max_length=240)
    parent_membership_version: str | None = Field(default=None, max_length=240)


class WatchlistSourceMemberRead(BaseModel):
    instrument_id: int
    position: int
    weight: float | None = None
    relationship_type: str
    source: str | None = None
    effective_at: datetime | None = None
    known_at: datetime | None = None


class WatchlistSourceResolvedRead(BaseModel):
    source: WatchlistSourceRead
    members: list[WatchlistSourceMemberRead] = []
    exclusions: list[dict] = []


class WatchlistSourceHistoryRefreshRequest(BaseModel):
    """Explicit, bounded request to hydrate canonical history for source members."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=1, max_length=256)
    timeframes: list[str] = Field(default_factory=list, max_length=12)
    as_of: datetime | None = None
    max_instruments: int = Field(default=5000, ge=1, le=5000)


class WatchlistSourceHistoryRefreshSourceOut(BaseModel):
    source_id: str
    source_kind: str | None = None
    name: str
    locked: bool = False
    status: str
    member_count: int = 0
    selected_count: int = 0
    deduplicated_count: int = 0
    excluded_count: int = 0
    membership_version: str | None = None
    message: str | None = None


class WatchlistSourceHistoryRefreshSummary(BaseModel):
    run_id: int | None = None
    source_ids: list[str]
    timeframes: list[str]
    as_of: datetime | None = None
    max_instruments: int
    available_instrument_count: int
    selected_instrument_count: int
    limited: bool
    queued: int
    already_queued: int = 0
    queue_unavailable: bool = False
    sources: list[WatchlistSourceHistoryRefreshSourceOut] = Field(default_factory=list)
    message: str | None = None


class WatchlistHistoryRefreshRunOut(BaseModel):
    """Durable status for a bounded canonical-source history refresh."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_ids: list[str]
    timeframes: list[str]
    membership_versions: dict = Field(default_factory=dict)
    as_of: datetime | None = None
    max_instruments: int
    available_instrument_count: int = 0
    selected_instrument_count: int = 0
    queued_count: int = 0
    already_queued_count: int = 0
    status: str
    cancel_requested: bool = False
    progress: dict = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WatchlistSourceHistoryTimeframeStatus(BaseModel):
    timeframe: str
    member_count: int = 0
    covered_member_count: int = 0
    coverage_percent: float = 0.0
    analysis_ready_member_count: int = 0
    analysis_ready_percent: float = 0.0
    required_bar_count: int | None = Field(default=None, ge=1)
    bar_count: int = 0
    oldest: datetime | None = None
    newest: datetime | None = None
    in_progress_count: int = 0
    complete_count: int = 0
    failed_count: int = 0
    pending_count: int = 0


class WatchlistSourceHistoryStatus(BaseModel):
    source_id: str
    source_kind: str | None = None
    name: str
    locked: bool = False
    membership_version: str | None = None
    as_of: datetime | None = None
    max_instruments: int
    available_instrument_count: int = 0
    selected_instrument_count: int = 0
    limited: bool = False
    excluded_count: int = 0
    overall_status: str
    # ``overall_status`` intentionally preserves the legacy covered/worker
    # contract.  These fields answer the stricter workstation question without
    # allowing a one-bar-per-member source to masquerade as study-ready.
    analysis_ready: bool = False
    analysis_ready_status: str = "pending"
    timeframes: list[WatchlistSourceHistoryTimeframeStatus] = Field(default_factory=list)
    message: str | None = None
