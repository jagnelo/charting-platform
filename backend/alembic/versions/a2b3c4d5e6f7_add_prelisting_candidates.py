"""Add auditable provisional instruments for future listing candidates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_event_prelisting_candidate",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("candidate_key", sa.String(length=180), nullable=False),
        sa.Column("consensus_id", sa.BigInteger(), nullable=True),
        sa.Column("anchor_event_id", sa.BigInteger(), nullable=True),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("proposed_symbol", sa.String(length=50), nullable=False),
        sa.Column("proposed_name", sa.String(length=300), nullable=False),
        sa.Column("exchange_mic", sa.String(length=10), nullable=True),
        sa.Column("expected_listing_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("stable_identifiers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("provider_sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["consensus_id"], ["market_event_consensus.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["anchor_event_id"], ["market_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_key", name="uq_market_event_prelisting_candidate_key"),
        sa.UniqueConstraint("consensus_id", name="uq_market_event_prelisting_consensus_id"),
    )
    for name, columns in (
        ("ix_market_event_prelisting_candidate_key", ["candidate_key"]),
        ("ix_market_event_prelisting_consensus_id", ["consensus_id"]),
        ("ix_market_event_prelisting_anchor_event_id", ["anchor_event_id"]),
        ("ix_market_event_prelisting_instrument_id", ["instrument_id"]),
        ("ix_market_event_prelisting_issuer_id", ["issuer_id"]),
        ("ix_market_event_prelisting_proposed_symbol", ["proposed_symbol"]),
        ("ix_market_event_prelisting_exchange_mic", ["exchange_mic"]),
        ("ix_market_event_prelisting_expected_listing_date", ["expected_listing_date"]),
        ("ix_market_event_prelisting_status", ["status"]),
        (
            "ix_market_event_prelisting_status_expected",
            ["status", "expected_listing_date"],
        ),
    ):
        op.create_index(name, "market_event_prelisting_candidate", columns)


def downgrade() -> None:
    for name in (
        "ix_market_event_prelisting_status_expected",
        "ix_market_event_prelisting_status",
        "ix_market_event_prelisting_expected_listing_date",
        "ix_market_event_prelisting_exchange_mic",
        "ix_market_event_prelisting_proposed_symbol",
        "ix_market_event_prelisting_issuer_id",
        "ix_market_event_prelisting_instrument_id",
        "ix_market_event_prelisting_anchor_event_id",
        "ix_market_event_prelisting_consensus_id",
        "ix_market_event_prelisting_candidate_key",
    ):
        op.drop_index(name, table_name="market_event_prelisting_candidate")
    op.drop_table("market_event_prelisting_candidate")
