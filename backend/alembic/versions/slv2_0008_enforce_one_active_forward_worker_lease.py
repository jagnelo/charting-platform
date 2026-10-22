"""Allow at most one active worker lease for an execution attempt."""

import sqlalchemy as sa

from alembic import op

revision = "slv2_0008"
down_revision: str | None = "slv2_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX strategy_lab_v2_execution_leases_active_attempt_key
            ON strategy_lab_v2_execution_leases (worker_id, attempt_id)
            WHERE released_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS strategy_lab_v2_execution_leases_active_attempt_key"))
