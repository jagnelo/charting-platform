import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ProviderCapability(str, enum.Enum):
    INSTRUMENT_SEARCH = "instrument_search"
    INSTRUMENT_METADATA = "instrument_metadata"
    PRICE_HISTORY = "price_history"
    LATEST_PRICE = "latest_price"
    INSTRUMENT_EVENTS = "instrument_events"
    INSTRUMENT_IDENTIFIERS = "instrument_identifiers"
    UNIVERSE_DISCOVERY = "universe_discovery"
    OPTION_CHAIN = "option_chain"
    OPTION_QUOTE_HISTORY = "option_quote_history"


class ProviderPolicy(Base, TimestampMixin):
    __tablename__ = "provider_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[ProviderCapability] = mapped_column(
        SAEnum(ProviderCapability), nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_weight_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    base_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    tokens_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    burst_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    freshness_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    score_floor: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    score_ceiling: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("100")
    )
    learned_weight: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
    effective_score: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )

    data_source: Mapped["DataSource"] = relationship(back_populates="provider_policies")

    __table_args__ = (
        UniqueConstraint(
            "data_source_id", "capability", name="uq_provider_policy_source_capability"
        ),
        Index(
            "ix_provider_policy_capability_rank",
            "capability",
            "is_enabled",
            "is_pinned",
            "effective_score",
            "base_priority",
        ),
    )


class ProviderHealthState(Base, TimestampMixin):
    __tablename__ = "provider_health_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[ProviderCapability] = mapped_column(
        SAEnum(ProviderCapability), nullable=False, index=True
    )
    failure_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    circuit_open_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ewma_latency_ms: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    ewma_success_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("1")
    )
    ewma_completeness: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("1")
    )
    ewma_freshness: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("1")
    )
    ewma_consistency: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("1")
    )
    observed_score: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    last_error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    data_source: Mapped["DataSource"] = relationship(back_populates="provider_health_states")

    __table_args__ = (
        UniqueConstraint(
            "data_source_id", "capability", name="uq_provider_health_state_source_capability"
        ),
    )


class ProviderRequestLog(Base, TimestampMixin):
    __tablename__ = "provider_request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    capability: Mapped[ProviderCapability] = mapped_column(
        SAEnum(ProviderCapability), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    operation_family: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usage_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="call_count")
    usage_unit_label: Mapped[str] = mapped_column(String(24), nullable=False, default="requests")
    usage_units: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("1")
    )
    response_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    data_source: Mapped["DataSource"] = relationship(back_populates="provider_request_logs")
    instrument: Mapped["Instrument | None"] = relationship()

    __table_args__ = (
        Index("ix_provider_request_log_capability_requested", "capability", "requested_at"),
        Index("ix_provider_request_log_source_requested", "data_source_id", "requested_at"),
    )
