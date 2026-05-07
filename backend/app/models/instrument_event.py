import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class InstrumentEventType(str, enum.Enum):
    EARNINGS = "earnings"
    EARNINGS_ESTIMATE = "earnings_estimate"
    DIVIDEND = "dividend"
    EX_DIVIDEND = "ex_dividend"
    SPLIT = "split"


class EventTimeHint(str, enum.Enum):
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    DURING_MARKET = "during_market"
    UNKNOWN = "unknown"


class InstrumentEvent(Base, TimestampMixin):
    """Persisted economic/corporate event for an instrument."""

    __tablename__ = "instrument_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[InstrumentEventType] = mapped_column(
        SAEnum(InstrumentEventType), nullable=False, index=True
    )
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    time_hint: Mapped[EventTimeHint] = mapped_column(
        SAEnum(EventTimeHint), nullable=False, default=EventTimeHint.UNKNOWN
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)

    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    actual: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    eps_estimate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    eps_actual: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    eps_surprise: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    eps_surprise_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    dividend_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    split_ratio: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    source_event_key: Mapped[str] = mapped_column(String(240), nullable=False)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="events")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "source", "source_event_key", name="uq_instrument_event_source_key"
        ),
        Index("ix_instrument_event_inst_time_type", "instrument_id", "event_time", "event_type"),
    )


class InstrumentEventFetchState(Base, TimestampMixin):
    """Tracks source bootstrap state so event ingestion remains DB-first."""

    __tablename__ = "instrument_event_fetch_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    earnings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetch_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    __table_args__ = (
        UniqueConstraint("instrument_id", "source", name="uq_instrument_event_fetch_state_source"),
    )
