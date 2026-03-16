import enum
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class OptionStyle(str, enum.Enum):
    AMERICAN = "american"
    EUROPEAN = "european"
    BERMUDAN = "bermudan"


class OptionRight(str, enum.Enum):
    CALL = "call"
    PUT = "put"


class Instrument(Base, TimestampMixin):
    """
    The universal tradeable (or reference) entity.
    Stocks, ETFs, futures, options, forex pairs, crypto, indices — all instruments.
    Specialised metadata lives in the *Detail sub-tables.
    Market data is global (no user ownership).
    User-specific data (drawings, alerts) FK back to this via user_id on those tables.
    """

    __tablename__ = "instrument"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument_type.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    instrument_type: Mapped["InstrumentType"] = relationship(back_populates="instruments")
    listings: Mapped[list["InstrumentListing"]] = relationship(back_populates="instrument")
    ohlcv_bars: Mapped[list["OHLCVBar"]] = relationship(back_populates="instrument")
    drawings: Mapped[list["ChartDrawing"]] = relationship(back_populates="instrument")
    price_alerts: Mapped[list["PriceAlert"]] = relationship(back_populates="instrument")
    indicator_alerts: Mapped[list["IndicatorAlert"]] = relationship(back_populates="instrument")

    equity_detail: Mapped[Optional["EquityDetail"]] = relationship(
        back_populates="instrument", uselist=False, foreign_keys="[EquityDetail.instrument_id]"
    )
    future_detail: Mapped[Optional["FutureDetail"]] = relationship(
        back_populates="instrument", uselist=False, foreign_keys="[FutureDetail.instrument_id]"
    )
    option_detail: Mapped[Optional["OptionDetail"]] = relationship(
        back_populates="instrument", uselist=False, foreign_keys="[OptionDetail.instrument_id]"
    )
    forex_detail: Mapped[Optional["ForexDetail"]] = relationship(
        back_populates="instrument", uselist=False, foreign_keys="[ForexDetail.instrument_id]"
    )

    def __repr__(self) -> str:
        return f"<Instrument symbol={self.symbol} name={self.name}>"


class EquityDetail(Base, TimestampMixin):
    __tablename__ = "equity_detail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exchange_mic: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    market_cap_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instrument: Mapped["Instrument"] = relationship(back_populates="equity_detail")


class FutureDetail(Base, TimestampMixin):
    __tablename__ = "future_detail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    underlying_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    underlying_instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id"), nullable=True
    )
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    tick_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    settlement_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    first_notice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_trading_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_continuous: Mapped[bool] = mapped_column(Boolean, default=False)
    instrument: Mapped["Instrument"] = relationship(
        back_populates="future_detail", foreign_keys=[instrument_id]
    )
    underlying_instrument: Mapped[Optional["Instrument"]] = relationship(
        foreign_keys=[underlying_instrument_id]
    )


class OptionDetail(Base, TimestampMixin):
    __tablename__ = "option_detail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    underlying_instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id"), nullable=False, index=True
    )
    right: Mapped[OptionRight] = mapped_column(SAEnum(OptionRight), nullable=False)
    style: Mapped[OptionStyle] = mapped_column(
        SAEnum(OptionStyle), nullable=False, default=OptionStyle.AMERICAN
    )
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    contract_size: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=100
    )
    delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    implied_vol: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    instrument: Mapped["Instrument"] = relationship(
        back_populates="option_detail", foreign_keys=[instrument_id]
    )
    underlying_instrument: Mapped["Instrument"] = relationship(
        foreign_keys=[underlying_instrument_id]
    )


class ForexDetail(Base, TimestampMixin):
    __tablename__ = "forex_detail"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    base_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    pip_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    instrument: Mapped["Instrument"] = relationship(back_populates="forex_detail")
