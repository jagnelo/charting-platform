"""Provider-agnostic market-data identity, series, calendar, and telemetry models.

These tables are deliberately additive.  Existing symbol-based tables remain valid
while new ingestion can attach observations to a stable domain key and an explicit
market series (venue/feed/session/adjustment scope).
"""

import enum
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class IdentityStatus(str, enum.Enum):
    RESOLVED = "resolved"
    PROVISIONAL = "provisional"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class AdjustmentBasis(str, enum.Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"
    PROVIDER_ADJUSTED = "provider_adjusted"


class CalendarExceptionKind(str, enum.Enum):
    HOLIDAY = "holiday"
    EARLY_CLOSE = "early_close"
    LATE_OPEN = "late_open"
    CLOSED = "closed"


class Issuer(Base, TimestampMixin):
    """Legal entity that issues one or more securities."""

    __tablename__ = "issuer"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    domain_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(300), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    lei: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    instruments: Mapped[list["Instrument"]] = relationship(back_populates="issuer")


class ExchangeSessionRule(Base, TimestampMixin):
    """Versioned local-time session rule for an exchange/venue."""

    __tablename__ = "exchange_session_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exchange.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_code: Mapped[str] = mapped_column(String(24), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    closes_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    crosses_midnight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trade_date_rule: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local_open_date"
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    exchange: Mapped["Exchange"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "session_code",
            "weekday",
            "valid_from",
            name="uq_exchange_session_rule_version",
        ),
        Index("ix_exchange_session_rule_lookup", "exchange_id", "session_code", "valid_from"),
    )


class ExchangeCalendarException(Base, TimestampMixin):
    """Holiday, early-close, or ad-hoc exchange calendar override."""

    __tablename__ = "exchange_calendar_exception"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exchange.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    exception_kind: Mapped[CalendarExceptionKind] = mapped_column(nullable=False)
    session_code: Mapped[str] = mapped_column(String(24), nullable=False, default="regular")
    opens_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    closes_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    exchange: Mapped["Exchange"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "exchange_id", "session_date", "session_code", name="uq_exchange_calendar_exception"
        ),
    )


class MarketSeries(Base, TimestampMixin):
    """A uniquely scoped time series for one instrument."""

    __tablename__ = "market_series"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exchange.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feed_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="consolidated")
    session_code: Mapped[str] = mapped_column(String(24), nullable=False, default="regular")
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    adjustment_basis: Mapped[AdjustmentBasis] = mapped_column(
        nullable=False, default=AdjustmentBasis.RAW
    )
    adjustment_version: Mapped[str] = mapped_column(String(80), nullable=False, default="v1")
    is_canonical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_series_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    instrument: Mapped["Instrument"] = relationship(back_populates="market_series")
    exchange: Mapped["Exchange | None"] = relationship()
    data_source: Mapped["DataSource | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "exchange_id",
            "data_source_id",
            "feed_scope",
            "session_code",
            "timeframe",
            "adjustment_basis",
            "adjustment_version",
            name="uq_market_series_scope",
        ),
        Index("ix_market_series_instrument_lookup", "instrument_id", "timeframe", "session_code"),
    )


class MarketSeriesDefault(Base, TimestampMixin):
    """The compatibility series selected for ordinary OHLCV reads.

    A provider may expose several valid feeds for the same instrument and
    timeframe.  ``MarketSeries.is_canonical`` records eligibility, while this
    row records the one series used by legacy symbol/timeframe reads.  The
    mapping is deliberately separate so an operator can change the default
    without rewriting observations or silently deleting alternate feeds.
    """

    __tablename__ = "market_series_default"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    is_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    market_series_id: Mapped[int | None] = mapped_column(
        BIGINT_ID, ForeignKey("market_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    selection_reason: Mapped[str] = mapped_column(
        String(80), nullable=False, default="first_canonical"
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    instrument: Mapped["Instrument"] = relationship()
    market_series: Mapped[MarketSeries] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "timeframe",
            "is_adjusted",
            name="uq_market_series_default_scope",
        ),
    )


class InstrumentIdentityQuarantine(Base, TimestampMixin):
    """Candidate identity that must be reviewed before it can be merged."""

    __tablename__ = "instrument_identity_quarantine"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    proposed_domain_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    exchange_mic: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    candidate_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    instrument: Mapped["Instrument | None"] = relationship()


