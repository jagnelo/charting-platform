"""add immutable unified code and research persistence

Revision ID: d1a2b3c4d5e6
Revises: c0a1b2c3d4e5
Create Date: 2026-07-29 21:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1a2b3c4d5e6"
down_revision: str | None = "c0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "code_asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "stable_key", name="uq_code_asset_user_key"),
    )
    op.create_index("ix_code_asset_user_id", "code_asset", ["user_id"])
    op.create_table(
        "code_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_asset_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("output_contract", sa.String(32), nullable=False),
        sa.Column("parameter_schema", sa.JSON(), nullable=False),
        sa.Column("default_parameters", sa.JSON(), nullable=False),
        sa.Column("sdk_version", sa.String(32), nullable=False),
        sa.Column("runtime_version", sa.String(32), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("lookback", sa.Integer(), nullable=True),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["code_asset_id"], ["code_asset.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("code_asset_id", "version_number", name="uq_code_version_number"),
    )
    op.create_index("ix_code_version_code_asset_id", "code_version", ["code_asset_id"])
    op.create_table(
        "research_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_version_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("run_config", sa.JSON(), nullable=False),
        sa.Column("dataset_manifest", sa.JSON(), nullable=False),
        sa.Column("reproducibility_hash", sa.String(128), nullable=True),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("resource_usage", sa.JSON(), nullable=False),
        sa.Column("logs", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_version.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_research_run_user_id", "research_run", ["user_id"])
    op.create_index("ix_research_run_code_version_id", "research_run", ["code_version_id"])
    op.create_index("ix_research_run_reproducibility_hash", "research_run", ["reproducibility_hash"])
    op.create_table(
        "research_artifact",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(48), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_run.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_artifact_research_run_id", "research_artifact", ["research_run_id"])


def downgrade() -> None:
    op.drop_index("ix_research_artifact_research_run_id", table_name="research_artifact")
    op.drop_table("research_artifact")
    op.drop_index("ix_research_run_reproducibility_hash", table_name="research_run")
    op.drop_index("ix_research_run_code_version_id", table_name="research_run")
    op.drop_index("ix_research_run_user_id", table_name="research_run")
    op.drop_table("research_run")
    op.drop_index("ix_code_version_code_asset_id", table_name="code_version")
    op.drop_table("code_version")
    op.drop_index("ix_code_asset_user_id", table_name="code_asset")
    op.drop_table("code_asset")
