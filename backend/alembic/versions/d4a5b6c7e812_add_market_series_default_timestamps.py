"""Add ORM timestamp columns to the default market-series mapping.

Revision ID: d4a5b6c7e812
Revises: slv2_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4a5b6c7e812"
down_revision: str | None = "slv2_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Bring the deployed table into parity with ``TimestampMixin``."""
    op.add_column(
        "market_series_default",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "market_series_default",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove only the columns introduced by this revision."""
    op.drop_column("market_series_default", "updated_at")
    op.drop_column("market_series_default", "created_at")
