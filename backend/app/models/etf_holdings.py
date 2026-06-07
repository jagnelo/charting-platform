from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ETFProfile(Base, TimestampMixin):
    """ETF-specific identity and adapter routing metadata for a canonical instrument."""

    __tablename__ = "etf_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    issuer: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    sponsor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fund_family: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    index_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sec_cik: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    sec_series_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sec_class_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    adapter_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    adapter_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    adapter_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unresolved", index=True
    )
    provider_aliases: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    legal_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    instrument: Mapped["Instrument"] = relationship()
    snapshots: Mapped[list["ETFHoldingsSnapshot"]] = relationship(
        back_populates="etf_profile", cascade="all, delete-orphan"
    )
    adapter_states: Mapped[list["ETFHoldingsAdapterState"]] = relationship(
        back_populates="etf_profile", cascade="all, delete-orphan"
    )
    backfill_jobs: Mapped[list["ETFHoldingsBackfillJob"]] = relationship(
        back_populates="etf_profile", cascade="all, delete-orphan"
    )
    backfill_filings: Mapped[list["ETFHoldingsBackfillFiling"]] = relationship(
        back_populates="etf_profile", cascade="all, delete-orphan"
    )


class ETFHoldingsRawArtifact(Base, TimestampMixin):
    """Raw issuer/API/SEC artifact retained so parsed holdings can be audited or replayed."""

    __tablename__ = "etf_holdings_raw_artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    composition_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    payload_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    legal_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    etf_profile: Mapped["ETFProfile"] = relationship()
    data_source: Mapped["DataSource | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "etf_profile_id",
            "source_kind",
            "content_hash",
            name="uq_etf_holdings_raw_artifact_hash",
        ),
    )


class ETFHoldingsSnapshot(Base, TimestampMixin):
    """A dated ETF composition snapshot with source/provenance timing metadata."""

    __tablename__ = "etf_holdings_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_artifact_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("etf_holdings_raw_artifact.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    composition_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(180), nullable=True)
    source_quality: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    completeness_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    snapshot_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    etf_profile: Mapped["ETFProfile"] = relationship(back_populates="snapshots")
    source_artifact: Mapped["ETFHoldingsRawArtifact | None"] = relationship()
    data_source: Mapped["DataSource | None"] = relationship()
    rows: Mapped[list["ETFHolding"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="ETFHolding.position"
    )

    __table_args__ = (
        UniqueConstraint(
            "etf_profile_id",
            "composition_date",
            "provenance",
            "source_provider",
            "snapshot_hash",
            name="uq_etf_holdings_snapshot_version",
        ),
        Index(
            "ix_etf_holdings_snapshot_latest",
            "etf_profile_id",
            "composition_date",
            "known_at",
        ),
    )


class ETFHolding(Base, TimestampMixin):
    """One raw/canonical holding row inside an ETF holdings snapshot."""

    __tablename__ = "etf_holding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_holdings_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    constituent_instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reported_symbol: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    reported_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cusip: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    sedol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    shares: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(80), nullable=True)
    holding_type: Mapped[str] = mapped_column(String(40), nullable=False, default="equity")
    row_type: Mapped[str] = mapped_column(String(40), nullable=False, default="security")
    source_row_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_row_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolution_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    snapshot: Mapped["ETFHoldingsSnapshot"] = relationship(back_populates="rows")
    constituent_instrument: Mapped["Instrument | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_row_hash", name="uq_etf_holding_snapshot_row_hash"),
        Index("ix_etf_holding_snapshot_weight", "snapshot_id", "weight"),
        Index("ix_etf_holding_snapshot_resolved", "snapshot_id", "is_resolved"),
    )


class ETFHoldingsAdapterState(Base, TimestampMixin):
    """Per-ETF health/status memory for issuer/SEC holdings adapters."""

    __tablename__ = "etf_holdings_adapter_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="SET NULL"), nullable=True, index=True
    )
    adapter_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(180), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unresolved_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    composition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completeness_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rate_limit_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    etf_profile: Mapped["ETFProfile"] = relationship(back_populates="adapter_states")
    data_source: Mapped["DataSource | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "etf_profile_id", "adapter_key", name="uq_etf_holdings_adapter_state"
        ),
    )


class ETFHoldingsBackfillJob(Base, TimestampMixin):
    """Auditable SEC/issuer backfill run for ETF holdings reconstruction."""

    __tablename__ = "etf_holdings_backfill_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    max_filings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    etf_profile: Mapped["ETFProfile"] = relationship(back_populates="backfill_jobs")
    requested_by_user: Mapped["User | None"] = relationship()
    filings: Mapped[list["ETFHoldingsBackfillFiling"]] = relationship(
        back_populates="last_job", order_by="ETFHoldingsBackfillFiling.filing_date.desc()"
    )

    __table_args__ = (
        Index(
            "ix_etf_holdings_backfill_job_profile_started",
            "etf_profile_id",
            "started_at",
        ),
    )


class ETFHoldingsBackfillFiling(Base, TimestampMixin):
    """Persistent accession-level state so SEC backfills can dedupe and explain work."""

    __tablename__ = "etf_holdings_backfill_filing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("etf_holdings_backfill_job.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("etf_holdings_snapshot.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accession_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    form: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    acceptance_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    primary_document: Mapped[str | None] = mapped_column(String(260), nullable=True)
    filing_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    etf_profile: Mapped["ETFProfile"] = relationship(back_populates="backfill_filings")
    last_job: Mapped["ETFHoldingsBackfillJob | None"] = relationship(back_populates="filings")
    snapshot: Mapped["ETFHoldingsSnapshot | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "etf_profile_id",
            "accession_number",
            name="uq_etf_holdings_backfill_filing_accession",
        ),
        Index(
            "ix_etf_holdings_backfill_filing_profile_status",
            "etf_profile_id",
            "status",
        ),
    )


class ETFIndexProxyMapping(Base, TimestampMixin):
    """Explicit user-visible mapping between ETF holdings and an intended index proxy."""

    __tablename__ = "etf_index_proxy_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    etf_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    index_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    proxy_symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    etf_profile: Mapped["ETFProfile"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "etf_profile_id",
            "index_name",
            name="uq_etf_index_proxy_mapping_profile_index",
        ),
    )
