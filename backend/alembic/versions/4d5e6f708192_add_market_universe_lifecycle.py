"""add durable US universe reconciliation and lifecycle observations"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d5e6f708192"
down_revision: str | None = "3c4d5e6f7081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_universe_reconciliation_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("quote_type", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="running"),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deactivated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quarantined_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_universe_reconciliation_run_source_type_observed",
        "market_universe_reconciliation_run",
        ["data_source_id", "quote_type", "observed_at"],
    )
    op.create_index(
        "ix_market_universe_reconciliation_run_status",
        "market_universe_reconciliation_run",
        ["status"],
    )

    op.create_table(
        "market_universe_lifecycle_observation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("provider_symbol", sa.String(length=80), nullable=False),
        sa.Column("exchange_mic", sa.String(length=10), nullable=True),
        sa.Column("quote_type", sa.String(length=40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lifecycle_status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_missing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("consecutive_missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["market_universe_reconciliation_run.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["listing_id"], ["instrument_listing.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id", "provider_symbol", "exchange_mic", "quote_type",
            name="uq_market_universe_lifecycle_observation",
        ),
    )
    for name, columns in (
        ("ix_market_universe_lifecycle_observation_source", ["data_source_id"]),
        ("ix_market_universe_lifecycle_observation_run", ["run_id"]),
        ("ix_market_universe_lifecycle_observation_instrument", ["instrument_id"]),
        ("ix_market_universe_lifecycle_observation_listing", ["listing_id"]),
        ("ix_market_universe_lifecycle_observation_symbol", ["provider_symbol"]),
        ("ix_market_universe_lifecycle_observation_exchange", ["exchange_mic"]),
        ("ix_market_universe_lifecycle_observation_quote_type", ["quote_type"]),
        ("ix_market_universe_lifecycle_observation_observed", ["observed_at"]),
        ("ix_market_universe_lifecycle_observation_status", ["lifecycle_status", "present"]),
    ):
        op.create_index(name, "market_universe_lifecycle_observation", columns)


def downgrade() -> None:
    for name in (
        "ix_market_universe_lifecycle_observation_status",
        "ix_market_universe_lifecycle_observation_observed",
        "ix_market_universe_lifecycle_observation_quote_type",
        "ix_market_universe_lifecycle_observation_exchange",
        "ix_market_universe_lifecycle_observation_symbol",
        "ix_market_universe_lifecycle_observation_listing",
        "ix_market_universe_lifecycle_observation_instrument",
        "ix_market_universe_lifecycle_observation_run",
        "ix_market_universe_lifecycle_observation_source",
    ):
        op.drop_index(name, table_name="market_universe_lifecycle_observation")
    op.drop_table("market_universe_lifecycle_observation")
    op.drop_index(
        "ix_market_universe_reconciliation_run_status",
        table_name="market_universe_reconciliation_run",
    )
    op.drop_index(
        "ix_market_universe_reconciliation_run_source_type_observed",
        table_name="market_universe_reconciliation_run",
    )
    op.drop_table("market_universe_reconciliation_run")
