"""Normalized provider adjustment-factor observations."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AdjustmentFactorObservation(Base, TimestampMixin):
    """Durable event-level adjustment input supplied by a data source.

    ``factor`` is populated only when the source supplies a numeric factor
    suitable for rebuilding its adjustment convention. Dividend amounts and
    other opaque event payloads remain stored as evidence without being
    converted into an invented factor.
    """

    __tablename__ = "adjustment_factor_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    factor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    factor: Mapped[Decimal | None] = mapped_column(Numeric(24, 12), nullable=True)
    factor_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 12), nullable=True)
    source_event_key: Mapped[str] = mapped_column(String(240), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    factor_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "factor_type",
            "effective_at",
            "source_event_key",
            name="uq_adjustment_factor_observation",
        ),
        Index(
            "ix_adjustment_factor_observation_instrument_effective",
            "instrument_id",
            "effective_at",
        ),
    )