class ProviderQuotaWindow(Base, TimestampMixin):
    """Durable usage/capacity counter for a provider capability window."""

    __tablename__ = "provider_quota_window"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # A provider-defined budget may be shared by several capabilities.  This
    # is intentionally separate from the request capability so an account-wide
    # allowance is not multiplied when different operations use the same key.
    # Missing values are backfilled to the legacy capability key by migration.
    quota_group: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    # A provider may publish independent budgets (for example requests/minute
    # and requests/month).  Each dimension is reserved independently; routing
    # must satisfy all dimensions before selecting a provider.
    dimension: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_units: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="configured")

    data_source: Mapped["DataSource"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "quota_group",
            "dimension",
            "window_started_at",
            "window_seconds",
            name="uq_provider_quota_window",
        ),
    )


class ProviderQuotaIdentity(Base, TimestampMixin):
    """Durable distinct-identity claim inside a provider quota window.

    Some provider plans meter a monthly pool by distinct symbols rather than
    by request.  A row is retained once a request has been admitted so the
    same symbol cannot be charged as a new identity by another worker or
    after an application restart.
    """

    __tablename__ = "provider_quota_identity"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    quota_group: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )

    dimension: Mapped[str] = mapped_column(String(80), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    identity_key: Mapped[str] = mapped_column(String(180), nullable=False)

    data_source: Mapped["DataSource"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "quota_group",
            "dimension",
            "window_started_at",
            "window_seconds",
            "identity_key",
            name="uq_provider_quota_identity",
        ),
        Index(
            "ix_provider_quota_identity_lookup",
            "data_source_id",
            "quota_group",
            "dimension",
            "window_started_at",
            "window_seconds",
        ),
    )


@event.listens_for(ProviderQuotaWindow, "before_insert")
def _default_provider_quota_window_group(_mapper, _connection, target) -> None:
    """Keep direct legacy model inserts capability-scoped without a quota guess."""

    if target.quota_group is None:
        target.quota_group = str(getattr(target.capability, "value", target.capability))


@event.listens_for(ProviderQuotaIdentity, "before_insert")
def _default_provider_quota_identity_group(_mapper, _connection, target) -> None:
    """Mirror the legacy capability key for direct identity inserts."""

    if target.quota_group is None:
        target.quota_group = str(getattr(target.capability, "value", target.capability))


class ProviderWorkloadLease(Base, TimestampMixin):
    """Short-lived, observable reservation for a queued market-data workload."""

    __tablename__ = "provider_workload_lease"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    workload_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="reserved", index=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    request_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    data_source: Mapped["DataSource | None"] = relationship()


class ProviderRoutingDecision(Base):
    """Immutable explanation of provider filtering/ranking for one request."""

    __tablename__ = "provider_routing_decision"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    request_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    selected_data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True
    )
    candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rejected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    workload_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketRefreshJob(Base, TimestampMixin):
    """Coalesced queued refresh request; workers perform provider I/O outside evaluators."""

    __tablename__ = "market_refresh_job"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    request_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=True, index=True
    )
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    timeframe: Mapped[str | None] = mapped_column(String(12), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A fresh opaque token is issued for each claim. Completion/retry must
    # match both the job id and this token so a worker whose lease expired
    # cannot mutate a later worker's result.
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class MarketUniverseReconciliationRun(Base, TimestampMixin):
    """One complete provider/venue universe observation and its outcome."""

    __tablename__ = "market_universe_reconciliation_run"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="running", index=True)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deactivated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class MarketUniverseLifecycleObservation(Base, TimestampMixin):
    """Current provider observation used for conservative listing lifecycle."""

    __tablename__ = "market_universe_lifecycle_observation"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("market_universe_reconciliation_run.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    listing_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument_listing.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_symbol: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    exchange_mic: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    quote_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    consecutive_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "exchange_mic",
            "quote_type",
            name="uq_market_universe_lifecycle_observation",
        ),
        Index(
            "ix_market_universe_lifecycle_provider_status",
            "data_source_id",
            "quote_type",
            "lifecycle_status",
            "present",
        ),
    )


class MarketEvent(Base, TimestampMixin):
    """Provider-normalized market event, including issuer and venue events."""

    __tablename__ = "market_event"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    consensus_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("market_event_consensus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=True, index=True
    )
    issuer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("issuer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    consensus: Mapped["MarketEventConsensus | None"] = relationship(
        back_populates="observations",
        foreign_keys=[consensus_id],
    )

    __table_args__ = (UniqueConstraint("event_key", "source", name="uq_market_event_source_key"),)


