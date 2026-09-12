"""Canonical metadata for tokenized securities and their chain deployments."""

from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TokenizedAssetDetail(Base, TimestampMixin):
    """Product-level token metadata; never conflated with the underlying asset."""

    __tablename__ = "tokenized_asset_detail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    underlying_instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_asset_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    token_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    underlying_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    underlying_figi: Mapped[str | None] = mapped_column(String(80), nullable=True)
    underlying_composite_figi: Mapped[str | None] = mapped_column(String(80), nullable=True)
    underlying_isin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    underlying_cusip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    backing_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    multiplier: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    circulating_supply: Mapped[Decimal | None] = mapped_column(Numeric(40, 12), nullable=True)
    total_supply: Mapped[Decimal | None] = mapped_column(Numeric(40, 12), nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_derivative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deployments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    collateral: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    corporate_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    instrument: Mapped["Instrument"] = relationship(
        foreign_keys=[instrument_id], back_populates="tokenized_asset_detail"
    )
    underlying_instrument: Mapped["Instrument | None"] = relationship(foreign_keys=[underlying_instrument_id])
