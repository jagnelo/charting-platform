"""Record explicit provenance for locally derived OHLCV bars."""

import sqlalchemy as sa

from alembic import op

revision = "ff0a1b2c3d4e"
down_revision = "fe4f5a6b7c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ohlcv_bar",
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("ohlcv_bar", sa.Column("source_timeframe", sa.String(length=8), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("derivation_method", sa.String(length=80), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("derived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("source_bar_count", sa.Integer(), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("source_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ohlcv_bar", sa.Column("source_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ohlcv_bar", "source_end")
    op.drop_column("ohlcv_bar", "source_start")
    op.drop_column("ohlcv_bar", "source_bar_count")
    op.drop_column("ohlcv_bar", "derived_at")
    op.drop_column("ohlcv_bar", "derivation_method")
    op.drop_column("ohlcv_bar", "source_timeframe")
    op.drop_column("ohlcv_bar", "is_derived")
