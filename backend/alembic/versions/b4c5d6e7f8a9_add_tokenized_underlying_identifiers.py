"""Add stable identifiers for tokenized economic underlyings."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tokenized_asset_detail", sa.Column("underlying_figi", sa.String(length=80), nullable=True))
    op.add_column(
        "tokenized_asset_detail",
        sa.Column("underlying_composite_figi", sa.String(length=80), nullable=True),
    )
    op.add_column("tokenized_asset_detail", sa.Column("underlying_cusip", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("tokenized_asset_detail", "underlying_cusip")
    op.drop_column("tokenized_asset_detail", "underlying_composite_figi")
    op.drop_column("tokenized_asset_detail", "underlying_figi")
