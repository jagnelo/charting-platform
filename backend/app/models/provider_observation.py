import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.ohlcv import Timeframe


class DatasetStatus(str, enum.Enum):
    FRESH = "fresh"
    STALE = "stale"
    PENDING = "pending"
    FAILED = "failed"


class InstrumentDatasetState(Base, TimestampMixin):
    __tablename__ = "instrument_dataset_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dataset_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    status: Mapped[DatasetStatus] = mapped_column(
        SAEnum(DatasetStatus), nullable=False, default=DatasetStatus.PENDING
    )
    coverage_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    coverage_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource | None"] = relationship(back_populates="dataset_states")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "dataset_type",
            "dataset_key",
            name="uq_instrument_dataset_state",
        ),
    )


class InstrumentProfileSnapshot(Base, TimestampMixin):
    __tablename__ = "instrument_profile_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource"] = relationship(back_populates="profile_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "profile_hash",
            name="uq_instrument_profile_snapshot_hash",
        ),
        Index(
            "ix_instrument_profile_snapshot_inst_source_observed",
            "instrument_id",
            "data_source_id",
            "observed_at",
        ),
    )


class MarketBarObservation(Base):
    __tablename__ = "market_bar_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(30, 4), nullable=True)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    is_adjusted: Mapped[bool] = mapped_column(nullable=False, default=True)

    instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource"] = relationship(back_populates="bar_observations")

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "timeframe",
            "ts",
            "is_adjusted",
            name="uq_market_bar_observation",
        ),
    )


class OptionChainSnapshot(Base, TimestampMixin):
    __tablename__ = "option_chain_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    underlying_instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    underlying_instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource"] = relationship(back_populates="option_chain_snapshots")
    quote_points: Mapped[list["OptionQuotePoint"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "underlying_instrument_id",
            "data_source_id",
            "expiration_date",
            "snapshot_hash",
            name="uq_option_chain_snapshot_hash",
        ),
        Index(
            "ix_option_chain_snapshot_underlying_exp_observed",
            "underlying_instrument_id",
            "expiration_date",
            "observed_at",
        ),
    )


class OptionQuotePoint(Base, TimestampMixin):
    __tablename__ = "option_quote_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    option_instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("option_chain_snapshot.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    mark: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    last: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(30, 4), nullable=True)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(30, 4), nullable=True)
    implied_vol: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    theta: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    vega: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    rho: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    extra_greeks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observation_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)

    option_instrument: Mapped["Instrument"] = relationship()
    snapshot: Mapped["OptionChainSnapshot | None"] = relationship(back_populates="quote_points")
    data_source: Mapped["DataSource"] = relationship(back_populates="option_quote_points")

    __table_args__ = (
        UniqueConstraint(
            "option_instrument_id",
            "data_source_id",
            "observed_at",
            name="uq_option_quote_point_observed",
        ),
        Index(
            "ix_option_quote_point_option_observed",
            "option_instrument_id",
            "observed_at",
        ),
    )
