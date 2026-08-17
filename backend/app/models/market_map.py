"""Durable, provenance-aware Market Map result cache."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarketMapCache(Base):
    """Persist one immutable Market Map result per user and cache identity.

    The response is stored as JSON so a completed-session map can be reopened without
    re-running provider or database fan-out. The identity is derived from the canonical
    source membership, request semantics, and local bar watermark; a new membership or
    newly ingested bar therefore produces a new cache entry rather than mutating history.
    """

    __tablename__ = "market_map_cache"
    __table_args__ = (
        UniqueConstraint("user_id", "cache_key", name="uq_market_map_cache_user_key"),
        Index("ix_market_map_cache_user_source", "user_id", "source_id"),
        Index("ix_market_map_cache_user_computed", "user_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(String(240), nullable=False)
    membership_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    bar_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class MarketMapSnapshot(Base):
    """A user-named immutable copy of a completed Market Map result."""

    __tablename__ = "market_map_snapshot"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_market_map_snapshot_user_name"),
        Index("ix_market_map_snapshot_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_id: Mapped[str] = mapped_column(String(240), nullable=False)
    membership_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    map_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
