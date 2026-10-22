import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BIGINT, JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
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
      Y  = calendar years
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
    Y1 = "Y1"  # 1 calendar year


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
    # Approximate seconds are used only for generic lookback/fallback math;
    # calendar-year bucketing is handled explicitly by bar_aggregation.
    Timeframe.Y1: 365 * 86400,
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
    market_series_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("market_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # bar open timestamp (UTC)
    session: Mapped[str] = mapped_column(
        String(16), default="regular", server_default="regular", nullable=False
    )
    # Stable conflict key for a scoped series while retaining nullable
    # compatibility for legacy rows that have no MarketSeries relationship.
    scope_key: Mapped[str] = mapped_column(
        String(180), default="legacy:regular", server_default="legacy:regular", nullable=False
    )

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 4), nullable=True)
    vwap: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=True)  # if provided by source

    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adjustment_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="raw")
    adjustment_version: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy")
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # TC-owned derived-bar lineage remains in the existing columns created by
    # ff0a1b2c3d4e. These are nullable except the provider/derived discriminator
    # so legacy rows retain their original unknown values without inference.
    is_derived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    source_timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    derivation_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    derived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_bar_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="ohlcv_bars")
    data_source: Mapped["DataSource"] = relationship(back_populates="ohlcv_bars")
    market_series: Mapped["MarketSeries | None"] = relationship(overlaps="market_series")

    __table_args__ = (
        # Primary query pattern: get all bars for an instrument at a timeframe in a date range
        Index("ix_ohlcv_instrument_tf_ts", "instrument_id", "timeframe", "ts"),
        Index(
            "ix_ohlcv_instrument_tf_session_ts",
            "instrument_id",
            "timeframe",
            "session",
            "ts",
        ),
        # Uniqueness: one bar per instrument/timeframe/ts/adjustment combination
        Index(
            "uq_ohlcv_bar",
            "instrument_id",
            "timeframe",
            "ts",
            "is_adjusted",
            "scope_key",
            unique=True,
        ),
        Index("ix_ohlcv_series_tf_ts", "market_series_id", "timeframe", "ts"),
    )

    def __repr__(self) -> str:
        return (
            f"<OHLCVBar instrument_id={self.instrument_id} "
            f"tf={self.timeframe} ts={self.ts} close={self.close}>"
        )


from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from app.models.data_source import DataSource
    from app.models.instrument import Instrument
    from app.models.market_data_foundation import MarketSeries
