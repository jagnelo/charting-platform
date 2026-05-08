"""replace radar expiry with stale lifecycle

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 17:25:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radarstate' AND e.enumlabel = 'EXPIRED'
            ) THEN
                ALTER TYPE radarstate RENAME VALUE 'EXPIRED' TO 'STALE';
            ELSIF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radarstate' AND e.enumlabel = 'expired'
            ) THEN
                ALTER TYPE radarstate RENAME VALUE 'expired' TO 'stale';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radaroutcomestatus' AND e.enumlabel = 'EXPIRED'
            ) THEN
                ALTER TYPE radaroutcomestatus RENAME VALUE 'EXPIRED' TO 'STALE';
            ELSIF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radaroutcomestatus' AND e.enumlabel = 'expired'
            ) THEN
                ALTER TYPE radaroutcomestatus RENAME VALUE 'expired' TO 'stale';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radarstate' AND e.enumlabel = 'STALE'
            ) THEN
                ALTER TYPE radarstate ADD VALUE IF NOT EXISTS 'RESOLVED';
            ELSE
                ALTER TYPE radarstate ADD VALUE IF NOT EXISTS 'resolved';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radarstate' AND e.enumlabel = 'STALE'
            ) THEN
                ALTER TYPE radarstate RENAME VALUE 'STALE' TO 'EXPIRED';
            ELSIF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radarstate' AND e.enumlabel = 'stale'
            ) THEN
                ALTER TYPE radarstate RENAME VALUE 'stale' TO 'expired';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radaroutcomestatus' AND e.enumlabel = 'STALE'
            ) THEN
                ALTER TYPE radaroutcomestatus RENAME VALUE 'STALE' TO 'EXPIRED';
            ELSIF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'radaroutcomestatus' AND e.enumlabel = 'stale'
            ) THEN
                ALTER TYPE radaroutcomestatus RENAME VALUE 'stale' TO 'expired';
            END IF;
        END
        $$;
        """
    )
