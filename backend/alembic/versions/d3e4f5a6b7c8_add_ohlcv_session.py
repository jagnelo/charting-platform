"""Add canonical OHLCV session classification."""

import sqlalchemy as sa

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "d2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ohlcv_bar",
        sa.Column("session", sa.String(length=16), server_default="regular", nullable=False),
    )
    op.create_index(
        "ix_ohlcv_instrument_tf_session_ts",
        "ohlcv_bar",
        ["instrument_id", "timeframe", "session", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_ohlcv_instrument_tf_session_ts", table_name="ohlcv_bar")
    op.drop_column("ohlcv_bar", "session")
