"""Add reviewer attribution to reconciliation decisions."""

import sqlalchemy as sa

from alembic import op


revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instrument_reconciliation_issue",
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_instrument_reconciliation_issue_resolved_by_user_id",
        "instrument_reconciliation_issue",
        ["resolved_by_user_id"],
    )
    op.create_foreign_key(
        "fk_instrument_reconciliation_issue_resolved_by_user_id_user",
        "instrument_reconciliation_issue",
        "user",
        ["resolved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_instrument_reconciliation_issue_resolved_by_user_id_user",
        "instrument_reconciliation_issue",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_instrument_reconciliation_issue_resolved_by_user_id",
        table_name="instrument_reconciliation_issue",
    )
    op.drop_column("instrument_reconciliation_issue", "resolved_by_user_id")
