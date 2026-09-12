"""Persist refresh-job attempt and outcome metadata."""

import sqlalchemy as sa
from alembic import op


revision = "5f6a7b8c9d0e"
down_revision = "4e5f6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_refresh_job",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "market_refresh_job",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "market_refresh_job",
        sa.Column("result_summary", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_market_refresh_job_finished_at",
        "market_refresh_job",
        ["finished_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_refresh_job_finished_at", table_name="market_refresh_job")
    op.drop_column("market_refresh_job", "result_summary")
    op.drop_column("market_refresh_job", "finished_at")
    op.drop_column("market_refresh_job", "started_at")
