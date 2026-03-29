from sqlalchemy import JSON, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class InstrumentIndicatorConfig(Base, TimestampMixin):
    """Per-user, per-instrument indicator configuration."""

    __tablename__ = "instrument_indicator_config"
    __table_args__ = (
        UniqueConstraint("user_id", "instrument_id", name="uq_user_instrument_indicators"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False
    )
    indicators: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    user: Mapped["User"] = relationship(back_populates="instrument_indicator_configs")
    instrument: Mapped["Instrument"] = relationship()
