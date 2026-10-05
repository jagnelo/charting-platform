"""Persist owner-scoped idempotency receipts for forward lifecycle changes."""

import sqlalchemy as sa

from alembic import op

revision = "ff5a6b7c8d9e"
down_revision: str | None = "ff4a5b6c7d8e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE strategy_lab_v2_forward_lifecycle_requests (
                owner_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                idempotency_key_digest TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                resolution_decision TEXT NOT NULL,
                result_instance_json TEXT NOT NULL,
                result_instance_fingerprint TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                receipt_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, instance_id, idempotency_key_digest)
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP TABLE strategy_lab_v2_forward_lifecycle_requests CASCADE")
    )
