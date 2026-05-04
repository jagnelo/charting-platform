from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AlertFiringEvent(Base, TimestampMixin):
    """
    Persisted record of every alert firing — an instrument-associated timeseries.

    alert_type: "price" | "indicator" | "screener"
    alert_id  : logical reference to the originating alert (not a FK; alert may be deleted)
    condition_snapshot: JSON-encoded snapshot of the condition at fire time for display
    deleted_at: soft delete — NULL means visible; set to exclude from chart/inbox
    """

    __tablename__ = "alert_firing_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True, index=True
    )

    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    trigger_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    condition_snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # JSON

    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instrument: Mapped["Instrument | None"] = relationship()  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return f"<AlertFiringEvent id={self.id} type={self.alert_type} alert_id={self.alert_id}>"
