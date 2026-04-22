from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class DataSource(Base, TimestampMixin):
    """
    Represents an external source of market data.
    Configuration and declared capabilities are stored as JSON for flexibility.
    """

    __tablename__ = "data_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=True)  # API keys, headers, rate limits
    supported_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)

    ohlcv_bars: Mapped[list["OHLCVBar"]] = relationship(back_populates="data_source")
    instrument_identifiers: Mapped[list["InstrumentIdentifier"]] = relationship(
        back_populates="data_source"
    )
    provider_symbols: Mapped[list["InstrumentProviderSymbol"]] = relationship(
        back_populates="data_source"
    )

    def __repr__(self) -> str:
        return f"<DataSource name={self.name}>"
