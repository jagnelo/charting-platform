import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OptionStyle(str, enum.Enum):
    AMERICAN = "american"
    EUROPEAN = "european"
    BERMUDAN = "bermudan"


class OptionRight(str, enum.Enum):
    CALL = "call"
    PUT = "put"


class EquityDetail(Base):
    """
    Extended metadata for Stock / ETF / REIT instruments.
    """

    __tablename__ = "equity_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id"), unique=True, nullable=False
    )
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sub_industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    website: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employees: Mapped[int | None] = mapped_column(nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    shares_outstanding: Mapped[Decimal | None] = mapped_column(Numeric(20, 0), nullable=True)
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_reit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="equity_detail")  # noqa


class FutureDetail(Base):
    """
    Metadata specific to futures contracts (equity index, commodity, bond, currency futures).
    """

    __tablename__ = "future_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id"), unique=True, nullable=False
    )
    # The underlying asset (e.g. S&P 500 index, Crude Oil, Gold)
    underlying_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # FK to the underlying instrument if it exists in our DB
    underlying_instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrument.id"), nullable=True
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_size: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    tick_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    settlement_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Physical or cash settlement
    settlement_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rollover_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # e.g. 'Q' quarterly, 'M' monthly, 'W' weekly
    expiry_cycle: Mapped[str | None] = mapped_column(String(8), nullable=True)

    instrument: Mapped["Instrument"] = relationship(
        back_populates="future_detail", foreign_keys=[instrument_id]
    )  # noqa


class OptionDetail(Base):
    """
    Metadata specific to options contracts (equity, index, ETF options).
    An option always has an underlying instrument.
    """

    __tablename__ = "option_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id"), unique=True, nullable=False
    )
    # The instrument this option is written on
    underlying_instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instrument.id"), nullable=False
    )
    strike: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    option_right: Mapped[OptionRight] = mapped_column(SAEnum(OptionRight), nullable=False)
    option_style: Mapped[OptionStyle] = mapped_column(
        SAEnum(OptionStyle), default=OptionStyle.AMERICAN, nullable=False
    )
    contract_size: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=100, nullable=False)
    # Option greeks (snapshot, not historical)
    delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    greeks_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    instrument: Mapped["Instrument"] = relationship(
        back_populates="option_detail", foreign_keys=[instrument_id]
    )  # noqa
    underlying_instrument: Mapped["Instrument"] = relationship(  # noqa
        foreign_keys=[underlying_instrument_id]
    )
