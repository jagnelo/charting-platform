"""Retain canonical bytes for durable Strategy Lab dispatch payloads.

Redis dispatch entries carry only content identities.  This additive table is
the worker lookup surface and is intentionally separate from owner-scoped
submission receipts so identical payloads deduplicate safely across retries
and owners.
"""

import sqlalchemy as sa

from alembic import op

revision = "ff1a2b3c4d5e"
down_revision: str | None = "ff0a1b2c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE strategy_lab_v2_dispatch_payloads (
                payload_digest TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                byte_length BIGINT NOT NULL,
                payload_fingerprint TEXT NOT NULL
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE strategy_lab_v2_dispatch_payloads CASCADE"))
