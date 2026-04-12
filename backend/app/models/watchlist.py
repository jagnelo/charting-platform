from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Watchlist(Base, TimestampMixin):
    """
    A user's named list of instruments to track.

    Managed watchlists (is_managed=True) are auto-populated by a screener run.
    Their items are locked — manual add/remove is blocked.  is_locked can also
    be set independently to prevent edits on a regular watchlist.
    """

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Managed / locked flags
    is_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    screener_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("screener_definition.id", ondelete="SET NULL"), nullable=True
    )
    last_screener_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        order_by="WatchlistItem.position",
    )
    screener: Mapped[Optional["ScreenerDefinition"]] = relationship(  # type: ignore[name-defined]
        foreign_keys=[screener_id]
    )

    def __repr__(self) -> str:
        return f"<Watchlist id={self.id} user_id={self.user_id} name={self.name}>"


class WatchlistItem(Base):
    """
    One instrument in a watchlist.

    left_screener_at: set when a managed watchlist's screener run no longer
    includes this instrument.  The item is kept for a 7-day grace period to
    give users visibility, then removed on the next run after the deadline.
    """

    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Grace-period tracking for managed watchlists
    left_screener_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")
    instrument: Mapped["Instrument"] = relationship()

    def __repr__(self) -> str:
        return f"<WatchlistItem watchlist={self.watchlist_id} instrument={self.instrument_id}>"
