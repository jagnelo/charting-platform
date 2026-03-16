from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

# Association table — watchlist ↔ instrument (many-to-many)
watchlist_instrument = Table(
    "watchlist_instrument",
    Base.metadata,
    Column(
        "watchlist_id", Integer, ForeignKey("watchlist.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "instrument_id", Integer, ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("added_at", DateTime(timezone=True)),
    Column("notes", Text, nullable=True),
    Column("sort_order", Integer, default=0),
)


class Watchlist(Base, TimestampMixin):
    """A user's named list of instruments to track."""

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="watchlists")
    instruments: Mapped[list["Instrument"]] = relationship(secondary=watchlist_instrument)

    def __repr__(self) -> str:
        return f"<Watchlist id={self.id} user_id={self.user_id} name={self.name}>"
