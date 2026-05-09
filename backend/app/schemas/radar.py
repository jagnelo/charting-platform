from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ohlcv import Timeframe
from app.models.radar import RadarOutcomeStatus, RadarRunStatus, RadarSetupType, RadarState


class RadarIndicatorVisualOut(BaseModel):
    type: str
    params: dict
    style: dict
    pane: str = "main"
    role: str | None = None
    label: str | None = None
    source_tag: str | None = None


class RadarDrawingVisualOut(BaseModel):
    drawing_type: str
    indicator_key: str | None = None
    label: str | None = None
    notes: str | None = None
    data: dict
    style: dict
    is_visible: bool = True
    is_locked: bool = True
    source_role: str | None = None
    source_tag: str | None = None


class RadarEvidenceOut(BaseModel):
    overlays: list[dict] = []
    indicator_visuals: list[RadarIndicatorVisualOut] = []
    drawing_visuals: list[RadarDrawingVisualOut] = []
    metrics: dict
    structures: list[dict]


class RadarRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timeframe: Timeframe
    universe_type: str
    universe_filter: dict | None
    status: RadarRunStatus
    started_at: datetime
    completed_at: datetime | None
    evaluated_count: int
    detection_count: int
    error_summary: str | None
    created_at: datetime
    updated_at: datetime


class RadarSetupThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    timeframe: Timeframe
    context_role: str | None
    reference_price: float
    current_setup_type: RadarSetupType
    current_state: RadarState
    state_changed_at: datetime
    started_at: datetime
    last_seen_at: datetime
    detection_count: int


class RadarDetectionSummaryOut(BaseModel):
    id: int
    run_id: int
    instrument_id: int
    instrument_symbol: str
    instrument_name: str
    timeframe: Timeframe
    setup_type: RadarSetupType
    score: float
    observed_at: datetime
    signal_at: datetime
    context_at: datetime | None
    state: RadarState
    state_reason: str | None
    fresh_until: datetime
    thread_id: int | None
    thread_event_index: int | None
    key_level_price: float | None
    entry_price: float | None
    invalidation_price: float | None
    target_price: float | None
    outcome_status: RadarOutcomeStatus
    outcome_last_evaluated_at: datetime | None
    bars_since_signal: int
    max_favorable_excursion_pct: float | None
    max_adverse_excursion_pct: float | None
    target_hit_at: datetime | None
    invalidated_at: datetime | None
    summary: str
    invalidation_hint: str | None
    score_factors: dict
    created_at: datetime
    updated_at: datetime


class RadarThreadEventOut(BaseModel):
    id: int
    setup_type: RadarSetupType
    score: float
    observed_at: datetime
    signal_at: datetime
    context_at: datetime | None
    state: RadarState
    state_reason: str | None
    thread_event_index: int | None
    key_level_price: float | None
    entry_price: float | None
    invalidation_price: float | None
    target_price: float | None
    outcome_status: RadarOutcomeStatus
    outcome_last_evaluated_at: datetime | None
    bars_since_signal: int
    max_favorable_excursion_pct: float | None
    max_adverse_excursion_pct: float | None
    target_hit_at: datetime | None
    invalidated_at: datetime | None
    summary: str
    invalidation_hint: str | None
    created_at: datetime
    updated_at: datetime


class RadarOutcomeSummaryOut(BaseModel):
    timeframe: Timeframe
    setup_type: RadarSetupType
    total: int
    open_count: int
    target_hit_count: int
    invalidated_count: int
    stale_count: int
    target_hit_rate: float
    invalidated_rate: float
    stale_rate: float
    avg_mfe_pct: float | None
    avg_mae_pct: float | None


class RadarWatchlistActionOut(BaseModel):
    watchlist_id: int
    watchlist_name: str
    item_id: int


class RadarDetectionDetailOut(RadarDetectionSummaryOut):
    evidence: RadarEvidenceOut
    thread: RadarSetupThreadOut | None = None
    thread_history: list[RadarThreadEventOut] = []
