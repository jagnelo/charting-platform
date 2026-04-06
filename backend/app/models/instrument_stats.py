from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InstrumentStats(Base):
    """
    Universal market statistics for any instrument type.
    Stored at sync time and refreshed on schedule.
    Synthetic instruments do not have stats rows.
    """

    __tablename__ = "instrument_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    week52_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    week52_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    avg_volume_30d: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(22, 2), nullable=True)
    beta: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped["Instrument"] = relationship(  # type: ignore[name-defined]
        back_populates="stats", foreign_keys=[instrument_id]
    )
