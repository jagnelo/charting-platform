"""Durable maintenance runs for canonical watchlist history hydration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class WatchlistHistoryRefreshRun(Base, TimestampMixin):
    """User-scoped, bounded history hydration request.

    The run stores the resolved selection and membership versions so a later
    status/cancellation request remains auditable even if a source changes.
    Individual instrument jobs remain idempotent and provider-neutral.
    """

    __tablename__ = "watchlist_history_refresh_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeframes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    membership_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    instrument_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_instruments: Mapped[int] = mapped_column(Integer, nullable=False)
    available_instrument_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_instrument_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    already_queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    progress: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
