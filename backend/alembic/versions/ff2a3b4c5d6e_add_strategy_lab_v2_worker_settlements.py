"""Retain immutable worker settlement receipts for terminal retries."""

import sqlalchemy as sa

from alembic import op

revision = "ff2a3b4c5d6e"
down_revision: str | None = "ff1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE strategy_lab_v2_worker_settlements (
                owner_id TEXT NOT NULL,
                settlement_fingerprint TEXT NOT NULL,
                admission_fingerprint TEXT NOT NULL,
                worker_execution_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                lease_observation_fingerprint TEXT NOT NULL,
                released_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, settlement_fingerprint),
                UNIQUE (owner_id, attempt_id),
                UNIQUE (owner_id, reservation_id)
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE strategy_lab_v2_worker_settlements CASCADE"))
