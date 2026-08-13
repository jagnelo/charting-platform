"""Add canonical listing lifecycle timestamps."""

import sqlalchemy as sa

from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instrument_listing",
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instrument_listing",
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instrument_listing",
        sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_instrument_listing_effective_at",
        "instrument_listing",
        ["effective_at"],
    )
    op.create_index(
        "ix_instrument_listing_known_at",
        "instrument_listing",
        ["known_at"],
    )
    op.create_index(
        "ix_instrument_listing_delisted_at",
        "instrument_listing",
        ["delisted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_listing_delisted_at", table_name="instrument_listing")
    op.drop_index("ix_instrument_listing_known_at", table_name="instrument_listing")
    op.drop_index("ix_instrument_listing_effective_at", table_name="instrument_listing")
    op.drop_column("instrument_listing", "delisted_at")
    op.drop_column("instrument_listing", "known_at")
    op.drop_column("instrument_listing", "effective_at")
