"""Retain every provider payload used to refresh tokenized assets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bigint_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "tokenized_asset_observation",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("instrument_id", bigint_id, nullable=False),
        sa.Column("provider_asset_id", sa.String(length=160), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("token_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tokenized_asset_observation_instrument_id",
        "tokenized_asset_observation",
        ["instrument_id"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_provider_asset_id",
        "tokenized_asset_observation",
        ["provider_asset_id"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_provider_name",
        "tokenized_asset_observation",
        ["provider_name"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_token_symbol",
        "tokenized_asset_observation",
        ["token_symbol"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_observed_at",
        "tokenized_asset_observation",
        ["observed_at"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_fetched_at",
        "tokenized_asset_observation",
        ["fetched_at"],
    )
    op.create_index(
        "ix_tokenized_asset_observation_provider_asset_observed",
        "tokenized_asset_observation",
        ["provider_name", "provider_asset_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tokenized_asset_observation_provider_asset_observed",
        table_name="tokenized_asset_observation",
    )
    op.drop_index("ix_tokenized_asset_observation_fetched_at", table_name="tokenized_asset_observation")
    op.drop_index("ix_tokenized_asset_observation_observed_at", table_name="tokenized_asset_observation")
    op.drop_index("ix_tokenized_asset_observation_token_symbol", table_name="tokenized_asset_observation")
    op.drop_index("ix_tokenized_asset_observation_provider_name", table_name="tokenized_asset_observation")
    op.drop_index(
        "ix_tokenized_asset_observation_provider_asset_id",
        table_name="tokenized_asset_observation",
    )
    op.drop_index("ix_tokenized_asset_observation_instrument_id", table_name="tokenized_asset_observation")
    op.drop_table("tokenized_asset_observation")
