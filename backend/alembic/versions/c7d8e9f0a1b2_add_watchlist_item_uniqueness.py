"""add watchlist item uniqueness

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-04-23 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_watchlist_item_watchlist_instrument",
        "watchlist_item",
        ["watchlist_id", "instrument_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_watchlist_item_watchlist_instrument",
        "watchlist_item",
        type_="unique",
    )
