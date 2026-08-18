"""Allow explicit canonical-instrument Market Map sources."""

import sqlalchemy as sa

from alembic import op


revision: str = "fa0b1c2d3e4f"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Explicit sources encode a bounded canonical-ID selection in the source
    # identity. Keep the cache/snapshot keys wide enough for the 500-ID limit.
    with op.batch_alter_table("market_map_cache") as batch:
        batch.alter_column(
            "source_id",
            existing_type=sa.String(length=240),
            type_=sa.String(length=4096),
            existing_nullable=False,
        )
    with op.batch_alter_table("market_map_snapshot") as batch:
        batch.alter_column(
            "source_id",
            existing_type=sa.String(length=240),
            type_=sa.String(length=4096),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("market_map_snapshot") as batch:
        batch.alter_column(
            "source_id",
            existing_type=sa.String(length=4096),
            type_=sa.String(length=240),
            existing_nullable=False,
        )
    with op.batch_alter_table("market_map_cache") as batch:
        batch.alter_column(
            "source_id",
            existing_type=sa.String(length=4096),
            type_=sa.String(length=240),
            existing_nullable=False,
        )
