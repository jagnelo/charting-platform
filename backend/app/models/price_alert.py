import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AlertCondition(str, enum.Enum):
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    TOUCHES = "touches"
    PERCENT_CHANGE_UP = "percent_change_up"
    PERCENT_CHANGE_DOWN = "percent_change_down"


class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    PAUSED = "paused"
    EXPIRED = "expired"


class PriceAlert(Base, TimestampMixin):
    """Raw price alert. Belongs to a user and an instrument."""

    __tablename__ = "price_alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )

    condition: Mapped[AlertCondition] = mapped_column(SAEnum(AlertCondition), nullable=False)
    threshold_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus), nullable=False, default=AlertStatus.ACTIVE, index=True
    )
    repeat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_known_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    last_notification_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user: Mapped["User"] = relationship(back_populates="price_alerts")
    instrument: Mapped["Instrument"] = relationship(back_populates="price_alerts")

    def __repr__(self) -> str:
        return f"<PriceAlert id={self.id} user_id={self.user_id} {self.condition} {self.threshold_price}>"
