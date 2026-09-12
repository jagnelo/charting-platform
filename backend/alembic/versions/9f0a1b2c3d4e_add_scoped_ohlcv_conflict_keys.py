"""Keep OHLCV uniqueness scoped by series and trading session."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9f0a1b2c3d4e"
down_revision: str | None = "8e9f0a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_scope_key(table_name: str) -> None:
    """Give legacy rows a deterministic compatibility scope before indexing."""

    op.execute(
        sa.text(
            f"UPDATE {table_name} SET scope_key = CASE "
            "WHEN market_series_id IS NULL THEN 'legacy:' || session "
            "ELSE 'series:' || CAST(market_series_id AS VARCHAR(40)) || ':' || session "
            "END"
        )
    )


def upgrade() -> None:
    # The canonical table historically used a unique index, while provider
    # observations used a named unique constraint. Replace both with the same
    # explicit scope key so PostgreSQL upserts can target the scoped identity.
    with op.batch_alter_table("ohlcv_bar") as batch:
        batch.add_column(
            sa.Column(
                "scope_key",
                sa.String(length=180),
                nullable=False,
                server_default="legacy:regular",
            )
        )
        batch.drop_index("uq_ohlcv_bar")

    with op.batch_alter_table("market_bar_observation") as batch:
        batch.add_column(
            sa.Column(
                "scope_key",
                sa.String(length=180),
                nullable=False,
                server_default="legacy:regular",
            )
        )
        batch.drop_constraint("uq_market_bar_observation", type_="unique")

    _backfill_scope_key("ohlcv_bar")
    _backfill_scope_key("market_bar_observation")

    op.create_index(
        "uq_ohlcv_bar",
        "ohlcv_bar",
        ["instrument_id", "timeframe", "ts", "is_adjusted", "scope_key"],
        unique=True,
    )
    with op.batch_alter_table("market_bar_observation") as batch:
        batch.create_unique_constraint(
            "uq_market_bar_observation",
            [
                "instrument_id",
                "data_source_id",
                "timeframe",
                "ts",
                "is_adjusted",
                "scope_key",
            ],
        )


def downgrade() -> None:
    op.drop_index("uq_ohlcv_bar", table_name="ohlcv_bar")
    with op.batch_alter_table("market_bar_observation") as batch:
        batch.drop_constraint("uq_market_bar_observation", type_="unique")
        batch.drop_column("scope_key")
    with op.batch_alter_table("ohlcv_bar") as batch:
        batch.drop_column("scope_key")

    op.create_index(
        "uq_ohlcv_bar",
        "ohlcv_bar",
        ["instrument_id", "timeframe", "ts", "is_adjusted"],
        unique=True,
    )
    with op.batch_alter_table("market_bar_observation") as batch:
        batch.create_unique_constraint(
            "uq_market_bar_observation",
            ["instrument_id", "data_source_id", "timeframe", "ts", "is_adjusted"],
        )
