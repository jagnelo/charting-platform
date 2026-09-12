"""add durable refresh-job lease tokens"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6c7d8e9f0a1b"
down_revision: str | None = "5b6c7d8e9f0a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_refresh_job",
        sa.Column("lease_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_market_refresh_job_lease_token",
        "market_refresh_job",
        ["lease_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_refresh_job_lease_token", table_name="market_refresh_job")
    op.drop_column("market_refresh_job", "lease_token")
