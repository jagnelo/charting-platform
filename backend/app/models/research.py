"""Immutable unified-Python assets and reproducible Study Lab persistence."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class CodeAssetKind(str, enum.Enum):
    PLOT = "plot"
    COLUMN = "column"
    CONDITION = "condition"
    SIGNAL = "signal"
    STUDY = "study"


class ResearchRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class CodeAsset(Base, TimestampMixin):
    __tablename__ = "code_asset"
    __table_args__ = (UniqueConstraint("user_id", "stable_key", name="uq_code_asset_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    stable_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    versions: Mapped[list[CodeVersion]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class CodeVersion(Base, TimestampMixin):
    __tablename__ = "code_version"
    __table_args__ = (
        UniqueConstraint("code_asset_id", "version_number", name="uq_code_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_asset_id: Mapped[int] = mapped_column(
        ForeignKey("code_asset.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    output_contract: Mapped[str] = mapped_column(String(32), nullable=False)
    output_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parameter_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    default_parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sdk_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    runtime_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    dependencies: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lookback: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diagnostics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    asset: Mapped[CodeAsset] = relationship(back_populates="versions")


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    code_version_id: Mapped[int] = mapped_column(
        ForeignKey("code_version.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ResearchRunStatus.QUEUED.value
    )
    run_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dataset_manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reproducibility_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    diagnostics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resource_usage: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    logs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    code_version: Mapped[CodeVersion] = relationship()
    artifacts: Mapped[list[ResearchArtifact]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ResearchArtifact(Base, TimestampMixin):
    __tablename__ = "research_artifact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    research_run_id: Mapped[int] = mapped_column(
        ForeignKey("research_run.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run: Mapped[ResearchRun] = relationship(back_populates="artifacts")
