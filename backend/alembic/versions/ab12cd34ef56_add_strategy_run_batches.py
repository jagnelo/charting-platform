"""add strategy run batches

Revision ID: ab12cd34ef56
Revises: d0e1f2a3b4c5
Create Date: 2026-05-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ab12cd34ef56"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("strategy_run_batch"):
        op.create_table(
            "strategy_run_batch",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
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
            sa.Column("label", sa.String(length=160), nullable=True),
            sa.Column("test_mode", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("parameter_dimensions", sa.JSON(), nullable=False),
            sa.Column("parameter_grid", sa.JSON(), nullable=False),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_batch_indexes = {
        index["name"] for index in inspector.get_indexes("strategy_run_batch")
    }
    for index_name, columns in [
        ("ix_strategy_run_batch_strategy_id", ["strategy_id"]),
        ("ix_strategy_run_batch_strategy_version_id", ["strategy_version_id"]),
        ("ix_strategy_run_batch_requested_by_user_id", ["requested_by_user_id"]),
    ]:
        if index_name not in existing_batch_indexes:
            op.create_index(index_name, "strategy_run_batch", columns)

    strategy_run_columns = {column["name"] for column in inspector.get_columns("strategy_run")}
    if "run_batch_id" not in strategy_run_columns:
        op.add_column(
            "strategy_run",
            sa.Column(
                "run_batch_id",
                sa.Integer(),
                sa.ForeignKey("strategy_run_batch.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "parameter_diff" not in strategy_run_columns:
        op.add_column(
            "strategy_run",
            sa.Column("parameter_diff", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
        op.alter_column("strategy_run", "parameter_diff", server_default=None)

    existing_run_indexes = {index["name"] for index in inspector.get_indexes("strategy_run")}
    if "ix_strategy_run_run_batch_id" not in existing_run_indexes:
        op.create_index("ix_strategy_run_run_batch_id", "strategy_run", ["run_batch_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("strategy_run"):
        existing_run_indexes = {index["name"] for index in inspector.get_indexes("strategy_run")}
        if "ix_strategy_run_run_batch_id" in existing_run_indexes:
            op.drop_index("ix_strategy_run_run_batch_id", table_name="strategy_run")
        strategy_run_columns = {column["name"] for column in inspector.get_columns("strategy_run")}
        if "parameter_diff" in strategy_run_columns:
            op.drop_column("strategy_run", "parameter_diff")
        if "run_batch_id" in strategy_run_columns:
            op.drop_column("strategy_run", "run_batch_id")

    if inspector.has_table("strategy_run_batch"):
        existing_batch_indexes = {
            index["name"] for index in inspector.get_indexes("strategy_run_batch")
        }
        for index_name in [
            "ix_strategy_run_batch_requested_by_user_id",
            "ix_strategy_run_batch_strategy_version_id",
            "ix_strategy_run_batch_strategy_id",
        ]:
            if index_name in existing_batch_indexes:
                op.drop_index(index_name, table_name="strategy_run_batch")
        op.drop_table("strategy_run_batch")
