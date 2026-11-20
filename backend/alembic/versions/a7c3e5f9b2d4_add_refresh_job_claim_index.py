"""add partial claim index for market_refresh_job

Revision ID: a7c3e5f9b2d4
Revises: e6f7a8b9c012
Create Date: 2026-11-20 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "a7c3e5f9b2d4"
down_revision = "e6f7a8b9c012"
branch_labels = None
depends_on = None

_OPEN_STATUSES = "status IN ('queued', 'retry', 'deferred', 'leased')"


def upgrade() -> None:
    op.create_index(
        "ix_market_refresh_job_claimable",
        "market_refresh_job",
        ["priority", "next_attempt_at", "id"],
        postgresql_where=sa.text(_OPEN_STATUSES),
    )


def downgrade() -> None:
    op.drop_index("ix_market_refresh_job_claimable", table_name="market_refresh_job")
