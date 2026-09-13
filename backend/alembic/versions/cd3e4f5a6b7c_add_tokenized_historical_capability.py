"""Add a distinct capability for tokenized historical price aggregates."""

from alembic import op

revision = "cd3e4f5a6b7c"
down_revision = "bc2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL stores ProviderCapability as a native enum. SQLite test
    # databases use SQLAlchemy's string representation and need no DDL.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE providercapability "
            "ADD VALUE IF NOT EXISTS 'TOKENIZED_HISTORICAL_PRICES'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value while rows may reference
    # it. The capability is additive and downgrade remains intentionally a
    # no-op, matching the other provider-capability enum migrations.
    return None
