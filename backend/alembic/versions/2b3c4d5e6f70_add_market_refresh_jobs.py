"""add coalesced market-data refresh jobs"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b3c4d5e6f70"
down_revision: str | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_refresh_job",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=180), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("timeframe", sa.String(length=12), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["instrument.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, cols, unique in (
        ("ix_market_refresh_job_request_key", ["request_key"], True),
        ("ix_market_refresh_job_instrument_id", ["instrument_id"], False),
        ("ix_market_refresh_job_capability", ["capability"], False),
        ("ix_market_refresh_job_priority", ["priority"], False),
        ("ix_market_refresh_job_status", ["status"], False),
        ("ix_market_refresh_job_next_attempt_at", ["next_attempt_at"], False),
    ):
        op.create_index(name, "market_refresh_job", cols, unique=unique)


def downgrade() -> None:
    for name in (
        "ix_market_refresh_job_next_attempt_at",
        "ix_market_refresh_job_status",
        "ix_market_refresh_job_priority",
        "ix_market_refresh_job_capability",
        "ix_market_refresh_job_instrument_id",
        "ix_market_refresh_job_request_key",
    ):
        op.drop_index(name, table_name="market_refresh_job")
    op.drop_table("market_refresh_job")
