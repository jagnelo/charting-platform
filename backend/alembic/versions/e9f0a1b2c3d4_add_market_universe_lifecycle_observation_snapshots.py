"""Retain every provider universe lifecycle observation payload."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9f1a2b3c4d5"
down_revision: str | None = "e8f9a0b1c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bigint_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "market_universe_lifecycle_observation_snapshot",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("run_id", bigint_id, nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("provider_symbol", sa.String(length=80), nullable=False),
        sa.Column("exchange_mic", sa.String(length=10), nullable=True),
        sa.Column("quote_type", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lifecycle_status", sa.String(length=24), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_missing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_seen", sa.Integer(), nullable=False),
        sa.Column("consecutive_missing", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["market_universe_reconciliation_run.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["listing_id"], ["instrument_listing.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        (
            "ix_market_universe_lifecycle_snapshot_source_symbol_observed",
            ["data_source_id", "provider_symbol", "observed_at"],
        ),
        ("ix_market_universe_lifecycle_snapshot_run_quote_type", ["run_id", "quote_type"]),
    ):
        op.create_index(name, "market_universe_lifecycle_observation_snapshot", columns)


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT 1 FROM market_universe_lifecycle_observation_snapshot LIMIT 1"
        )
    ).first()
    if populated is not None:
        raise RuntimeError(
            "refusing to downgrade: universe lifecycle observation evidence exists and would be lost"
        )
    op.drop_index(
        "ix_market_universe_lifecycle_snapshot_run_quote_type",
        table_name="market_universe_lifecycle_observation_snapshot",
    )
    op.drop_index(
        "ix_market_universe_lifecycle_snapshot_source_symbol_observed",
        table_name="market_universe_lifecycle_observation_snapshot",
    )
    op.drop_table("market_universe_lifecycle_observation_snapshot")
