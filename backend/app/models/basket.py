from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Basket(Base, TimestampMixin):
    """Weighted instrument collection usable as a reusable universe building block."""

    __tablename__ = "basket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    weighting_scheme: Mapped[str] = mapped_column(
        String(40), nullable=False, default="custom", index=True
    )
    rebalance_frequency: Mapped[str | None] = mapped_column(String(40), nullable=True)
    classification_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    source_etf_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("etf_profile.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("etf_holdings_snapshot.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    composition_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_system_managed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    user: Mapped["User | None"] = relationship()
    source_etf_profile: Mapped["ETFProfile | None"] = relationship()
    source_snapshot: Mapped["ETFHoldingsSnapshot | None"] = relationship()
    members: Mapped[list["BasketMember"]] = relationship(
        back_populates="basket",
        cascade="all, delete-orphan",
        order_by="BasketMember.position",
    )
    snapshots: Mapped[list["BasketSnapshot"]] = relationship(
        back_populates="basket",
        cascade="all, delete-orphan",
        order_by="BasketSnapshot.composition_date",
    )

    __table_args__ = (
        Index("ix_basket_user_source", "user_id", "source_type"),
        UniqueConstraint(
            "user_id",
            "name",
            name="uq_basket_user_name",
        ),
    )


class BasketMember(Base, TimestampMixin):
    """One weighted instrument membership row inside a basket."""

    __tablename__ = "basket_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("basket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_holding_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("etf_holding.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    basket: Mapped["Basket"] = relationship(back_populates="members")
    instrument: Mapped["Instrument"] = relationship()
    source_holding: Mapped["ETFHolding | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("basket_id", "instrument_id", name="uq_basket_member_instrument"),
        Index("ix_basket_member_weight", "basket_id", "weight"),
    )


class BasketSnapshot(Base, TimestampMixin):
    """Point-in-time basket composition for dynamic basket universe replay."""

    __tablename__ = "basket_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("basket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    composition_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    known_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    source_snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("etf_holdings_snapshot.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    basket: Mapped["Basket"] = relationship(back_populates="snapshots")
    source_snapshot: Mapped["ETFHoldingsSnapshot | None"] = relationship()
    members: Mapped[list["BasketSnapshotMember"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="BasketSnapshotMember.position",
    )

    __table_args__ = (
        Index("ix_basket_snapshot_basket_date", "basket_id", "composition_date"),
        Index("ix_basket_snapshot_source", "basket_id", "source_snapshot_id"),
    )


class BasketSnapshotMember(Base, TimestampMixin):
    """One instrument membership row in a point-in-time basket snapshot."""

    __tablename__ = "basket_snapshot_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    basket_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("basket_snapshot.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("instrument.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_holding_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("etf_holding.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    snapshot: Mapped["BasketSnapshot"] = relationship(back_populates="members")
    instrument: Mapped["Instrument"] = relationship()
    source_holding: Mapped["ETFHolding | None"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "basket_snapshot_id",
            "instrument_id",
            name="uq_basket_snapshot_member_instrument",
        ),
        Index("ix_basket_snapshot_member_weight", "basket_snapshot_id", "weight"),
    )
