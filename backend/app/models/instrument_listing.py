from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InstrumentListing(Base):
    """
    The same instrument (e.g. AAPL) can be listed on multiple exchanges
    under different tickers. This table captures each listing.
    """

    __tablename__ = "instrument_listing"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument.id"), nullable=False)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchange.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Is this the canonical/primary listing for this instrument?
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="listings")  # noqa
    exchange: Mapped["Exchange"] = relationship(back_populates="listings")  # noqa
