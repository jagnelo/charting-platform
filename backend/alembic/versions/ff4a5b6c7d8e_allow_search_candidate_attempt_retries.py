"""Allow one immutable search candidate to have multiple run attempts."""

import sqlalchemy as sa

from alembic import op

revision = "ff4a5b6c7d8e"
down_revision: str | None = "ff3a4b5c6d7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original three-column candidate constraint made the search-state
    # retry contract impossible to use: a new attempt for the same candidate
    # collided with the first dispatch. Locate it by its exact definition
    # rather than relying on PostgreSQL's length-truncated generated name.
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE existing_name TEXT;
            BEGIN
                FOR existing_name IN
                    SELECT constraint_row.conname
                    FROM pg_constraint AS constraint_row
                    WHERE constraint_row.conrelid =
                          'strategy_lab_v2_search_dispatches'::regclass
                      AND constraint_row.contype = 'u'
                      AND pg_get_constraintdef(constraint_row.oid) =
                          'UNIQUE (owner_id, experiment_fingerprint, candidate_index)'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE strategy_lab_v2_search_dispatches DROP CONSTRAINT %I',
                        existing_name
                    );
                END LOOP;
            END $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE strategy_lab_v2_search_dispatches
            ADD CONSTRAINT strategy_lab_v2_search_dispatch_candidate_attempt_key
            UNIQUE (owner_id, experiment_fingerprint, candidate_index, attempt_id)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE strategy_lab_v2_search_dispatches
            DROP CONSTRAINT strategy_lab_v2_search_dispatch_candidate_attempt_key
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE strategy_lab_v2_search_dispatches
            ADD CONSTRAINT strategy_lab_v2_search_dispatches_candidate_key
            UNIQUE (owner_id, experiment_fingerprint, candidate_index)
            """
        )
    )
