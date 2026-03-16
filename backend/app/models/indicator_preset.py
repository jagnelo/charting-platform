from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class IndicatorPreset(Base, TimestampMixin):
    """
    A named, reusable set of technical indicators belonging to a user.

    indicators JSON structure:
    [
      { "type": "sma", "params": {"period": 20}, "style": {"color": "#ffb74d", "lineWidth": 1.5}, "pane": "main" },
      { "type": "rsi", "params": {"period": 14}, "style": {"color": "#ef9a9a", "lineWidth": 1.5}, "pane": "separate" }
    ]
    """

    __tablename__ = "indicator_preset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    indicators: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="indicator_presets")

    def __repr__(self) -> str:
        return f"<IndicatorPreset id={self.id} user_id={self.user_id} name={self.name}>"
