"""Persist provider availability notification cooldown state."""

import sqlalchemy as sa

from alembic import op

revision = "fe4f5a6b7c8d"
down_revision = "fd3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_health_state",
        sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_health_state",
        sa.Column("last_notification_kind", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "provider_health_state",
        sa.Column("notified_failure_streak", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("provider_health_state", "notified_failure_streak")
    op.drop_column("provider_health_state", "last_notification_kind")
    op.drop_column("provider_health_state", "last_notification_at")
