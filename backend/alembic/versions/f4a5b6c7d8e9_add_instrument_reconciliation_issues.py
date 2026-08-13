"""Add durable instrument reconciliation issue queue."""

import sqlalchemy as sa

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_reconciliation_issue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("provider_symbol", sa.String(length=80), nullable=False),
        sa.Column("issue_type", sa.String(length=60), nullable=False),
        sa.Column("fingerprint", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_source_id",
            "provider_symbol",
            "issue_type",
            "fingerprint",
            name="uq_instrument_reconciliation_issue_identity",
        ),
    )
    op.create_index(
        "ix_instrument_reconciliation_issue_data_source_id",
        "instrument_reconciliation_issue",
        ["data_source_id"],
    )
    op.create_index(
        "ix_instrument_reconciliation_issue_provider_symbol",
        "instrument_reconciliation_issue",
        ["provider_symbol"],
    )
    op.create_index(
        "ix_instrument_reconciliation_issue_issue_type",
        "instrument_reconciliation_issue",
        ["issue_type"],
    )
    op.create_index(
        "ix_instrument_reconciliation_issue_status",
        "instrument_reconciliation_issue",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_reconciliation_issue_status", table_name="instrument_reconciliation_issue")
    op.drop_index("ix_instrument_reconciliation_issue_issue_type", table_name="instrument_reconciliation_issue")
    op.drop_index("ix_instrument_reconciliation_issue_provider_symbol", table_name="instrument_reconciliation_issue")
    op.drop_index("ix_instrument_reconciliation_issue_data_source_id", table_name="instrument_reconciliation_issue")
    op.drop_table("instrument_reconciliation_issue")
