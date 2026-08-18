"""Durable provider-backed benchmark-family holdings refresh runs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class BenchmarkFamilyHoldingsRefreshRun(Base, TimestampMixin):
    """Admin-owned bounded holdings backfill with resumable progress."""

    __tablename__ = "benchmark_family_holdings_refresh_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    roles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requested_dates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refreshed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    progress: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
