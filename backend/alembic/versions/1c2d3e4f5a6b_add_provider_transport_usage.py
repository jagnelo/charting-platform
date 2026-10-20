"""Persist provider transport-byte observations for usage accounting."""

import sqlalchemy as sa

from alembic import op

revision = "1c2d3e4f5a6b"
down_revision = "0b1c2d3e4f5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_request_log",
        sa.Column("http_requests", sa.Integer(), nullable=True),
    )
    op.add_column(
        "provider_request_log",
        sa.Column("response_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "provider_request_log",
        sa.Column("response_headers", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("provider_request_log", "response_headers")
    op.drop_column("provider_request_log", "response_bytes")
    op.drop_column("provider_request_log", "http_requests")
