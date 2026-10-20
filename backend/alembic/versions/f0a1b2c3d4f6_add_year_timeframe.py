"""Add the calendar-year OHLCV timeframe used by tokenized aggregates."""

from alembic import op

revision = "f0a1b2c3d4f6"
down_revision = "ef5a6b7c8d9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL stores Timeframe as a native enum. SQLite test databases use
    # SQLAlchemy's string representation and need no DDL for this additive
    # value.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE timeframe ADD VALUE IF NOT EXISTS 'Y1'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value while persisted rows may
    # reference it. This additive migration therefore remains a no-op on
    # downgrade, matching the existing enum-value migrations.
    return None
