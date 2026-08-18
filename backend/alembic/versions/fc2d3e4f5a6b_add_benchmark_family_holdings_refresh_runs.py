"""Persist provider-backed benchmark-family holdings refresh runs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fc2d3e4f5a6b"
down_revision: str | Sequence[str] | None = "fb1c2d3e4f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmark_family_holdings_refresh_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("family_keys", sa.JSON(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("requested_dates", sa.JSON(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refreshed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unavailable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
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
        "ix_benchmark_family_holdings_refresh_run_user_id",
        "benchmark_family_holdings_refresh_run",
        ["user_id"],
    )
    op.create_index(
        "ix_benchmark_family_holdings_refresh_run_status",
        "benchmark_family_holdings_refresh_run",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_benchmark_family_holdings_refresh_run_status",
        table_name="benchmark_family_holdings_refresh_run",
    )
    op.drop_index(
        "ix_benchmark_family_holdings_refresh_run_user_id",
        table_name="benchmark_family_holdings_refresh_run",
    )
    op.drop_table("benchmark_family_holdings_refresh_run")
