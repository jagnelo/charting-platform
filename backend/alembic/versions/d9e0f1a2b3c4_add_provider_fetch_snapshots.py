"""add provider fetch snapshots

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-04-26 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9e0f1a2b3c4"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_identifier_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "data_source_id",
            "snapshot_hash",
            name="uq_instrument_identifier_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_instrument_identifier_snapshot_inst_source_observed",
        "instrument_identifier_snapshot",
        ["instrument_id", "data_source_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "latest_price_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_latest_price_snapshot_inst_source_observed",
        "latest_price_snapshot",
        ["instrument_id", "data_source_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "instrument_search_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("query", sa.String(length=120), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "query",
            "result_hash",
            name="uq_instrument_search_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_instrument_search_snapshot_source_query_observed",
        "instrument_search_snapshot",
        ["data_source_id", "query", "observed_at"],
        unique=False,
    )

    op.create_table(
        "universe_discovery_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("quote_type", sa.String(length=40), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "quote_type",
            "offset",
            "snapshot_hash",
            name="uq_universe_discovery_snapshot_hash",
        ),
    )
    op.create_index(
        "ix_universe_discovery_snapshot_source_type_offset_observed",
        "universe_discovery_snapshot",
        ["data_source_id", "quote_type", "offset", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_universe_discovery_snapshot_source_type_offset_observed",
        table_name="universe_discovery_snapshot",
    )
    op.drop_table("universe_discovery_snapshot")

    op.drop_index(
        "ix_instrument_search_snapshot_source_query_observed",
        table_name="instrument_search_snapshot",
    )
    op.drop_table("instrument_search_snapshot")

    op.drop_index(
        "ix_latest_price_snapshot_inst_source_observed",
        table_name="latest_price_snapshot",
    )
    op.drop_table("latest_price_snapshot")

    op.drop_index(
        "ix_instrument_identifier_snapshot_inst_source_observed",
        table_name="instrument_identifier_snapshot",
    )
    op.drop_table("instrument_identifier_snapshot")
