"""add strategy lab tables

Revision ID: d0e1f2a3b4c5
Revises: c2d3e4f5a6b7
Create Date: 2026-05-10 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_definition",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("definition_type", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_strategy_definition_user_name"),
    )
    op.create_index("ix_strategy_definition_user_id", "strategy_definition", ["user_id"])

    op.create_table(
        "strategy_version",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategy_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("engine_type", sa.String(length=32), nullable=False),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("parameter_schema", sa.JSON(), nullable=False),
        sa.Column("default_parameters", sa.JSON(), nullable=False),
        sa.Column("universe_config", sa.JSON(), nullable=False),
        sa.Column("benchmark_config", sa.JSON(), nullable=False),
        sa.Column("execution_model", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("strategy_id", "version_number", name="uq_strategy_version_number"),
    )
    op.create_index("ix_strategy_version_strategy_id", "strategy_version", ["strategy_id"])

    op.create_table(
        "strategy_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategy_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_version_id",
            sa.Integer(),
            sa.ForeignKey("strategy_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engine_type", sa.String(length=32), nullable=False),
        sa.Column("test_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameter_values", sa.JSON(), nullable=False),
        sa.Column("universe_config", sa.JSON(), nullable=False),
        sa.Column("benchmark_config", sa.JSON(), nullable=False),
        sa.Column("execution_assumptions", sa.JSON(), nullable=False),
        sa.Column("engine_run_ref", sa.String(length=120), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("artifact_manifest", sa.JSON(), nullable=False),
        sa.Column("warning_log", sa.JSON(), nullable=False),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_strategy_run_strategy_id", "strategy_run", ["strategy_id"])
    op.create_index("ix_strategy_run_strategy_version_id", "strategy_run", ["strategy_version_id"])
    op.create_index("ix_strategy_run_requested_by_user_id", "strategy_run", ["requested_by_user_id"])
    op.create_index("ix_strategy_run_engine_run_ref", "strategy_run", ["engine_run_ref"])


def downgrade() -> None:
    op.drop_index("ix_strategy_run_engine_run_ref", table_name="strategy_run")
    op.drop_index("ix_strategy_run_requested_by_user_id", table_name="strategy_run")
    op.drop_index("ix_strategy_run_strategy_version_id", table_name="strategy_run")
    op.drop_index("ix_strategy_run_strategy_id", table_name="strategy_run")
    op.drop_table("strategy_run")
    op.drop_index("ix_strategy_version_strategy_id", table_name="strategy_version")
    op.drop_table("strategy_version")
    op.drop_index("ix_strategy_definition_user_id", table_name="strategy_definition")
    op.drop_table("strategy_definition")
