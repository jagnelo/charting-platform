from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Dashboard(Base, TimestampMixin):
    """User-owned dashboard/workspace container."""

    __tablename__ = "dashboard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user: Mapped["User"] = relationship(back_populates="dashboards")
    tabs: Mapped[list["DashboardTab"]] = relationship(
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardTab.position",
    )


class DashboardTab(Base, TimestampMixin):
    """Named page inside a dashboard."""

    __tablename__ = "dashboard_tab"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dashboard_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dashboard.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    layout_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="tabs")
    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="tab",
        cascade="all, delete-orphan",
        order_by="DashboardWidget.position",
    )


class DashboardWidget(Base, TimestampMixin):
    """Positioned and configured widget inside a dashboard tab."""

    __tablename__ = "dashboard_widget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tab_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dashboard_tab.id", ondelete="CASCADE"), nullable=False, index=True
    )
    widget_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    layout: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    style: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    tab: Mapped["DashboardTab"] = relationship(back_populates="widgets")
