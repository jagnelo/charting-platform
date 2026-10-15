"""Add database-side timestamp defaults to provider pagination state."""

import sqlalchemy as sa

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("provider_pagination_state") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_pagination_state") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
