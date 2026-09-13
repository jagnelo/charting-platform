"""Retain tokenized economic issuer CIKs separately from token identity."""

import sqlalchemy as sa

from alembic import op

revision = "ef5a6b7c8d9e"
down_revision = "de4f5a6b7c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tokenized_asset_detail",
        sa.Column("underlying_cik", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "tokenized_asset_detail",
        sa.Column("underlying_issuer_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_tokenized_asset_detail_underlying_cik",
        "tokenized_asset_detail",
        ["underlying_cik"],
    )
    op.create_index(
        "ix_tokenized_asset_detail_underlying_issuer_id",
        "tokenized_asset_detail",
        ["underlying_issuer_id"],
    )
    op.create_foreign_key(
        "fk_tokenized_asset_detail_underlying_issuer_id_issuer",
        "tokenized_asset_detail",
        "issuer",
        ["underlying_issuer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tokenized_asset_detail_underlying_issuer_id_issuer",
        "tokenized_asset_detail",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_tokenized_asset_detail_underlying_issuer_id",
        table_name="tokenized_asset_detail",
    )
    op.drop_index(
        "ix_tokenized_asset_detail_underlying_cik",
        table_name="tokenized_asset_detail",
    )
    op.drop_column("tokenized_asset_detail", "underlying_issuer_id")
    op.drop_column("tokenized_asset_detail", "underlying_cik")
