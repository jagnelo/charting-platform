"""Retain every provider observation of a market bar."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "ce5f6a7b8c9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_IDENTITY_COLUMNS = [
    "instrument_id",
    "data_source_id",
    "timeframe",
    "ts",
    "is_adjusted",
    "scope_key",
]


def upgrade() -> None:
    """Include observation time in the raw-bar conflict key.

    A normalized OHLCV bar is a projection and may be refreshed when a
    provider revises history. Raw provider observations must remain available
    for replay and audit, so each fetch timestamp gets its own immutable row.
    """

    with op.batch_alter_table("market_bar_observation") as batch:
        batch.drop_constraint("uq_market_bar_observation", type_="unique")
        batch.create_unique_constraint(
            "uq_market_bar_observation",
            [*_IDENTITY_COLUMNS, "observed_at"],
        )


def downgrade() -> None:
    """Restore the old key only when no observations would be discarded.

    A downgrade that silently deletes duplicate observations would violate the
    append-only evidence invariant. Refuse it instead and require an explicit
    operator migration if a rollback is genuinely needed.
    """

    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            "SELECT 1 FROM market_bar_observation "
            "GROUP BY instrument_id, data_source_id, timeframe, ts, is_adjusted, scope_key "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot downgrade append-only market bar observations without losing data"
        )

    with op.batch_alter_table("market_bar_observation") as batch:
        batch.drop_constraint("uq_market_bar_observation", type_="unique")
        batch.create_unique_constraint(
            "uq_market_bar_observation",
            _IDENTITY_COLUMNS,
        )
