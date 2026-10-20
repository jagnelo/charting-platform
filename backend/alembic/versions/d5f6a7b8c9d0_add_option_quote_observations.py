"""Retain every provider response used to refresh an option quote."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5f6a7b8c9d0"
down_revision: str | None = "d6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bigint_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "option_quote_observation",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("option_instrument_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["option_instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["option_chain_snapshot.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_option_quote_observation_option_instrument_id", ["option_instrument_id"]),
        ("ix_option_quote_observation_snapshot_id", ["snapshot_id"]),
        ("ix_option_quote_observation_data_source_id", ["data_source_id"]),
        ("ix_option_quote_observation_observed_at", ["observed_at"]),
        ("ix_option_quote_observation_fetched_at", ["fetched_at"]),
        (
            "ix_option_quote_observation_option_source_observed",
            ["option_instrument_id", "data_source_id", "observed_at"],
        ),
    ):
        op.create_index(name, "option_quote_observation", columns)


def downgrade() -> None:
    for name in (
        "ix_option_quote_observation_option_source_observed",
        "ix_option_quote_observation_fetched_at",
        "ix_option_quote_observation_observed_at",
        "ix_option_quote_observation_data_source_id",
        "ix_option_quote_observation_snapshot_id",
        "ix_option_quote_observation_option_instrument_id",
    ):
        op.drop_index(name, table_name="option_quote_observation")
    op.drop_table("option_quote_observation")
