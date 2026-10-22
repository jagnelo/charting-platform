"""Bind forward dispatches to their admission checkpoint."""

import sqlalchemy as sa

from alembic import op

revision = "slv2_0007"
down_revision: str | None = "slv2_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE strategy_lab_v2_forward_event_dispatches
            ADD COLUMN pre_event_checkpoint_fingerprint TEXT NULL,
            ADD COLUMN warmup_receipt_fingerprint TEXT NULL,
            ADD COLUMN admission_decision TEXT NULL,
            ADD CONSTRAINT strategy_lab_v2_forward_dispatch_admission_evidence_check
            CHECK (
                (
                    pre_event_checkpoint_fingerprint IS NULL
                    AND warmup_receipt_fingerprint IS NULL
                    AND admission_decision IS NULL
                )
                OR
                (
                    pre_event_checkpoint_fingerprint IS NOT NULL
                    AND warmup_receipt_fingerprint IS NOT NULL
                    AND admission_decision IS NOT NULL
                    AND admission_decision IN ('enqueue', 'buffered', 'correction_enqueue')
                )
            )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE strategy_lab_v2_forward_event_dispatches
            DROP CONSTRAINT strategy_lab_v2_forward_dispatch_admission_evidence_check,
            DROP COLUMN admission_decision,
            DROP COLUMN warmup_receipt_fingerprint,
            DROP COLUMN pre_event_checkpoint_fingerprint
            """
        )
    )
