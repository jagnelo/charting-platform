"""Persist bounded watchlist history refresh runs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fb1c2d3e4f5a"
down_revision: str | Sequence[str] | None = "fa0b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_history_refresh_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("timeframes", sa.JSON(), nullable=False),
        sa.Column("membership_versions", sa.JSON(), nullable=False),
        sa.Column("instrument_ids", sa.JSON(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_instruments", sa.Integer(), nullable=False),
        sa.Column("available_instrument_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_instrument_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("already_queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_watchlist_history_refresh_run_user_id",
        "watchlist_history_refresh_run",
        ["user_id"],
    )
    op.create_index(
        "ix_watchlist_history_refresh_run_status",
        "watchlist_history_refresh_run",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_watchlist_history_refresh_run_status", table_name="watchlist_history_refresh_run"
    )
    op.drop_index(
        "ix_watchlist_history_refresh_run_user_id", table_name="watchlist_history_refresh_run"
    )
    op.drop_table("watchlist_history_refresh_run")
