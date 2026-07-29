"""Persistent state for the TC2000-style workstation and research library."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.instrument import Instrument


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    tabs: Mapped[list[WorkspaceTab]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", order_by="WorkspaceTab.position"
    )


class WorkspaceTab(Base, TimestampMixin):
    __tablename__ = "workspace_tab"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspace.id", ondelete="CASCADE"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layout_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active_window_key: Mapped[str | None] = mapped_column(String(80), nullable=True)

    workspace: Mapped[Workspace] = relationship(back_populates="tabs")
    windows: Mapped[list[WorkspaceWindow]] = relationship(
        back_populates="tab", cascade="all, delete-orphan", order_by="WorkspaceWindow.position"
    )

    __table_args__ = (UniqueConstraint("workspace_id", "stable_key", name="uq_workspace_tab_key"),)


class WorkspaceWindow(Base, TimestampMixin):
    __tablename__ = "workspace_window"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tab_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspace_tab.id", ondelete="CASCADE"), index=True
    )
    instance_key: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    link_group: Mapped[str] = mapped_column(String(24), nullable=False, default="blue")
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    style: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tab: Mapped[WorkspaceTab] = relationship(back_populates="windows")

    __table_args__ = (UniqueConstraint("tab_id", "instance_key", name="uq_workspace_window_key"),)


class WorkspaceLibraryItem(Base, TimestampMixin):
    __tablename__ = "workspace_library_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    stable_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dependency_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("user_id", "kind", "stable_key", name="uq_library_item_key"),)


class InstrumentNote(Base, TimestampMixin):
    __tablename__ = "instrument_note"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True)
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (UniqueConstraint("user_id", "instrument_id", name="uq_instrument_note_user"),)


class MarketGroup(Base, TimestampMixin):
    __tablename__ = "market_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stable_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    group_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("market_group.id"), nullable=True)
    representative_instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True
    )
    equal_weight_instrument_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="curated")
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list[MarketGroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="MarketGroupMember.position"
    )
    proxies: Mapped[list[MarketGroupProxy]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class MarketGroupMember(Base, TimestampMixin):
    __tablename__ = "market_group_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("market_group.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instrument.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(48), nullable=False, default="constituent")
    weight: Mapped[float | None] = mapped_column(nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="curated")
    verification_state: Mapped[str] = mapped_column(String(40), nullable=False, default="unverified")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    group: Mapped[MarketGroup] = relationship(back_populates="members")
    instrument: Mapped[Instrument] = relationship(foreign_keys=[instrument_id])

    __table_args__ = (
        Index("ix_market_group_member_time", "market_group_id", "effective_at", "known_at"),
    )


class MarketGroupProxy(Base, TimestampMixin):
    __tablename__ = "market_group_proxy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("market_group.id", ondelete="CASCADE"), index=True
    )
    instrument_id: Mapped[int] = mapped_column(Integer, ForeignKey("instrument.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(48), nullable=False, default="industry_proxy")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="curated")
    verification_state: Mapped[str] = mapped_column(String(40), nullable=False, default="unverified")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    group: Mapped[MarketGroup] = relationship(back_populates="proxies")
    instrument: Mapped[Instrument] = relationship(foreign_keys=[instrument_id])

    __table_args__ = (UniqueConstraint("market_group_id", "instrument_id", name="uq_market_group_proxy"),)
