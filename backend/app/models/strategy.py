import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class StrategySourceType(str, enum.Enum):
    CUSTOM = "custom"
    RADAR = "radar"


class StrategyDefinitionType(str, enum.Enum):
    RULES = "rules"
    DSL = "dsl"
    PYTHON = "python"
    SIGNAL_SOURCE = "signal_source"


class StrategyEngineType(str, enum.Enum):
    PLATFORM = "platform"
    NAUTILUS = "nautilus"


class StrategyTestMode(str, enum.Enum):
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    PAPER_FORWARD = "paper_forward"


class StrategyRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class StrategyDefinition(Base, TimestampMixin):
    __tablename__ = "strategy_definition"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_strategy_definition_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StrategySourceType.CUSTOM.value
    )
    definition_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StrategyDefinitionType.RULES.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    user: Mapped["User"] = relationship(back_populates="strategy_definitions")
    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by=lambda: StrategyVersion.version_number.desc(),
    )
    runs: Mapped[list["StrategyRun"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by=lambda: StrategyRun.created_at.desc(),
    )


class StrategyVersion(Base, TimestampMixin):
    __tablename__ = "strategy_version"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_number", name="uq_strategy_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StrategyEngineType.NAUTILUS.value
    )
    definition_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parameter_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    default_parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    universe_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    benchmark_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_model: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    strategy: Mapped["StrategyDefinition"] = relationship(back_populates="versions")
    runs: Mapped[list["StrategyRun"]] = relationship(
        back_populates="strategy_version",
        cascade="all, delete-orphan",
        order_by=lambda: StrategyRun.created_at.desc(),
    )


class StrategyRun(Base, TimestampMixin):
    __tablename__ = "strategy_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("strategy_definition.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("strategy_version.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine_type: Mapped[str] = mapped_column(String(32), nullable=False)
    test_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StrategyRunStatus.QUEUED.value
    )
    timeframe: Mapped[str | None] = mapped_column(String(8), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parameter_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    universe_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    benchmark_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_assumptions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    engine_run_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    result_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warning_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    strategy: Mapped["StrategyDefinition"] = relationship(back_populates="runs")
    strategy_version: Mapped["StrategyVersion"] = relationship(back_populates="runs")
    requested_by: Mapped["User"] = relationship()
