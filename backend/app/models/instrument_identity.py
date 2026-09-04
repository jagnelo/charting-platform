import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.provider_runtime import ProviderCapability


class InstrumentIdentifierType(str, enum.Enum):
    ISIN = "isin"
    FIGI = "figi"
    COMPOSITE_FIGI = "composite_figi"
    CUSIP = "cusip"
    SEDOL = "sedol"
    LEI = "lei"
    CIK = "cik"
    INTERNAL = "internal"


class InstrumentIdentifier(Base, TimestampMixin):
    """Canonical, provider-agnostic identifier assigned to an instrument."""

    __tablename__ = "instrument_identifier"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id"), nullable=True, index=True
    )
    identifier_type: Mapped[InstrumentIdentifierType] = mapped_column(
        SAEnum(InstrumentIdentifierType), nullable=False, index=True
    )
    identifier_value: Mapped[str] = mapped_column(String(80), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="identifiers")
    data_source: Mapped["DataSource"] = relationship(back_populates="instrument_identifiers")

    __table_args__ = (
        UniqueConstraint(
            "identifier_type", "identifier_value", name="uq_instrument_identifier_type_value"
        ),
    )


class InstrumentProviderSymbol(Base, TimestampMixin):
    """Provider-specific symbol/metadata binding for a canonical instrument."""

    __tablename__ = "instrument_provider_symbol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id"), nullable=False, index=True
    )
    provider_symbol: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_exchange_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider_instrument_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    instrument: Mapped["Instrument"] = relationship(back_populates="provider_symbols")
    data_source: Mapped["DataSource"] = relationship(back_populates="provider_symbols")

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "provider_exchange_code",
            name="uq_instrument_provider_symbol",
        ),
    )


class InstrumentProviderCapabilityStatus(Base, TimestampMixin):
    """Dynamic support memory for a provider capability on a canonical instrument."""

    __tablename__ = "instrument_provider_capability_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[ProviderCapability] = mapped_column(
        SAEnum(ProviderCapability), nullable=False, index=True
    )
    support_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    instrument: Mapped["Instrument"] = relationship()
    data_source: Mapped["DataSource"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "capability",
            name="uq_instrument_provider_capability_status",
        ),
    )
