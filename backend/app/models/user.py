from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    """
    Application user account.
    All user-owned resources (drawings, alerts, presets, screeners, watchlists)
    carry a user_id FK pointing here.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships to user-owned resources
    drawings: Mapped[list["ChartDrawing"]] = relationship(back_populates="user")
    price_alerts: Mapped[list["PriceAlert"]] = relationship(back_populates="user")
    indicator_alerts: Mapped[list["IndicatorAlert"]] = relationship(back_populates="user")
    indicator_presets: Mapped[list["IndicatorPreset"]] = relationship(back_populates="user")
    screener_definitions: Mapped[list["ScreenerDefinition"]] = relationship(back_populates="user")
    screener_alerts: Mapped[list["ScreenerAlert"]] = relationship(back_populates="user")
    watchlists: Mapped[list["Watchlist"]] = relationship(back_populates="user")
    instrument_indicator_configs: Mapped[list["InstrumentIndicatorConfig"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
