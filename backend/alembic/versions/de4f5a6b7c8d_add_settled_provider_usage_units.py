"""add settled provider usage units to request logs

Revision ID: de4f5a6b7c8d
Revises: cd3e4f5a6b7c
Create Date: 2026-09-13 20:15:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "de4f5a6b7c8d"
down_revision = "cd3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_request_log",
        sa.Column("settled_usage_units", sa.Numeric(precision=12, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_request_log", "settled_usage_units")
