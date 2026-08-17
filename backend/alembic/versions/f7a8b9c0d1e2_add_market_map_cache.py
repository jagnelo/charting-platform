"""Persist canonical Market Map results by source-aware cache identity."""

import sqlalchemy as sa

from alembic import op


revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_map_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=240), nullable=False),
        sa.Column("membership_version", sa.String(length=160), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("bar_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cache_key", name="uq_market_map_cache_user_key"),
    )
    op.create_index("ix_market_map_cache_user_id", "market_map_cache", ["user_id"])
    op.create_index(
        "ix_market_map_cache_user_source", "market_map_cache", ["user_id", "source_id"]
    )
    op.create_index(
        "ix_market_map_cache_user_computed", "market_map_cache", ["user_id", "computed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_market_map_cache_user_computed", table_name="market_map_cache")
    op.drop_index("ix_market_map_cache_user_source", table_name="market_map_cache")
    op.drop_index("ix_market_map_cache_user_id", table_name="market_map_cache")
    op.drop_table("market_map_cache")
