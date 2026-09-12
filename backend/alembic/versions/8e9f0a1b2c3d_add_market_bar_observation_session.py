"""Add session scope to provider bar observations."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8e9f0a1b2c3d"
down_revision: str | None = "7d8e9f0a1b2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_bar_observation",
        sa.Column("session", sa.String(length=16), nullable=False, server_default="regular"),
    )


def downgrade() -> None:
    op.drop_column("market_bar_observation", "session")
