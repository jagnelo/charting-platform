from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Exchange(Base, TimestampMixin):
    """
    A financial exchange where instruments are listed and traded.
    Identified by its MIC (Market Identifier Code) per ISO 10383.
    """

    __tablename__ = "exchange"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mic: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=True)  # ISO 3166-1 alpha-2
    timezone: Mapped[str] = mapped_column(String(60), nullable=True)  # e.g. "America/New_York"
    market_open: Mapped[str] = mapped_column(String(5), nullable=True)  # "09:30"
    market_close: Mapped[str] = mapped_column(String(5), nullable=True)  # "16:00"
    currency: Mapped[str] = mapped_column(String(3), nullable=True)  # ISO 4217

    # Relationships
    listings: Mapped[list["InstrumentListing"]] = relationship(back_populates="exchange")

    def __repr__(self) -> str:
        return f"<Exchange mic={self.mic} name={self.name}>"
