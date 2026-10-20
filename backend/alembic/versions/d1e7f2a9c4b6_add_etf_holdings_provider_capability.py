"""Add the shared ETF holdings provider capability."""

from alembic import op

revision = "d1e7f2a9c4b6"
down_revision = "b6e9a42d1c73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ProviderCapability is a PostgreSQL native enum in production. SQLite
    # stores the enum as text and requires no schema change.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DO $$ BEGIN ALTER TYPE providercapability "
            "ADD VALUE IF NOT EXISTS 'ETF_HOLDINGS'; "
            "EXCEPTION WHEN undefined_object THEN NULL; END $$;"
        )


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value once policy, entitlement,
    # health, or request-log rows may reference it. Keep downgrade additive.
    return None
