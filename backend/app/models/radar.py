import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.ohlcv import Timeframe


class RadarRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RadarSetupType(str, enum.Enum):
    APPROACHING_SUPPORT = "approaching_support"
    APPROACHING_RESISTANCE = "approaching_resistance"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"
    RECLAIM = "reclaim"
    REJECTION = "rejection"


class RadarRun(Base, TimestampMixin):
    __tablename__ = "radar_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timeframe: Mapped[Timeframe] = mapped_column(
        SAEnum(Timeframe), nullable=False, default=Timeframe.D1
    )
    universe_type: Mapped[str] = mapped_column(String(32), nullable=False, default="all")
    universe_filter: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[RadarRunStatus] = mapped_column(
        SAEnum(RadarRunStatus), nullable=False, default=RadarRunStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    detections: Mapped[list["RadarDetection"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RadarDetection(Base, TimestampMixin):
    __tablename__ = "radar_detection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("radar_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("radar_setup_thread.id", ondelete="SET NULL"), nullable=True, index=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        SAEnum(Timeframe), nullable=False, default=Timeframe.D1
    )
    setup_type: Mapped[RadarSetupType] = mapped_column(
        SAEnum(RadarSetupType), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    context_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fresh_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    thread_event_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_level_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    invalidation_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    score_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    run: Mapped["RadarRun"] = relationship(back_populates="detections")
    instrument: Mapped["Instrument"] = relationship()
    thread: Mapped["RadarSetupThread | None"] = relationship(
        back_populates="detections",
        foreign_keys=[thread_id],
    )


class RadarSetupThread(Base, TimestampMixin):
    __tablename__ = "radar_setup_thread"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        SAEnum(Timeframe), nullable=False, default=Timeframe.D1
    )
    context_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reference_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_setup_type: Mapped[RadarSetupType] = mapped_column(
        SAEnum(RadarSetupType), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    detection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    instrument: Mapped["Instrument"] = relationship()
    detections: Mapped[list["RadarDetection"]] = relationship(
        back_populates="thread",
        foreign_keys="RadarDetection.thread_id",
        order_by=lambda: (
            RadarDetection.signal_at,
            RadarDetection.thread_event_index,
            RadarDetection.id,
        ),
    )
