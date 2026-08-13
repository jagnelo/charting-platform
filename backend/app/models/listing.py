from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class InstrumentListing(Base, TimestampMixin):
    """
    Represents an instrument's listing on a specific exchange.
    The same instrument (e.g. AAPL) can be listed on multiple exchanges
    under different tickers and currencies (e.g. XNAS:AAPL vs XETR:APC).
    """

    __tablename__ = "instrument_listing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exchange.id"), nullable=True, index=True
    )

    ticker: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=True)  # ISO 4217
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # primary listing flag
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="listings")
    exchange: Mapped["Exchange"] = relationship(back_populates="listings")

    def __repr__(self) -> str:
        return f"<InstrumentListing ticker={self.ticker} exchange_id={self.exchange_id}>"
