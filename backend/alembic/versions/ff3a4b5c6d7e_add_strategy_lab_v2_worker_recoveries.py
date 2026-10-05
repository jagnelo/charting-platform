"""Persist immutable worker recovery receipts for crash replay."""

import sqlalchemy as sa

from alembic import op

revision = "ff3a4b5c6d7e"
down_revision: str | None = "ff2a3b4c5d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE strategy_lab_v2_worker_recoveries (
                owner_id TEXT NOT NULL,
                recovery_fingerprint TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                plan_fingerprint TEXT NOT NULL,
                next_attempt_id TEXT NULL,
                lease_observation_fingerprint TEXT NOT NULL,
                lease_observation_sequence BIGINT NOT NULL,
                released_at TEXT NOT NULL,
                record_fingerprint TEXT NOT NULL,
                PRIMARY KEY (owner_id, recovery_fingerprint),
                UNIQUE (owner_id, attempt_id),
                UNIQUE (owner_id, reservation_id)
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE strategy_lab_v2_worker_recoveries CASCADE"))
