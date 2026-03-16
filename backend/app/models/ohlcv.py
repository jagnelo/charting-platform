import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Timeframe(str, enum.Enum):
    """
    Canonical timeframe identifiers.
    Prefix convention:
      M  = minutes
      H  = hours
      D  = days
      W  = weeks
      MN = months
    """

    M1 = "M1"  # 1 minute
    M5 = "M5"  # 5 minutes
    M15 = "M15"  # 15 minutes
    M30 = "M30"  # 30 minutes
    H1 = "H1"  # 1 hour
    H2 = "H2"  # 2 hours
    H4 = "H4"  # 4 hours
    H12 = "H12"  # 12 hours
    D1 = "D1"  # 1 day
    W1 = "W1"  # 1 week
    MN = "MN"  # 1 month


# Timeframe → approximate seconds (used for aggregation logic)
TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H2: 7200,
    Timeframe.H4: 14400,
    Timeframe.H12: 43200,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
    Timeframe.MN: 2592000,
}


class OHLCVBar(Base):
    """
    A single OHLCV candlestick bar for an instrument at a given timeframe.

    Unified table — no artificial split between "intraday" and "daily".
    Indexed on (instrument_id, timeframe, ts) for fast range queries.

    is_adjusted: True  → split/dividend-adjusted close (default for most long-term charts)
                 False → raw unadjusted price
    """

    __tablename__ = "ohlcv_bar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id"), nullable=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # bar open timestamp (UTC)

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 4), nullable=True)
    vwap: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=True)  # if provided by source

    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="ohlcv_bars")
    data_source: Mapped["DataSource"] = relationship(back_populates="ohlcv_bars")

    __table_args__ = (
        # Primary query pattern: get all bars for an instrument at a timeframe in a date range
        Index("ix_ohlcv_instrument_tf_ts", "instrument_id", "timeframe", "ts"),
        # Uniqueness: one bar per instrument/timeframe/ts/adjustment combination
        Index(
            "uq_ohlcv_bar",
            "instrument_id",
            "timeframe",
            "ts",
            "is_adjusted",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OHLCVBar instrument_id={self.instrument_id} "
            f"tf={self.timeframe} ts={self.ts} close={self.close}>"
        )
