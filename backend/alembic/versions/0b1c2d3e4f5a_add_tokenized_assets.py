"""Add tokenized-asset capability and product metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0b1c2d3e4f5a"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ProviderCapability is a PostgreSQL enum in deployed databases.  SQLite
    # test databases use the same string-valued SQLAlchemy enum and need no
    # explicit type operation.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE providercapability ADD VALUE IF NOT EXISTS 'TOKENIZED_ASSETS'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )
    op.create_table(
        "tokenized_asset_detail",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("underlying_instrument_id", sa.Integer(), nullable=True),
        sa.Column("provider_asset_id", sa.String(length=160), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("token_symbol", sa.String(length=80), nullable=True),
        sa.Column("isin", sa.String(length=20), nullable=True),
        sa.Column("underlying_symbol", sa.String(length=80), nullable=True),
        sa.Column("underlying_isin", sa.String(length=20), nullable=True),
        sa.Column("backing_type", sa.String(length=80), nullable=True),
        sa.Column("multiplier", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("circulating_supply", sa.Numeric(precision=40, scale=12), nullable=True),
        sa.Column("total_supply", sa.Numeric(precision=40, scale=12), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("is_derivative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deployments", sa.JSON(), nullable=True),
        sa.Column("collateral", sa.JSON(), nullable=True),
        sa.Column("corporate_actions", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"], ["instrument.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instrument_id", name="uq_tokenized_asset_detail_instrument_id"),
    )
    op.create_index(
        "ix_tokenized_asset_detail_provider_asset_id",
        "tokenized_asset_detail",
        ["provider_asset_id"],
    )
    op.create_index(
        "ix_tokenized_asset_detail_provider_name",
        "tokenized_asset_detail",
        ["provider_name"],
    )
    op.create_index(
        "ix_tokenized_asset_detail_token_symbol",
        "tokenized_asset_detail",
        ["token_symbol"],
    )
    op.create_index(
        "ix_tokenized_asset_detail_isin", "tokenized_asset_detail", ["isin"]
    )
    op.create_index(
        "ix_tokenized_asset_detail_underlying_instrument_id",
        "tokenized_asset_detail",
        ["underlying_instrument_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tokenized_asset_detail_underlying_instrument_id",
        table_name="tokenized_asset_detail",
    )
    op.drop_index("ix_tokenized_asset_detail_isin", table_name="tokenized_asset_detail")
    op.drop_index("ix_tokenized_asset_detail_token_symbol", table_name="tokenized_asset_detail")
    op.drop_index("ix_tokenized_asset_detail_provider_name", table_name="tokenized_asset_detail")
    op.drop_index(
        "ix_tokenized_asset_detail_provider_asset_id", table_name="tokenized_asset_detail"
    )
    op.drop_table("tokenized_asset_detail")
