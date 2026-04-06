from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ScreenerAlert(Base, TimestampMixin):
    """
    Notifies a user when instruments enter or leave a screener's results.

    trigger_type:
      'entered' — fire when an instrument appears in matched_ids for the first time
      'left'    — fire when an instrument disappears from matched_ids
      'both'    — fire on either event

    Diff is performed between the previous ScreenerResult.matched_ids and the
    current one each time the screener runs.

    repeat: if True, re-arms automatically after firing so that every new
            enter/leave event triggers a notification.  If False, fires once
            then status→'triggered'.
    """

    __tablename__ = "screener_alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screener_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("screener_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trigger_type: Mapped[str] = mapped_column(String(10), nullable=False, default="both")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    repeat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ID of the last ScreenerResult we evaluated this alert against.
    # Used to detect new runs and compute diffs.
    last_checked_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("screener_result.id", ondelete="SET NULL"), nullable=True
    )
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="screener_alerts")  # type: ignore[name-defined]
    screener: Mapped["ScreenerDefinition"] = relationship()  # type: ignore[name-defined]
    last_checked_result: Mapped[Optional["ScreenerResult"]] = relationship(  # type: ignore[name-defined]
        foreign_keys=[last_checked_run_id]
    )

    def __repr__(self) -> str:
        return f"<ScreenerAlert id={self.id} screener={self.screener_id} user={self.user_id} type={self.trigger_type}>"
