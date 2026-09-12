"""Add durable cursors for bounded provider-wide event scans."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_event_scan_state",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("scan_key", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("cursor_issuer_id", sa.BigInteger(), nullable=True),
        sa.Column("cycle_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cycle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_batch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="idle"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["cursor_issuer_id"], ["issuer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_key", name="uq_market_event_scan_state_key"),
    )
    for name, columns in (
        ("ix_market_event_scan_state_scan_key", ["scan_key"]),
        ("ix_market_event_scan_state_provider", ["provider"]),
        ("ix_market_event_scan_state_cursor_issuer_id", ["cursor_issuer_id"]),
        ("ix_market_event_scan_state_status", ["status"]),
        (
            "ix_market_event_scan_provider_operation",
            ["provider", "operation"],
        ),
    ):
        op.create_index(name, "market_event_scan_state", columns)


def downgrade() -> None:
    for name in (
        "ix_market_event_scan_provider_operation",
        "ix_market_event_scan_state_status",
        "ix_market_event_scan_state_cursor_issuer_id",
        "ix_market_event_scan_state_provider",
        "ix_market_event_scan_state_scan_key",
    ):
        op.drop_index(name, table_name="market_event_scan_state")
    op.drop_table("market_event_scan_state")
