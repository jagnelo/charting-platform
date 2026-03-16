from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.ohlcv import Timeframe
from app.models.price_alert import AlertStatus


class IndicatorAlertCondition(str):
    """
    Condition operators for indicator alerts.
    Defined as constants rather than enum for forward extensibility.
    """

    GT = "gt"  # indicator value > threshold
    LT = "lt"  # indicator value < threshold
    GTE = "gte"
    LTE = "lte"
    CROSSES_ABOVE = "crosses_above"  # value was below threshold, now above
    CROSSES_BELOW = "crosses_below"  # value was above threshold, now below


class IndicatorAlert(Base, TimestampMixin):
    """
    An alert that triggers based on a computed indicator value rather than raw price.

    Examples:
      RSI(14) on H1 crosses below 30
      EMA(50) on D1 crosses above EMA(200) on D1  — "golden cross"
      Close > VWAP                                 — price vs indicator
      MACD histogram > 0                           — indicator vs fixed value

    Two comparison modes:
      1. indicator_a vs threshold_value  (e.g. RSI < 30)
      2. indicator_a vs indicator_b       (e.g. EMA50 crosses EMA200)

    indicator_a_type / indicator_b_type must match a key in INDICATOR_REGISTRY.
    indicator_a_params / indicator_b_params are passed to the computation function.
    """

    __tablename__ = "indicator_alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(SAEnum(Timeframe), nullable=False)

    # Primary indicator (always required)
    indicator_a_type: Mapped[str] = mapped_column(String(30), nullable=False)
    indicator_a_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Comparison condition
    condition: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # IndicatorAlertCondition values

    # Mode 1: compare indicator_a value to a fixed numeric threshold
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    # Mode 2: compare indicator_a to another indicator's value
    indicator_b_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    indicator_b_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Alert behaviour
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(AlertStatus), nullable=False, default=AlertStatus.ACTIVE, index=True
    )
    repeat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trigger tracking
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_value_a: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    last_value_b: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    last_notification_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user: Mapped["User"] = relationship(back_populates="indicator_alerts")
    instrument: Mapped["Instrument"] = relationship(back_populates="indicator_alerts")

    def __repr__(self) -> str:
        return (
            f"<IndicatorAlert id={self.id} user_id={self.user_id} "
            f"{self.indicator_a_type} {self.condition} "
            f"{self.threshold_value or self.indicator_b_type}>"
        )
