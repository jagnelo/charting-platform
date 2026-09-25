"""Retain every provider payload used to refresh a market event."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bigint_id = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
    op.create_table(
        "market_event_observation",
        sa.Column("id", bigint_id, autoincrement=True, nullable=False),
        sa.Column("market_event_id", bigint_id, nullable=False),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("source_version", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_event_id"], ["market_event.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_event_observation_market_event_id",
        "market_event_observation",
        ["market_event_id"],
    )
    op.create_index(
        "ix_market_event_observation_event_key",
        "market_event_observation",
        ["event_key"],
    )
    op.create_index(
        "ix_market_event_observation_source",
        "market_event_observation",
        ["source"],
    )
    op.create_index(
        "ix_market_event_observation_event_type",
        "market_event_observation",
        ["event_type"],
    )
    op.create_index(
        "ix_market_event_observation_observed_at",
        "market_event_observation",
        ["observed_at"],
    )
    op.create_index(
        "ix_market_event_observation_source_event_observed",
        "market_event_observation",
        ["source", "event_key", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_event_observation_source_event_observed",
        table_name="market_event_observation",
    )
    op.drop_index("ix_market_event_observation_observed_at", table_name="market_event_observation")
    op.drop_index("ix_market_event_observation_event_type", table_name="market_event_observation")
    op.drop_index("ix_market_event_observation_source", table_name="market_event_observation")
    op.drop_index("ix_market_event_observation_event_key", table_name="market_event_observation")
    op.drop_index(
        "ix_market_event_observation_market_event_id",
        table_name="market_event_observation",
    )
    op.drop_table("market_event_observation")
