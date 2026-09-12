"""Persist radar coverage outcome separately from execution status."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4a5b6c7d8e9f"
down_revision: str | None = "3e4f5a6b7c8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_run") as batch:
        batch.add_column(
            sa.Column(
                "coverage_status",
                sa.String(length=24),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.add_column(
            sa.Column(
                "coverage_total_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "coverage_missing_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(sa.Column("coverage_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("radar_run") as batch:
        batch.drop_column("coverage_summary")
        batch.drop_column("coverage_missing_count")
        batch.drop_column("coverage_total_count")
        batch.drop_column("coverage_status")
