from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AssetClass(Base, TimestampMixin):
    """
    Top-level financial asset class.
    Examples: Equity, Fixed Income, Commodity, Currency, Cryptocurrency, Index, Real Estate
    """

    __tablename__ = "asset_class"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    instrument_types: Mapped[list["InstrumentType"]] = relationship(back_populates="asset_class")

    def __repr__(self) -> str:
        return f"<AssetClass name={self.name}>"


class InstrumentType(Base, TimestampMixin):
    """
    A specific type of financial instrument within an asset class.
    Examples:
      Equity     → Stock, ETF, REIT, Closed-End Fund
      Commodity  → Spot, Future, ETF
      Derivative → Option (Call/Put), Future, CFD, Warrant
      Currency   → Forex Pair, Crypto Spot
      Index      → Index (non-tradeable reference), Index ETF
    """

    __tablename__ = "instrument_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_class_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("asset_class.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    asset_class: Mapped["AssetClass"] = relationship(back_populates="instrument_types")
    instruments: Mapped[list["Instrument"]] = relationship(back_populates="instrument_type")

    def __repr__(self) -> str:
        return f"<InstrumentType name={self.name}>"
