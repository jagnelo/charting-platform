"""add instrument_merge_log audit table for duplicate-instrument merges

Schema only: the data repair itself is a bounded, idempotent worker task
(``app.services.instrument_dedup``), not a migration, so deploys never hold
locks across the whole market-data schema.

Revision ID: b1c2d3e4f5a7
Revises: d5e6f7a8b9c0
Create Date: 2026-11-26 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a7"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_merge_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("duplicate_instrument_id", sa.Integer(), nullable=False),
        sa.Column("canonical_instrument_id", sa.Integer(), nullable=False),
        sa.Column("duplicate_symbol", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "merged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_instrument_merge_log_duplicate",
        "instrument_merge_log",
        ["duplicate_instrument_id"],
        unique=True,
    )
    op.create_index(
        "ix_instrument_merge_log_canonical",
        "instrument_merge_log",
        ["canonical_instrument_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_merge_log_canonical", table_name="instrument_merge_log")
    op.drop_index("uq_instrument_merge_log_duplicate", table_name="instrument_merge_log")
    op.drop_table("instrument_merge_log")
