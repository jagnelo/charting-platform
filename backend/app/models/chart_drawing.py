from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.ohlcv import Timeframe


class ChartDrawing(Base, TimestampMixin):
    """
    A user-defined drawing overlay on a chart for a specific instrument.
    Scoped to a timeframe, or pinned across all timeframes via pin_to_all.
    All drawings belong to a specific user.
    """

    __tablename__ = "chart_drawing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timeframe: Mapped[Timeframe | None] = mapped_column(
        SAEnum(Timeframe), nullable=True, index=True
    )
    pin_to_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    drawing_type: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    style: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="drawings")
    instrument: Mapped["Instrument"] = relationship(back_populates="drawings")

    def __repr__(self) -> str:
        return f"<ChartDrawing id={self.id} user_id={self.user_id} type={self.drawing_type}>"
