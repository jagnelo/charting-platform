"""add instrument sync run audit table

Revision ID: f3a4b5c6d7e8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("instrument_sync_run"):
        op.create_table(
            "instrument_sync_run",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("operation", sa.String(length=40), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("metrics", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("instrument_sync_run")}
    for index_name, columns in [
        ("ix_instrument_sync_run_operation", ["operation"]),
        ("ix_instrument_sync_run_source", ["source"]),
        ("ix_instrument_sync_run_status", ["status"]),
    ]:
        if index_name not in existing_indexes:
            op.create_index(index_name, "instrument_sync_run", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("instrument_sync_run"):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("instrument_sync_run")}
    for index_name in [
        "ix_instrument_sync_run_status",
        "ix_instrument_sync_run_source",
        "ix_instrument_sync_run_operation",
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="instrument_sync_run")
    op.drop_table("instrument_sync_run")
