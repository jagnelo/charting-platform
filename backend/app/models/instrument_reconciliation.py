from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class InstrumentReconciliationIssue(Base, TimestampMixin):
    """Durable queue for provider observations that cannot be safely reconciled."""

    __tablename__ = "instrument_reconciliation_issue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("data_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_symbol: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    data_source: Mapped["DataSource"] = relationship()
    resolved_by: Mapped["User | None"] = relationship(foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "issue_type",
            "fingerprint",
            name="uq_instrument_reconciliation_issue_identity",
        ),
    )
