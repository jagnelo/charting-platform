"""add_instrument_indicator_config

Revision ID: a3a03047acc3
Revises: 030fc5ddfae4
Create Date: 2026-03-27 23:29:52.153656

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a3a03047acc3'
down_revision: str | None = '030fc5ddfae4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_indicator_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("indicators", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "instrument_id", name="uq_user_instrument_indicators"),
    )
    op.create_index("ix_instrument_indicator_config_user_id", "instrument_indicator_config", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_instrument_indicator_config_user_id", table_name="instrument_indicator_config")
    op.drop_table("instrument_indicator_config")
