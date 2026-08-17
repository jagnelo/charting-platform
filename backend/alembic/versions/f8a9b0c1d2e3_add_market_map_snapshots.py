"""Persist user-named Market Map snapshots."""

import sqlalchemy as sa

from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_map_snapshot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_id", sa.String(length=240), nullable=False),
        sa.Column("membership_version", sa.String(length=160), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("map_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_market_map_snapshot_user_name"),
    )
    op.create_index("ix_market_map_snapshot_user_id", "market_map_snapshot", ["user_id"])
    op.create_index(
        "ix_market_map_snapshot_user_created",
        "market_map_snapshot",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_map_snapshot_user_created", table_name="market_map_snapshot")
    op.drop_index("ix_market_map_snapshot_user_id", table_name="market_map_snapshot")
    op.drop_table("market_map_snapshot")
