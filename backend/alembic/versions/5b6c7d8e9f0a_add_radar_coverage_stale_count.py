"""Persist stale local OHLCV count for radar coverage preflight."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5b6c7d8e9f0a"
down_revision: str | None = "4a5b6c7d8e9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_run") as batch:
        batch.add_column(
            sa.Column(
                "coverage_stale_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("radar_run") as batch:
        batch.drop_column("coverage_stale_count")
