"""Add the compatibility mapping for the default OHLCV series."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "9f0a1b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_series_default",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=False),
        sa.Column("is_adjusted", sa.Boolean(), nullable=False),
        sa.Column("market_series_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "selection_reason",
            sa.String(length=80),
            nullable=False,
            server_default="first_canonical",
        ),
        sa.Column(
            "selected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["market_series_id"], ["market_series.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "is_adjusted",
            name="uq_market_series_default_scope",
        ),
    )
    op.create_index(
        "ix_market_series_default_instrument_id",
        "market_series_default",
        ["instrument_id"],
    )
    op.create_index(
        "ix_market_series_default_market_series_id",
        "market_series_default",
        ["market_series_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_series_default_market_series_id", table_name="market_series_default"
    )
    op.drop_index(
        "ix_market_series_default_instrument_id", table_name="market_series_default"
    )
    op.drop_table("market_series_default")
