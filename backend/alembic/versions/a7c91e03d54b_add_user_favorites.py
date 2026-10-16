"""Persist the TC2000 My Favorites Quick List per user."""

import sqlalchemy as sa

from alembic import op

revision = "a7c91e03d54b"
down_revision = "ff2a3b4c5d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "favorite_instrument",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "instrument_id", name="uq_favorite_user_instrument"),
    )
    op.create_index("ix_favorite_instrument_user_id", "favorite_instrument", ["user_id"])
    op.create_index("ix_favorite_instrument_instrument_id", "favorite_instrument", ["instrument_id"])


def downgrade() -> None:
    op.drop_index("ix_favorite_instrument_instrument_id", table_name="favorite_instrument")
    op.drop_index("ix_favorite_instrument_user_id", table_name="favorite_instrument")
    op.drop_table("favorite_instrument")
