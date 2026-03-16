from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.ohlcv import Timeframe


class ScreenerDefinition(Base, TimestampMixin):
    """
    A user-defined screener that evaluates a condition tree across a universe
    of instruments and returns those that match.

    universe_type:
      'all'           — every instrument in the DB
      'watchlist'     — instruments in a specific watchlist
      'asset_class'   — all instruments of a given asset class
      'custom'        — explicit list in universe_instrument_ids

    conditions (JSON condition tree):
    {
      "operator": "AND",   // AND | OR | NOT
      "conditions": [
        {
          "type": "indicator_threshold",
          "indicator": "rsi",
          "params": {"period": 14},
          "op": "lt",          // gt | lt | gte | lte | eq
          "value": 30
        },
        {
          "type": "indicator_cross",
          "indicator_a": {"type": "ema", "params": {"period": 50}},
          "indicator_b": {"type": "ema", "params": {"period": 200}},
          "op": "crosses_above"
        },
        {
          "type": "price_threshold",
          "field": "close",    // open | high | low | close | volume
          "op": "gt",
          "value": 10.0
        },
        {
          "type": "price_change",
          "lookback_bars": 5,
          "op": "gt",
          "value": 0.03        // 3% rise over last 5 bars
        },
        {
          "operator": "OR",
          "conditions": [...]  // nested groups
        }
      ]
    }

    schedule: optional cron string for automated runs (e.g. "0 16 * * 1-5" = market close weekdays)
    """

    __tablename__ = "screener_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    universe_type: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    universe_watchlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("watchlist.id"), nullable=True
    )
    universe_asset_class_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_class.id"), nullable=True
    )
    universe_instrument_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    timeframe: Mapped[Timeframe] = mapped_column(
        SAEnum(Timeframe), nullable=False, default=Timeframe.D1
    )
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False)
    schedule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="screener_definitions")
    results: Mapped[list["ScreenerResult"]] = relationship(
        back_populates="screener", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScreenerDefinition id={self.id} user_id={self.user_id} name={self.name}>"


class ScreenerResult(Base):
    """
    Snapshot of a screener run — which instruments matched and what their
    indicator values were at the time of the run.
    """

    __tablename__ = "screener_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    screener_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("screener_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # List of instrument IDs that matched
    matched_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Per-instrument computed values at match time: { instrument_id: { "rsi": 28.4, "close": 145.2 } }
    result_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    screener: Mapped["ScreenerDefinition"] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return f"<ScreenerResult screener_id={self.screener_id} matched={len(self.matched_ids)} run_at={self.run_at}>"
