"""Audit trail of duplicate instruments folded into a canonical row."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.market_data_foundation import BIGINT_ID


class InstrumentMergeLog(Base):
    """One duplicate instrument id that was merged into a canonical id.

    Deliberately has no foreign keys: the duplicate row no longer exists and a
    canonical row may itself be merged later. Following ``canonical`` through
    this table resolves any retired instrument id to its surviving id.
    """

    __tablename__ = "instrument_merge_log"
    __table_args__ = (
        Index("uq_instrument_merge_log_duplicate", "duplicate_instrument_id", unique=True),
        Index("ix_instrument_merge_log_canonical", "canonical_instrument_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, primary_key=True, autoincrement=True)
    duplicate_instrument_id: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_instrument_id: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    merged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
