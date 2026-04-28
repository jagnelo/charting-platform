"""add provider request usage fields

Revision ID: a7b8c9d0e1f2
Revises: f4b5c6d7e8f9
Create Date: 2026-04-28 12:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_request_log",
        sa.Column("operation_family", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "provider_request_log",
        sa.Column("usage_mode", sa.String(length=24), nullable=False, server_default="call_count"),
    )
    op.add_column(
        "provider_request_log",
        sa.Column("usage_unit_label", sa.String(length=24), nullable=False, server_default="requests"),
    )
    op.add_column(
        "provider_request_log",
        sa.Column("usage_units", sa.Numeric(precision=12, scale=4), nullable=False, server_default="1"),
    )
    op.execute("UPDATE provider_request_log SET operation_family = operation WHERE operation_family IS NULL")
    op.alter_column("provider_request_log", "operation_family", nullable=False)
    op.create_index(
        "ix_provider_request_log_source_requested",
        "provider_request_log",
        ["data_source_id", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_request_log_source_requested", table_name="provider_request_log")
    op.drop_column("provider_request_log", "usage_units")
    op.drop_column("provider_request_log", "usage_unit_label")
    op.drop_column("provider_request_log", "usage_mode")
    op.drop_column("provider_request_log", "operation_family")
