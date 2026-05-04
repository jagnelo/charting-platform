from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ohlcv import Timeframe
from app.models.radar import RadarRunStatus, RadarSetupType


class RadarOverlayPoint(BaseModel):
    time: int
    price: float


class RadarOverlay(BaseModel):
    kind: str
    role: str | None = None
    label: str | None = None
    color: str | None = None
    dash_pattern: list[int] | None = None
    start_time: int | None = None
    end_time: int | None = None
    price_low: float | None = None
    price_high: float | None = None
    time: int | None = None
    price: float | None = None
    points: list[RadarOverlayPoint] | None = None


class RadarEvidenceOut(BaseModel):
    overlays: list[RadarOverlay]
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
    fresh_until: datetime
    key_level_price: float | None
    summary: str
    invalidation_hint: str | None
    score_factors: dict


class RadarDetectionDetailOut(RadarDetectionSummaryOut):
    evidence: RadarEvidenceOut

