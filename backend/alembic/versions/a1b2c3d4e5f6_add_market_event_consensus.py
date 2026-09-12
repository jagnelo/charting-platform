"""Add durable conservative market-event consensus groups."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_event_consensus",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("consensus_key", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="single_source"),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agreement_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("conflict_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("canonical_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consensus_key", name="uq_market_event_consensus_key"),
    )
    for name, columns in (
        ("ix_market_event_consensus_key", ["consensus_key"]),
        ("ix_market_event_consensus_event_type", ["event_type"]),
        ("ix_market_event_consensus_instrument_id", ["instrument_id"]),
        ("ix_market_event_consensus_issuer_id", ["issuer_id"]),
        ("ix_market_event_consensus_effective_date", ["effective_date"]),
        ("ix_market_event_consensus_event_time", ["event_time"]),
        ("ix_market_event_consensus_status", ["status"]),
        (
            "ix_market_event_consensus_target_date",
            ["instrument_id", "issuer_id", "effective_date"],
        ),
        ("ix_market_event_consensus_status_observed", ["status", "last_observed_at"]),
    ):
        op.create_index(name, "market_event_consensus", columns)

    with op.batch_alter_table("market_event") as batch:
        batch.add_column(sa.Column("consensus_id", sa.BigInteger(), nullable=True))
        batch.create_foreign_key(
            "fk_market_event_consensus_id",
            "market_event_consensus",
            ["consensus_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_market_event_consensus_id", ["consensus_id"])


def downgrade() -> None:
    with op.batch_alter_table("market_event") as batch:
        batch.drop_index("ix_market_event_consensus_id")
        batch.drop_constraint("fk_market_event_consensus_id", type_="foreignkey")
        batch.drop_column("consensus_id")
    for name in (
        "ix_market_event_consensus_status_observed",
        "ix_market_event_consensus_target_date",
        "ix_market_event_consensus_status",
        "ix_market_event_consensus_event_time",
        "ix_market_event_consensus_effective_date",
        "ix_market_event_consensus_issuer_id",
        "ix_market_event_consensus_instrument_id",
        "ix_market_event_consensus_event_type",
        "ix_market_event_consensus_key",
    ):
        op.drop_index(name, table_name="market_event_consensus")
    op.drop_table("market_event_consensus")

