"""Retain every routed provider response body on its request log."""

import sqlalchemy as sa

from alembic import op

revision = "fb2c3d4e5f6a"
down_revision = "fa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_request_log",
        sa.Column("response_payloads", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT 1 FROM provider_request_log "
            "WHERE response_payloads IS NOT NULL LIMIT 1"
        )
    ).first()
    if populated is not None:
        raise RuntimeError(
            "refusing to downgrade: provider response evidence exists and would be lost"
        )
    op.drop_column("provider_request_log", "response_payloads")
