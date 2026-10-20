"""Widen provider quota counters for byte-sized allowances."""

import sqlalchemy as sa

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "fb2c3d4e5f6a"
branch_labels = None
depends_on = None


_COLUMNS = ("limit_units", "reserved_units", "consumed_units")
_INT32_MAX = 2_147_483_647


def upgrade() -> None:
    with op.batch_alter_table("provider_quota_window") as batch:
        for column in _COLUMNS:
            batch.alter_column(column, existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    bind = op.get_bind()
    for column in _COLUMNS:
        too_large = bind.execute(
            sa.text(f"SELECT 1 FROM provider_quota_window WHERE {column} > :max_value LIMIT 1"),
            {"max_value": _INT32_MAX},
        ).first()
        if too_large:
            raise RuntimeError(
                f"Cannot narrow provider_quota_window.{column}; values exceed 32-bit range"
            )

    with op.batch_alter_table("provider_quota_window") as batch:
        for column in _COLUMNS:
            batch.alter_column(column, existing_type=sa.BigInteger(), type_=sa.Integer())