class MarketEventConsensus(Base, TimestampMixin):
    """Conservative cross-provider event reconciliation result.

    Provider observations remain the source of truth in ``market_event``.  A
    consensus row is only a durable candidate grouping: unresolved observations
    are left ungrouped, and groups with different semantic values are marked
    ``conflicted`` rather than silently selecting one provider's value.
    """

    __tablename__ = "market_event_consensus"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    consensus_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issuer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("issuer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    announced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="single_source", index=True)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agreement_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    conflict_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    canonical_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    observations: Mapped[list[MarketEvent]] = relationship(
        back_populates="consensus",
        foreign_keys="MarketEvent.consensus_id",
    )

    __table_args__ = (
        Index(
            "ix_market_event_consensus_target_date",
            "instrument_id",
            "issuer_id",
            "effective_date",
        ),
        Index("ix_market_event_consensus_status_observed", "status", "last_observed_at"),
    )


class MarketEventPrelistingCandidate(Base, TimestampMixin):
    """Auditable provisional instrument created from a future listing event."""

    __tablename__ = "market_event_prelisting_candidate"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    candidate_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    consensus_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("market_event_consensus.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    anchor_event_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("market_event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issuer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("issuer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    proposed_symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    proposed_name: Mapped[str] = mapped_column(String(300), nullable=False)
    exchange_mic: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    expected_listing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    stable_identifiers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    consensus: Mapped["MarketEventConsensus | None"] = relationship()
    anchor_event: Mapped["MarketEvent | None"] = relationship(foreign_keys=[anchor_event_id])

    __table_args__ = (
        Index(
            "ix_market_event_prelisting_status_expected",
            "status",
            "expected_listing_date",
        ),
    )


class MarketEventScanState(Base, TimestampMixin):
    """Durable cursor for bounded provider-wide market-event scans."""

    __tablename__ = "market_event_scan_state"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    scan_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    cursor_issuer_id: Mapped[int | None] = mapped_column(
        BIGINT_ID,
        ForeignKey("issuer.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cycle_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cycle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_batch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="idle", index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_market_event_scan_provider_operation", "provider", "operation"),
    )


class FundamentalFact(Base, TimestampMixin):
    """Point-in-time raw/curated fundamental observation."""

    __tablename__ = "fundamental_fact"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    issuer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("issuer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fact_namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(160), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    filed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_fundamental_fact_point_in_time", "issuer_id", "fact_key", "filed_at"),
    )


class ShortInterestObservation(Base, TimestampMixin):
    """FINRA/provider short-interest observation with publication provenance."""

    __tablename__ = "short_interest_observation"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    short_position: Mapped[Decimal | None] = mapped_column(Numeric(30, 4), nullable=True)
    short_percent_float: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    days_to_cover: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "settlement_date", "source", name="uq_short_interest_observation"
        ),
    )


class MarketCoverageSnapshot(Base):
    """Point-in-time coverage measurement for one explicitly scoped series."""

    __tablename__ = "market_coverage_snapshot"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    market_series_id: Mapped[int | None] = mapped_column(
        BIGINT_ID, ForeignKey("market_series.id", ondelete="CASCADE"), nullable=True, index=True
    )
    timeframe: Mapped[str] = mapped_column(String(12), nullable=False)
    expected_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="unavailable", index=True
    )
    missing_slices: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "market_series_id", "timeframe", "evaluated_at", name="uq_market_coverage_snapshot"
        ),
        Index("ix_market_coverage_snapshot_evaluated", "evaluated_at"),
    )


class ProviderShadowObservation(Base):
    """Comparison evidence captured while a candidate route is still shadowed."""

    __tablename__ = "provider_shadow_observation"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    request_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    primary_data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True
    )
    alternate_data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True
    )
    comparison_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    discrepancy_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    routing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_provider_shadow_observation_observed", "observed_at"),)


class MarketDataAnomaly(Base):
    """Reviewable anomaly or provider disagreement, never silently discarded."""

    __tablename__ = "market_data_anomaly"

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    market_series_id: Mapped[int | None] = mapped_column(
        BIGINT_ID, ForeignKey("market_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anomaly_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info", index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
