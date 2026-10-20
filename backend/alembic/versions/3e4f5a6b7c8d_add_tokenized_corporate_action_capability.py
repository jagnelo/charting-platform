"""Add a dedicated tokenized-corporate-action provider capability."""

from alembic import op

revision = "3e4f5a6b7c8d"
down_revision = "2d3e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL stores ProviderCapability as a native enum. SQLite test
    # databases use SQLAlchemy's string representation and need no DDL.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE providercapability "
            "ADD VALUE IF NOT EXISTS 'TOKENIZED_CORPORATE_ACTIONS'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value while rows may reference
    # it. The capability is additive and downgrade remains intentionally a
    # no-op, matching the earlier tokenized-assets enum migration.
    return None
