"""Retain complete normalized availability-probe responses."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9a0b1c2e5"
down_revision: str | None = "e8f9a0b1c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_availability_observation",
        sa.Column("response_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT 1 FROM provider_availability_observation "
            "WHERE response_payload IS NOT NULL LIMIT 1"
        )
    ).first()
    if populated is not None:
        raise RuntimeError(
            "refusing to downgrade: availability response evidence exists and would be lost"
        )
    op.drop_column("provider_availability_observation", "response_payload")
